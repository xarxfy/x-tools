import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useFeatures } from "../api/monitor";
import { useEndMaintenance, useMaintenance } from "../api/ops";
import { useCan } from "../api/users";
import { EventList } from "../components/history";
import { Icon } from "../components/Icon";
import { PauseDialog, remaining } from "../components/Maintenance";
import { Empty, Hub, PageHead } from "../components/ui";
import { CloudflarePage } from "./CloudflarePage";
import { CredentialsPage } from "./CredentialsPage";
import { DomainsPage } from "./DomainsPage";
import { JobsPage } from "./JobsPage";
import { ServicesPage } from "./ServicesPage";

/** A page with tabs; the tab is kept in the address (?view=…), the first tab is the default. */
function useView(keys: string[], param = "view"): [string, (k: string) => void] {
  const [params, setParams] = useSearchParams();
  const view = keys.find((k) => k === params.get(param)) ?? keys[0];
  return [view, (k) => setParams(k === keys[0] ? {} : { [param]: k }, { replace: true })];
}

/** Services, with the stored logins as a second tab. */
export function ServicesHub() {
  const { t } = useTranslation();
  const can = useCan();
  const keys = can("credentials.manage") ? ["services", "logins"] : ["services"];
  const [view, setView] = useView(keys);
  return (
    <Hub title={t("nav.services")} tab={view} onTab={setView}
         tabs={keys.map((k) => ({ key: k, label: t(k === "services" ? "hub.servicesTab" : "nav.credentials") }))}>
      {view === "logins" ? <CredentialsPage /> : <ServicesPage />}
    </Hub>
  );
}

/** Domains, with DNS and tunnels (Cloudflare) as a second tab when that connection is switched on. */
export function DomainsHub() {
  const { t } = useTranslation();
  const features = useFeatures();
  const keys = features.data?.cloudflare ? ["domains", "cloudflare"] : ["domains"];
  const [view, setView] = useView(keys);
  return (
    <Hub title={t("nav.domains")} tab={view} onTab={setView}
         tabs={keys.map((k) => ({ key: k, label: t(k === "domains" ? "hub.domainsTab" : "hub.dnsTab") }))}>
      {view === "cloudflare" ? <CloudflarePage /> : <DomainsPage />}
    </Hub>
  );
}

function MaintenanceTab() {
  const { t } = useTranslation();
  const windows = useMaintenance();
  const end = useEndMaintenance();
  const can = useCan();
  const [pausing, setPausing] = useState(false);
  return (
    <>
      <PageHead title={t("hub.maintenanceTab")} sub={t("maintenance.text")}>
        {can("alerts.pause") && (
          <button type="button" className="btn btn-primary" onClick={() => setPausing(true)}>
            <Icon name="jobs" size={16} />{t("maintenance.pause")}
          </button>
        )}
      </PageHead>
      {!windows.data?.length ? <Empty>{t("hub.noWindows")}</Empty> : (
        <div className="card list">
          {windows.data.map((w) => (
            <div key={w.id} className="list-row static-row">
              <div className="list-main">
                <div className="list-title">{t("maintenance.paused", { what: w.label })}</div>
                <div className="list-sub">{[t("maintenance.remaining", { time: remaining(w.until) }), w.reason, w.created_by].filter(Boolean).join(" · ")}</div>
              </div>
              {can("alerts.pause") && (
                <button type="button" className="btn btn-small btn-ghost" disabled={end.isPending} onClick={() => end.mutate(w.id)}>{t("maintenance.end")}</button>
              )}
            </div>
          ))}
        </div>
      )}
      {pausing && <PauseDialog onClose={() => setPausing(false)} />}
    </>
  );
}

function HistoryTab() {
  const { t } = useTranslation();
  const [days, setDays] = useState(7);
  return (
    <>
      <PageHead title={t("history.title")}>
        <div className="tabs">
          {[7, 30, 90].map((d) => (
            <button key={d} type="button" className={days === d ? "active" : ""} onClick={() => setDays(d)}>{t("hub.days", { count: d })}</button>
          ))}
        </div>
      </PageHead>
      <EventList limit={300} days={days} />
    </>
  );
}

/** Monitoring: jobs (heartbeats), the history of problems and the maintenance windows. */
export function MonitoringHub() {
  const { t } = useTranslation();
  const keys = ["jobs", "history", "maintenance"];
  const [view, setView] = useView(keys);
  return (
    <Hub title={t("nav.monitoring")} tab={view} onTab={setView}
         tabs={[{ key: "jobs", label: t("nav.jobs") }, { key: "history", label: t("hub.historyTab") }, { key: "maintenance", label: t("hub.maintenanceTab") }]}>
      {view === "history" ? <HistoryTab /> : view === "maintenance" ? <MaintenanceTab /> : <JobsPage />}
    </Hub>
  );
}
