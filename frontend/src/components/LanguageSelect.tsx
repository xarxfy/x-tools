import { useTranslation } from "react-i18next";
import { LANGUAGES, setLanguage, type Language } from "../i18n";

export function LanguageSelect({ compact = false }: { compact?: boolean }) {
  const { i18n, t } = useTranslation();
  return (
    <select className={compact ? "input lang-select" : "input"} aria-label={t("account.language")}
            value={i18n.language.slice(0, 2)} onChange={(e) => setLanguage(e.target.value as Language)}>
      {Object.entries(LANGUAGES).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
    </select>
  );
}
