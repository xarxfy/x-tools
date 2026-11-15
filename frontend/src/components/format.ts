/** Formatting helpers for sizes, durations and relative times. */
import i18n from "../i18n";

export function fmtBytes(n?: number): string {
  if (n === undefined || n === null) return "–";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v >= 10 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`;
}

export function fmtDuration(seconds?: number): string {
  if (!seconds) return "–";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d} d ${h} h`;
  if (h) return `${h} h ${m} min`;
  return `${m} min`;
}

export function ago(ts?: number): string {
  const t = i18n.t.bind(i18n);
  if (!ts) return t("format.never");
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return t("format.justNow");
  if (s < 3600) return t("format.minAgo", { count: Math.round(s / 60) });
  if (s < 86400) return t("format.hAgo", { count: Math.round(s / 3600) });
  return t("format.daysAgo", { count: Math.round(s / 86400) });
}

export function pct(used?: number, total?: number): number {
  return used !== undefined && total ? (used / total) * 100 : 0;
}

export function level(p: number): "up" | "warn" | "down" {
  return p >= 90 ? "down" : p >= 80 ? "warn" : "up";
}
