import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useFeatures, useOverview } from "../api/monitor";
import { Icon, type IconName } from "../components/Icon";
import { Dot, Loading, PageHead } from "../components/ui";
import { ago, level } from "../components/format";
import { EventList } from "../components/history";
import { useCan } from "../api/users";
import { issueText } from "../components/issueText";
import { useState } from "react";
import { useUpdateInfo } from "../api/ops";
import { MaintenanceBanner, PauseDialog } from "../components/Maintenance";
import "./OverviewPage.css";

export function OverviewPage() {
  const { t } = useTranslation();
  const overview = useOverview();
  const customersOn = useFeatures().data?.customers ?? false;
  const isAdmin = useCan()("admin.settings");
  const canPause = useCan()("alerts.pause");
  const [pausing, setPausing] = useState(false);
  const update = useUpdateInfo(isAdmin);
  if (!overview.data) return <Loading error={overview.error} retry={() => overview.refetch()} />;
  const { issues, counts, notifications } = overview.data;
  const open = issues.filter((i) => !i.manual);
  const live = open.filter((i) => !i.paused); // paused ones (maintenance window) do not count
  const manual = issues.filter((i) => i.manual);
  const empty = counts.services === 0;

  const chips: { to: string; icon: IconName; label: string; value: string }[] = [
    ...(counts.guests ? [{ to: "/proxmox", icon: "proxmox" as IconName, label: t("overview.guests"), value: `${counts.guests_running}/${counts.guests}` }] : []),
    { to: "/docker", icon: "docker", label: t("overview.containers"), value: `${counts.containers_running}/${counts.containers}` },
    { to: "/services", icon: "services", label: t("nav.services"), value: String(counts.services) },
    ...(customersOn ? [{ to: "/customers", icon: "customers" as IconName, label: t("nav.customers"), value: String(counts.customers) }] : []),
  ];
  const { hosts, jobs, backup, sites } = overview.data;
  const sitesUp = sites.filter((s) => s.level === "up").length;
  const soon = sites.filter((s) => s.cert_expires && (s.cert_expires - Date.now() / 1000) / 86400 < 14)
    .map((s) => Math.max(0, Math.floor((s.cert_expires! - Date.now() / 1000) / 86400)));
  const worst = live.some((i) => i.level === "down") ? "down" : live.length ? "warn" : "up";

  return (
    <>
      <PageHead title={t("nav.overview")}>
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

      <section className={`card status-card is-${worst}`}>
        <div className="status-head">
          <span className="status-icon"><Icon name={live.length ? "alert" : "check"} size={22} /></span>
          <div className="status-text">
            <h2>{live.length ? t("overview.attention", { count: live.length }) : t("overview.nothingToDo")}</h2>
            <p className="muted">
              {notifications ? t("overview.notifyOn") : !isAdmin ? t("overview.notifyOff") : (
                <>{t("overview.notifyOff")} <Link to="/admin?tab=notifications">{t("overview.setUp")}</Link></>
              )}
            </p>
          </div>
        </div>
        <div className="ov-chips">
          {chips.map((c) => (
            <Link key={c.to} to={c.to} className="ov-chip">
              <Icon name={c.icon} size={15} /><b>{c.value}</b><span>{c.label}</span>
            </Link>
          ))}
        </div>
      </section>

      <div className="ov-grid">
        <div className="ov-main">
          <h2 className="section-title first">{t("overview.needsAttention")}</h2>
          <section className="card">
            {open.length === 0 ? <p className="card-pad muted no-problems">{t("overview.noProblems")}</p> : (
              <ul className="issue-list">
                {open.map((i) => (
                  <li key={i.key}>
                    <Link to={i.link}>
                      <Dot state={i.level} />
                      <span>{issueText(i.text)}</span>
                      {i.paused && <span className="badge">{t("maintenance.badge")}</span>}
                      <Icon name="chevron" size={14} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {manual.length > 0 && (
              <p className="muted manual-note card-pad">
                {t("overview.manual", { names: manual.map((i) => i.text.replace(/^Container (.*): stopped by you$/, "$1")).join(", ") })}
              </p>
            )}
          </section>

          <h2 className="section-title">{t("history.title")}</h2>
          <EventList limit={8} />
        </div>

        <aside className="ov-side">
          <h2 className="section-title first">{t("overview.servers")}</h2>
          <section className="card host-list">
            {hosts.length <= 1 && <p className="muted host-hint">{t("overview.serversEmpty")}</p>}
            {hosts.map((h) => (
              <Link key={h.link} to={h.link} className="host-row">
                <div className="host-top">
                  <Dot state={h.state} /><strong>{h.name}</strong>
                  {h.updates ? <span className="badge">{t("overview.updates", { count: h.updates })}</span> : null}
                  {h.reboot && <span className="badge badge-warn">{t("overview.reboot")}</span>}
                </div>
                <div className="ov-host-meters">
                  {([["load", h.load], ["mem", h.mem], ["disk", h.disk]] as [string, number | null][]).map(([k, v]) => v === null ? null : (
                    <div key={k} className="mini" title={`${t(`overview.${k}`)} ${v} %`}>
                      <span>{t(`overview.${k}`)}</span>
                      <div className="bar"><span className={`bar-${level(v)}`} style={{ width: `${Math.min(100, v)}%` }} /></div>
                      <b>{v} %</b>
                    </div>
                  ))}
                </div>
              </Link>
            ))}
          </section>

          <h2 className="section-title">{t("overview.jobs")} · {t("overview.backup")}</h2>
          <section className="card side-list">
            <Link to="/monitoring" className="side-row">
              <Dot state={!jobs.total ? "off" : jobs.late ? "down" : "up"} />
              <span>{!jobs.total ? t("overview.jobsNone") : jobs.late ? t("overview.jobsLate", { count: jobs.late }) : t("overview.jobsAllOk", { ok: jobs.ok, total: jobs.total - jobs.paused })}</span>
              {jobs.paused > 0 && <span className="badge">{t("overview.jobsPaused", { count: jobs.paused })}</span>}
            </Link>
            <Link to="/admin?tab=backup" className="side-row">
              <Dot state={!backup.enabled ? "off" : backup.last_ok === false ? "down" : backup.last_at ? "up" : "warn"} />
              <span>{!backup.enabled ? t("overview.backupOff") : backup.last_ok === false ? t("overview.backupFail")
                : backup.last_at ? t("overview.backupOk", { when: ago(backup.last_at) }) : t("overview.backupWait")}</span>
            </Link>
          </section>

          {customersOn && sites.length > 0 && (
            <>
              <h2 className="section-title">{t("overview.websites")}</h2>
              <Link to="/customers" className="card side-list">
                <span className="side-row">
                  <Dot state={sitesUp === sites.length ? "up" : sites.some((s) => s.level === "down") ? "down" : "warn"} />
                  <span>{t("overview.websitesUp", { up: sitesUp, total: sites.length })}</span>
                </span>
                <span className="side-row">
                  <Dot state={soon.length ? "warn" : "up"} />
                  <span>{soon.length ? t("overview.certSoon", { days: Math.min(...soon) }) : t("overview.allCertsOk")}</span>
                </span>
              </Link>
            </>
          )}
        </aside>
      </div>

      {pausing && <PauseDialog onClose={() => setPausing(false)} />}

      {empty && (
        <div className="card card-pad start-card">
          <strong>{t("overview.startTitle")}</strong>
          <ol>
            <li><Link to="/services">{t("overview.start1")}</Link></li>
            {customersOn && <li><Link to="/customers">{t("overview.start2")}</Link></li>}
            <li><Link to="/admin?tab=notifications">{t("overview.start3")}</Link></li>
            <li><Link to="/servers">{t("overview.start4")}</Link></li>
          </ol>
        </div>
      )}
    </>
  );
}
