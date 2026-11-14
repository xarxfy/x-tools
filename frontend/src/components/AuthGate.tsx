import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAppStatus, useMe } from "../api/auth";

/** Routes the user to /setup (first start), /login (not logged in) or the app. */
export function AuthGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const location = useLocation();
  const status = useAppStatus();
  const me = useMe(status.data ? !status.data.needs_setup : false);

  if (status.isError || me.isError) {
    return (
      <div className="center-state">
        <div>
          <p>{t("app.error")}</p>
          <button className="btn" onClick={() => window.location.reload()}>
            {t("app.retry")}
          </button>
        </div>
      </div>
    );
  }
  if (!status.data || (!status.data.needs_setup && me.isPending)) {
    return <div className="center-state">{t("app.loading")}</div>;
  }
  if (status.data.needs_setup) return <Navigate to="/setup" replace />;
  if (!me.data) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}
