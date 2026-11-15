import { issueText } from "./issueText";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useEvents, useMetrics, type HistoryEvent, type MetricPoint } from "../api/account";
import { Dot, Empty } from "./ui";
import { ago, fmtDuration } from "./format";
import "./history.css";

const SERIES: { key: "load" | "mem" | "disk"; color: string }[] = [
  { key: "load", color: "var(--accent)" },
  { key: "mem", color: "#af52de" },
  { key: "disk", color: "var(--warn)" },
];
const W = 640;
const H = 150;

function path(points: MetricPoint[], key: "load" | "mem" | "disk", t0: number, t1: number): string {
  let d = "";
  let gap = true;
  for (const p of points) {
    const v = p[key];
    if (v === null || v === undefined) {
      gap = true;
      continue;
    }
    const x = ((Date.parse(p.ts) - t0) / Math.max(1, t1 - t0)) * W;
    const y = H - (Math.min(100, Math.max(0, v)) / 100) * H;
    d += `${gap ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    gap = false;
  }
  return d;
}

/** Load, memory and disk over time (percent). */
export function MetricsChart({ source }: { source: string }) {
  const { t } = useTranslation();
  const [hours, setHours] = useState(24);
  const metrics = useMetrics(source, hours);
  const points = metrics.data ?? [];
  const t1 = Date.now();
  const t0 = t1 - hours * 3600_000;
  return (
    <div className="chart-card card card-pad">
      <div className="chart-head">
        <div className="chart-legend">
          {SERIES.map((s) => (
            <span key={s.key}><i style={{ background: s.color }} />{t(`history.${s.key}`)}</span>
          ))}
        </div>
        <div className="tabs tabs-small">
          {[24, 24 * 7, 24 * 30].map((h) => (
            <button key={h} type="button" className={hours === h ? "active" : ""} onClick={() => setHours(h)}>
              {t(`history.range.${h}`)}
            </button>
          ))}
        </div>
      </div>
      {points.length < 2 ? (
        <p className="muted chart-empty">{t("history.noMetrics")}</p>
      ) : (
        <svg className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
             aria-label={t("history.chartLabel")}>
          {[25, 50, 75].map((v) => (
            <line key={v} x1="0" x2={W} y1={H - (v / 100) * H} y2={H - (v / 100) * H} className="chart-grid" />
          ))}
          {SERIES.map((s) => (
            <path key={s.key} d={path(points, s.key, t0, t1)} fill="none" stroke={s.color} strokeWidth="2"
                  vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          ))}
        </svg>
      )}
      <div className="chart-axis muted">
        <span>{t(`history.range.${hours}`)}</span>
        <span>{t("history.now")}</span>
      </div>
    </div>
  );
}

function duration(e: HistoryEvent): string {
  const end = e.ended_at ? Date.parse(e.ended_at) : Date.now();
  return fmtDuration(Math.max(60, (end - Date.parse(e.started_at)) / 1000));
}

export function EventList({ limit = 10, days = 7 }: { limit?: number; days?: number }) {
  const { t } = useTranslation();
  const events = useEvents(days, limit);
  if (!events.data) return null;
  if (!events.data.length) return <Empty>{t("history.noEvents", { days })}</Empty>;
  return (
    <div className="card list">
      {events.data.map((e) => (
        <Link key={e.id} to={e.link || "/"} className="list-row">
          <Dot state={e.ended_at ? "off" : e.level} />
          <span className="list-main">
            <span className="event-text">{issueText(e.text)}</span>
            <span className="list-sub">
              {e.ended_at
                ? t("history.solved", { when: ago(Date.parse(e.started_at) / 1000), duration: duration(e) })
                : t("history.ongoing", { when: ago(Date.parse(e.started_at) / 1000), duration: duration(e) })}
            </span>
          </span>
        </Link>
      ))}
    </div>
  );
}
