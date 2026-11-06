"""
Daily price pipeline for SmartCart.

Downloads store + full price files published under the Israeli price-transparency
regulations (via il-supermarket-scraper), and writes compact JSON files that the
site reads from the `price-data` branch.

Output layout (OUT_DIR):
  index.json                      {updated, chains:[{key,name,stores}]}
  stores.json                     [{c, id, n, city, addr}]
  chains/<key>/base.json          {codes, names, units, prices, w}  (parallel arrays)
  chains/<key>/stores/<id>.json   {b: base64 bitset of item indexes, d: {idx: price}}
  report.json                     per-chain diagnostics
"""
import base64, collections, datetime, glob, json, os, re, sys, traceback
import xml.etree.ElementTree as ET

CHAINS = {
    "SHUFERSAL": "שופרסל",
    "RAMI_LEVY": "רמי לוי",
    "VICTORY_NEW_SOURCE": "ויקטורי",
    "YAYNO_BITAN_AND_CARREFOUR": "יינות ביתן / קרפור",
    "OSHER_AD": "אושר עד",
    "MAHSANI_ASHUK_NEW_SOURCE": "מחסני השוק",
    "TIV_TAAM": "טיב טעם",
    "HAZI_HINAM": "חצי חינם",
    "YOHANANOF": "יוחננוף",
    "SUPER_SAPIR": "סופר ספיר / נטו חיסכון",
    "KING_STORE": "קינג סטור",
    "SHEFA_BARCART_ASHEM": "שפע ברכת השם",
    "NETIV_HASED": "נתיב החסד",
    "ZOL_VEBEGADOL": "זול ובגדול",
    "FRESH_MARKET_AND_SUPER_DOSH": "פרש מרקט / סופר דוש",
}
DUMPS = os.environ.get("XML_STORE_PATH", "dumps")
OUT = os.environ.get("OUT_DIR", "out")


def local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def child_map(el):
    m = {}
    for c in el:
        k = local(c.tag)
        if k not in m:
            m[k] = (c.text or "").strip()
    return m


def norm_store_id(s):
    s = re.sub(r"\D", "", s or "")
    return str(int(s)) if s else ""


def norm_code(s):
    s = re.sub(r"\s", "", s or "")
    return s.lstrip("0") or s


def norm_city(s):
    s = (s or "").strip().replace("-", " ").replace("־", " ")
    s = re.sub(r"\s+", " ", s)
    return "" if (not s or s.isdigit() or s in ("0", "unknown")) else s


CITY_CODES = {}
CITY_NAMES = []


def load_city_codes():
    """CBS locality codes -> names (many chains publish the city as a numeric code)."""
    import urllib.request
    url = ("https://data.gov.il/api/3/action/datastore_search"
           "?resource_id=5c78e9fa-c2e2-4771-93ff-7f400a12f7ba&limit=5000")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SmartCart price pipeline)"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.load(r)
        for rec in data["result"]["records"]:
            code, name = str(rec.get("סמל_ישוב", "")).strip(), str(rec.get("שם_ישוב", "")).strip()
            if code.isdigit() and int(code) > 0 and name:
                CITY_CODES[int(code)] = norm_city(name)
    except Exception as e:  # noqa
        print("city codes download failed:", e)
    names = {n for n in CITY_CODES.values() if n and len(n) >= 3}
    CITY_NAMES.extend(sorted(names, key=len, reverse=True))


def resolve_city(raw, store_name):
    raw = (raw or "").strip()
    if raw.isdigit():
        city = CITY_CODES.get(int(raw), "")
    else:
        city = norm_city(raw)
    if not city and store_name:
        n = " " + norm_city(store_name) + " "
        for c in CITY_NAMES:
            if f" {c} " in n:
                return c
    return city


def parse_stores(path):
    stores = {}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return stores
    for el in root.iter():
        m = child_map(el)
        if "storeid" in m and ("storename" in m or "address" in m):
            sid = norm_store_id(m.get("storeid"))
            if sid:
                stores[sid] = {
                    "n": m.get("storename", "").strip(),
                    "raw_city": m.get("city", "").strip(),
                    "addr": m.get("address", "").strip(),
                }
    return stores


def parse_prices(path):
    store_id, items = "", []
    for _, el in ET.iterparse(path, events=("end",)):
        t = local(el.tag)
        if t == "storeid" and not store_id:
            store_id = norm_store_id(el.text)
        elif t in ("item", "product"):
            m = child_map(el)
            code = norm_code(m.get("itemcode", ""))
            try:
                price = round(float(m.get("itemprice", "") or "nan"), 2)
            except ValueError:
                price = None
            if code and price and price > 0:
                name = m.get("itemname") or m.get("manufactureritemdescription") or ""
                qty, unit = m.get("quantity", ""), m.get("unitqty", "") or m.get("unitofmeasure", "")
                try:
                    qf = float(qty)
                    qty = ("%g" % qf) if qf > 0 else ""
                except ValueError:
                    qty = ""
                w = (m.get("bisweighted") or m.get("blsweighted") or "0").strip() in ("1", "true", "True")
                items.append((code, name.strip(), f"{qty} {unit}".strip(), price, w))
            el.clear()
    if not store_id:
        mm = re.search(r"pricefull\d+-(?:\d+-)?(\d+)-\d{8,}", os.path.basename(path), re.I)
        store_id = norm_store_id(mm.group(1)) if mm else ""
    return store_id, items


def chain_folder(key):
    try:
        from il_supermarket_scarper.utils import DumpFolderNames
        return os.path.join(DUMPS, DumpFolderNames[key].value)
    except Exception:
        return None


def build_chain(key, folder, report):
    files = [f for f in glob.glob(os.path.join(folder, "**", "*"), recursive=True) if os.path.isfile(f)]
    xmls = [f for f in files if f.lower().endswith(".xml")]
    store_files = [f for f in xmls if "store" in os.path.basename(f).lower()]
    price_files = [f for f in xmls if "pricefull" in os.path.basename(f).lower()]
    report.update(files=len(files), store_files=len(store_files), price_files=len(price_files))

    meta = {}
    for f in store_files:
        meta.update(parse_stores(f))

    per_store = {}
    info = {}
    for f in sorted(price_files):  # sorted -> latest timestamp wins
        try:
            sid, items = parse_prices(f)
        except Exception as e:  # noqa
            report.setdefault("errors", []).append(f"{os.path.basename(f)}: {e}")
            continue
        if not sid or not items:
            continue
        prices = {}
        for code, name, unit, price, w in items:
            prices[code] = price
            if code not in info or (not info[code][0] and name):
                info[code] = (name, unit, w)
        per_store[sid] = prices
    if not per_store:
        return None

    freq = collections.Counter()
    for p in per_store.values():
        freq.update(p.keys())
    codes = [c for c, _ in freq.most_common()]
    idx = {c: i for i, c in enumerate(codes)}
    base_prices = []
    for c in codes:
        cnt = collections.Counter(p[c] for p in per_store.values() if c in p)
        base_prices.append(cnt.most_common(1)[0][0])

    out_dir = os.path.join(OUT, "chains", key)
    os.makedirs(os.path.join(out_dir, "stores"), exist_ok=True)
    base = {
        "codes": codes,
        "names": [info[c][0] for c in codes],
        "units": [info[c][1] for c in codes],
        "prices": base_prices,
        "w": [i for i, c in enumerate(codes) if info[c][2]],
    }
    with open(os.path.join(out_dir, "base.json"), "w", encoding="utf-8") as fh:
        json.dump(base, fh, ensure_ascii=False, separators=(",", ":"))

    stores_out = []
    for sid, prices in per_store.items():
        bits = bytearray((len(codes) + 7) // 8)
        diffs = {}
        for c, pr in prices.items():
            i = idx[c]
            bits[i >> 3] |= 1 << (i & 7)
            if pr != base_prices[i]:
                diffs[i] = pr
        with open(os.path.join(out_dir, "stores", f"{sid}.json"), "w", encoding="utf-8") as fh:
            json.dump({"b": base64.b64encode(bytes(bits)).decode(), "d": diffs}, fh, separators=(",", ":"))
        m = meta.get(sid, {})
        name = m.get("n") or f"סניף {sid}"
        stores_out.append({"c": key, "id": sid, "n": name,
                           "city": resolve_city(m.get("raw_city", ""), m.get("n", "")), "addr": m.get("addr", "")})
    report.update(stores=len(stores_out), items=len(codes),
                  stores_with_city=sum(1 for s in stores_out if s["city"]),
                  raw_city_samples=sorted({v.get("raw_city", "") for v in meta.values()})[:8])
    return stores_out


def scrape(keys):
    from il_supermarket_scarper import ScarpingTask
    task = ScarpingTask(enabled_scrapers=keys, files_types=["STORE_FILE", "PRICE_FULL_FILE"],
                        multiprocessing=4, timeout_in_seconds=60 * 60 * 3)
    task.start()
    task.join()


def main():
    keys = [k for k in os.environ.get("CHAINS", ",".join(CHAINS)).split(",") if k in CHAINS]
    if os.environ.get("SKIP_SCRAPE") != "1":
        try:
            scrape(keys)
        except Exception:
            traceback.print_exc()
    os.makedirs(OUT, exist_ok=True)
    load_city_codes()
    all_stores, chains, report = [], [], {"_city_codes_loaded": len(CITY_CODES)}
    for key in keys:
        rep = report.setdefault(key, {})
        folder = chain_folder(key) or os.path.join(DUMPS, key)
        if not os.path.isdir(folder):
            rep["error"] = f"no folder {folder}"
            continue
        try:
            st = build_chain(key, folder, rep)
        except Exception as e:  # noqa
            rep["error"] = repr(e)
            traceback.print_exc()
            continue
        if st:
            all_stores += st
            chains.append({"key": key, "name": CHAINS[key], "stores": len(st)})
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")
    with open(os.path.join(OUT, "stores.json"), "w", encoding="utf-8") as fh:
        json.dump(all_stores, fh, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"updated": now, "chains": chains}, fh, ensure_ascii=False)
    with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as fh:
        json.dump({"updated": now, "chains": report}, fh, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if not chains:
        sys.exit("No chain produced data")


if __name__ == "__main__":
    main()
