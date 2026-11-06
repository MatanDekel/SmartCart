import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";
import { firebaseConfig } from "./firebase-config.js";

export const configured = !!(firebaseConfig.apiKey && firebaseConfig.projectId);
export const app = configured ? initializeApp(firebaseConfig) : null;
export const auth = configured ? getAuth(app) : null;
export const db = configured ? getFirestore(app) : null;

const MESSAGES = {
  "auth/email-already-in-use": "כבר יש חשבון עם המייל הזה. אפשר להתחבר.",
  "auth/invalid-email": "כתובת המייל לא תקינה.",
  "auth/weak-password": "הסיסמה צריכה להיות באורך 6 תווים לפחות.",
  "auth/missing-password": "צריך להזין סיסמה.",
  "auth/invalid-credential": "המייל או הסיסמה לא נכונים.",
  "auth/wrong-password": "המייל או הסיסמה לא נכונים.",
  "auth/user-not-found": "לא נמצא חשבון עם המייל הזה.",
  "auth/too-many-requests": "יותר מדי ניסיונות. נסי שוב בעוד כמה דקות.",
  "auth/network-request-failed": "אין חיבור לאינטרנט. בדקי את החיבור ונסי שוב.",
  "auth/popup-blocked": "הדפדפן חסם את חלון ההתחברות. מנסה שוב בדרך אחרת…",
  "auth/popup-closed-by-user": "חלון ההתחברות נסגר לפני שהסתיים.",
  "auth/cancelled-popup-request": "חלון ההתחברות נסגר לפני שהסתיים.",
  "auth/unauthorized-domain": "הכתובת של האתר לא מאושרת ב־Firebase. צריך להוסיף אותה ב־Authorized domains.",
  "auth/account-exists-with-different-credential": "כבר יש חשבון עם המייל הזה. התחברי עם מייל וסיסמה.",
  "auth/operation-not-allowed": "ההרשמה במייל לא מופעלת ב־Firebase. צריך להפעיל Email/Password ב־Authentication."
};
export const authMessage = (e) => MESSAGES[e?.code] || "משהו השתבש. נסי שוב.";
