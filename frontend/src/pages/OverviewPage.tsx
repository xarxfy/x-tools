import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useOverview } from "../api/monitor";
import { Icon, type IconName } from "../components/Icon";
import { Dot, Loading, PageHead } from "../components/ui";
import { level, pct } from "../components/format";
import "./OverviewPage.css";

export function OverviewPage() {
  const { t } = useTranslation();
  const overview = useOverview();
  if (!overview.data) return <Loading error={overview.error} retry={() => overview.refetch()} />;
  const { issues, counts, system, notifications } = overview.data;
  const open = issues.filter((i) => !i.manual);
  const manual = issues.filter((i) => i.manual);
  const empty = counts.services === 0 && counts.customers === 0;

  const tiles: { to: string; icon: IconName; label: string; value: string; sub?: string }[] = [
    { to: "/servers", icon: "servers", label: t("nav.servers"), value: String(counts.servers) },
    {
      to: "/servers/local?tab=docker", icon: "docker", label: t("overview.containers"),
      value: `${counts.containers_running}/${counts.containers}`, sub: t("overview.running"),
    },
    { to: "/services", icon: "services", label: t("nav.services"), value: String(counts.services) },
    {
      to: "/customers", icon: "customers", label: t("nav.customers"), value: String(counts.customers),
      sub: counts.sites ? t("overview.sitesUp", { up: counts.sites_up, total: counts.sites }) : undefined,
    },
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
      <PageHead title={t("nav.overview")} sub={open.length ? t("overview.attention", { count: open.length }) : t("overview.allGood")} />

      <section className={`card status-card ${open.length ? (open.some((i) => i.level === "down") ? "is-down" : "is-warn") : "is-up"}`}>
        <div className="status-head">
          <span className="status-icon"><Icon name={open.length ? "alert" : "check"} size={22} /></span>
          <div>
            <h2>{open.length ? t("overview.needsAttention") : t("overview.nothingToDo")}</h2>
            <p className="muted">
              {notifications ? t("overview.notifyOn") : (
                <>
                  {t("overview.notifyOff")} <Link to="/settings">{t("overview.setUp")}</Link>
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

      <div className="tile-grid">
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
          <Link to="/servers/local" className="card card-pad overview-meters">
            {meters.map(([label, value]) => (
              <div key={label} className="meter">
                <div className="meter-top"><span>{label}</span><b>{value.toFixed(0)} %</b></div>
                <div className="bar"><span className={`bar-${level(value)}`} style={{ width: `${Math.min(100, value)}%` }} /></div>
              </div>
            ))}
          </Link>
        </>
      )}

      {empty && (
        <div className="card card-pad start-card">
          <strong>{t("overview.startTitle")}</strong>
          <ol>
            <li><Link to="/services">{t("overview.start1")}</Link></li>
            <li><Link to="/customers">{t("overview.start2")}</Link></li>
            <li><Link to="/settings">{t("overview.start3")}</Link></li>
          </ol>
        </div>
      )}
    </>
  );
}
