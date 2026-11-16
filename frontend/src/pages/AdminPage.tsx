import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useCan } from "../api/users";
import { Empty, PageHead } from "../components/ui";
import { RolesSettings } from "./AdminRoles";
import { BackupSettings } from "./SettingsAccount";
import { CloudflareSettings } from "./SettingsCloudflare";
import { Agents, Notifications } from "./SettingsPage";
import { AuditSettings, UsersSettings } from "./SettingsUsers";

// tab → permissions of which one is enough to see it
const TABS: Record<string, string[]> = {
  users: ["admin.users"],
  roles: ["admin.users", "admin.roles"],
  audit: ["admin.audit"],
  agents: ["admin.agents"],
  notifications: ["admin.settings"],
  cloudflare: ["admin.settings"],
  backup: ["admin.backup"],
};

/** Administration: users, roles and permissions, audit log, agents, notifications, Cloudflare, backup. */
export function AdminPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const can = useCan();
  const tabs = Object.keys(TABS).filter((k) => TABS[k].some((p) => can(p)));
  const tab = tabs.find((k) => k === params.get("tab")) ?? tabs[0];
  if (!tab) return <Empty>{t("administration.forbidden")}</Empty>;
  return (
    <>
      <PageHead title={t("nav.administration")} sub={t("administration.sub")} />
      <div className="tabs" role="tablist">
        {tabs.map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""}
                  onClick={() => setParams(k === tabs[0] ? {} : { tab: k })}>
            {t(`administration.tab.${k}`)}
          </button>
        ))}
      </div>
      {tab === "users" ? <UsersSettings /> : tab === "roles" ? <RolesSettings /> : tab === "audit" ? <AuditSettings />
        : tab === "agents" ? <Agents /> : tab === "notifications" ? <Notifications />
          : tab === "cloudflare" ? <CloudflareSettings /> : <BackupSettings />}
    </>
  );
}
