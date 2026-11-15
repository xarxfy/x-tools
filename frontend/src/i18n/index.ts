import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import de from "./de.json";
import en from "./en.json";

/** Languages of the interface. Adding one = adding a JSON file here (missing keys fall back to English). */
export const LANGUAGES = { en: "English", de: "Deutsch" } as const;
export type Language = keyof typeof LANGUAGES;

const KEY = "xt_lang";

function initial(): Language {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored && stored in LANGUAGES) return stored as Language;
  } catch {
    /* storage may be blocked */
  }
  return (navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
}

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, de: { translation: de } },
  lng: initial(),
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React already escapes
});
document.documentElement.lang = i18n.language;

export function setLanguage(lng: Language): void {
  try {
    localStorage.setItem(KEY, lng);
  } catch {
    /* ignore */
  }
  document.documentElement.lang = lng;
  void i18n.changeLanguage(lng);
}

export default i18n;
