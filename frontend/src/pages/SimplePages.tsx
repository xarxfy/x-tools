import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="center-state">
      <div>
        <h1>{t("pages.notFound")}</h1>
        <Link to="/">{t("pages.backHome")}</Link>
      </div>
    </div>
  );
}
