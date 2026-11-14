import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function OverviewPage() {
  const { t } = useTranslation();
  return (
    <>
      <header className="page-head">
        <div>
          <h1>{t("pages.overview.title")}</h1>
        </div>
      </header>
      <div className="card card-pad">
        <p style={{ marginTop: 0 }}>
          <strong>{t("pages.overview.welcome")}</strong>
        </p>
        <p className="muted" style={{ marginBottom: 0 }}>
          {t("pages.overview.next")}
        </p>
      </div>
    </>
  );
}

export function ComingSoonPage({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return (
    <>
      <header className="page-head">
        <div>
          <h1>{t(titleKey)}</h1>
          <p>{t("pages.comingSoon")}</p>
        </div>
      </header>
      <div className="card card-pad muted">{t("pages.comingSoonText")}</div>
    </>
  );
}

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
