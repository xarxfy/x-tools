import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useFeatures, useOverview } from "../api/monitor";
import { Icon, type IconName } from "../components/Icon";
import { Dot, Loading, PageHead } from "../components/ui";
import { level, pct } from "../components/format";
import { EventList } from "../components/history";
import { useCan } from "../api/users";
import { useState } from "react";
import { useUpdateInfo } from "../api/ops";
import { MaintenanceBanner, PauseDialog } from "../components/Maintenance";
import "./OverviewPage.css";

export function OverviewPage() {
  const { t } = useTranslation();
  const overview = useOverview();
  const customersOn = useFeatures().data?.customers ?? false;
  const isAdmin = useCan()("admin");
  const canPause = useCan()("operator");
  const [pausing, setPausing] = useState(false);
  const update = useUpdateInfo(isAdmin);
  if (!overview.data) return <Loading error={overview.error} retry={() => overview.refetch()} />;
  const { issues, counts, system, notifications } = overview.data;
  const open = issues.filter((i) => !i.manual);
  const live = open.filter((i) => !i.paused); // paused ones (maintenance window) do not count
  const manual = issues.filter((i) => i.manual);
  const empty = counts.services === 0;

  const tiles: { to: string; icon: IconName; label: string; value: string; sub?: string }[] = [
    ...(counts.guests ? [{
      to: "/proxmox", icon: "proxmox" as IconName, label: t("overview.guests"),
      value: `${counts.guests_running}/${counts.guests}`, sub: t("overview.running"),
    }] : []),
    {
      to: "/docker", icon: "docker", label: t("overview.containers"),
      value: `${counts.containers_running}/${counts.containers}`, sub: t("overview.running"),
    },
    { to: "/services", icon: "services", label: t("nav.services"), value: String(counts.services) },
    ...(customersOn ? [{
      to: "/customers", icon: "customers" as IconName, label: t("nav.customers"), value: String(counts.customers),
      sub: counts.sites ? t("overview.sitesUp", { up: counts.sites_up, total: counts.sites }) : undefined,
    }] : []),
  ];
  const meters = system
    ? ([
      [t("servers.load"), system.load ? (system.load[0] / Math.max(1, system.cpus ?? 1)) * 100 : undefined],
      [t("servers.memory"), system.mem_total ? pct(system.mem_used, system.mem_total) : undefined],
      [t("servers.disk"), system.disk_total ? pct(system.disk_used, system.disk_total) : undefined],
    ].filter(([, v]) => v !== undefined) as [string, number][])
    : [];

  return (
    <>
      <PageHead title={t("nav.overview")} sub={live.length ? t("overview.attention", { count: live.length }) : t("overview.allGood")}>
        {canPause && (
          <button type="button" className="btn" onClick={() => setPausing(true)}>
            <Icon name="jobs" size={16} />{t("maintenance.pause")}
          </button>
        )}
      </PageHead>
      {update.data?.available && (
        <Link to="/settings?tab=about" className="card card-pad update-banner">
          <Icon name="download" size={16} />
          <span>{t("update.available", { version: update.data.latest })}</span>
          <Icon name="chevron" size={14} />
        </Link>
      )}
      <MaintenanceBanner />

      <section className={`card status-card ${live.length ? (live.some((i) => i.level === "down") ? "is-down" : "is-warn") : "is-up"}`}>
        <div className="status-head">
          <span className="status-icon"><Icon name={live.length ? "alert" : "check"} size={22} /></span>
          <div>
            <h2>{live.length ? t("overview.needsAttention") : t("overview.nothingToDo")}</h2>
            <p className="muted">
              {notifications ? t("overview.notifyOn") : !isAdmin ? t("overview.notifyOff") : (
                <>
                  {t("overview.notifyOff")} <Link to="/settings?tab=notifications">{t("overview.setUp")}</Link>
                </>
              )}
            </p>
          </div>
        </div>
        {open.length > 0 && (
          <ul className="issue-list">
            {open.map((i) => (
              <li key={i.key}>
                <Link to={i.link}>
                  <Dot state={i.level} />
                  <span>{i.text}</span>
                  {i.paused && <span className="badge">{t("maintenance.badge")}</span>}
                  <Icon name="chevron" size={14} />
                </Link>
              </li>
            ))}
          </ul>
        )}
        {manual.length > 0 && (
          <p className="muted manual-note">
            {t("overview.manual", { names: manual.map((i) => i.text.replace(/^Container (.*): stopped by you$/, "$1")).join(", ") })}
          </p>
        )}
      </section>

      <div className={`tile-grid tiles-${tiles.length}`}>
        {tiles.map((tile) => (
          <Link key={tile.to} to={tile.to} className="card tile">
            <span className="tile-icon"><Icon name={tile.icon} size={18} /></span>
            <span className="tile-value">{tile.value}</span>
            <span className="tile-label">{tile.label}{tile.sub && <span className="muted"> · {tile.sub}</span>}</span>
          </Link>
        ))}
      </div>

      {meters.length > 0 && (
        <>
          <h2 className="section-title">{t("servers.local")}</h2>
          <Link to="/docker#local" className="card card-pad overview-meters">
            {meters.map(([label, value]) => (
              <div key={label} className="meter">
                <div className="meter-top"><span>{label}</span><b>{value.toFixed(0)} %</b></div>
                <div className="bar"><span className={`bar-${level(value)}`} style={{ width: `${Math.min(100, value)}%` }} /></div>
              </div>
            ))}
          </Link>
        </>
      )}

      <h2 className="section-title">{t("history.title")}</h2>
      <EventList limit={8} />

      {pausing && <PauseDialog onClose={() => setPausing(false)} />}

      {empty && (
        <div className="card card-pad start-card">
          <strong>{t("overview.startTitle")}</strong>
          <ol>
            <li><Link to="/services">{t("overview.start1")}</Link></li>
            {customersOn && <li><Link to="/customers">{t("overview.start2")}</Link></li>}
            <li><Link to="/settings?tab=notifications">{t("overview.start3")}</Link></li>
            <li><Link to="/settings?tab=agents">{t("overview.start4")}</Link></li>
          </ol>
        </div>
      )}
    </>
  );
}
