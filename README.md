# SmartCart – מה קונים השבוע

רשימת קניות לסופר: מוצרים לפי קטגוריות, בחירת כמויות, סימון מה כבר בעגלה, ומוצרים שנוספו נשמרים גם לשבוע הבא.

אתר סטטי בקובץ אחד (`index.html`). מחוץ ל־claude.ai הנתונים נשמרים בדפדפן (localStorage).

## פריסה ל־Vercel

אין צורך ב־build. ב־Vercel: Add New → Project → בוחרים את `SmartCart` → Framework Preset: **Other** → Deploy.

## הרשמה במייל (Firebase)

1. ב־[Firebase Console](https://console.firebase.google.com) יוצרים פרויקט ומוסיפים Web app.
2. מעתיקים את ה־config לקובץ `firebase-config.js`.
3. Authentication → Sign-in method → מפעילים **Email/Password**.
4. Authentication → Settings → Authorized domains → מוסיפים את הדומיין של Vercel.
5. Firestore Database → Create database, ובלשונית Rules מדביקים את התוכן של `firestore.rules`.

כל משתמש רואה רק את הרשימה שלו (`users/{uid}/lists/shopping`).
