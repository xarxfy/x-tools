import { Navigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PageHead } from "../components/ui";
import { AccountSettings } from "./SettingsAccount";

/** Your own account: password, two-factor login, language. */
export function AccountPage() {
  const { t } = useTranslation();
  return (
    <>
      <PageHead title={t("nav.account")} />
      <AccountSettings />
    </>
  );
}

const SETTINGS_TO_ADMIN: Record<string, string> = {
  general: "system", about: "system", notifications: "notifications", agents: "agents", cloudflare: "cloudflare",
  users: "users", audit: "audit", backup: "backup",
};

/** Old links: /settings?tab=… → Account or the Administration tab that took over. */
export function SettingsRedirect() {
  const tab = new URLSearchParams(window.location.search).get("tab") ?? "";
  if (tab === "agents") return <Navigate to="/servers" replace />;
  if (SETTINGS_TO_ADMIN[tab]) return <Navigate to={`/admin?tab=${SETTINGS_TO_ADMIN[tab]}`} replace />;
  return <Navigate to="/account" replace />;
}

/** /credentials and /cloudflare and /jobs became tabs. */
export function MovedRedirect({ to }: { to: string }) {
  useParams();
  return <Navigate to={to} replace />;
}
