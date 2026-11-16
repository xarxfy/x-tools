import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAgents, useServerGroups } from "../api/monitor";
import { useCustomers, useServices } from "../api/data";
import { useEndMaintenance, useJobs, useMaintenance, useStartMaintenance } from "../api/ops";
import { useCan } from "../api/users";
import { Icon } from "./Icon";
import { Dialog } from "./ui";

const DURATIONS = [30, 60, 240, 1440];

export function remaining(until: number): string {
  const min = Math.max(1, Math.round((until - Date.now() / 1000) / 60));
  return min >= 120 ? `${Math.round(min / 60)} h` : `${min} min`;
}

/** Active windows with a button to end each one – shown on the overview. */
export function MaintenanceBanner() {
  const { t } = useTranslation();
  const windows = useMaintenance();
  const end = useEndMaintenance();
  const edit = useCan()("alerts.pause");
  if (!windows.data?.length) return null;
  return (
    <div className="card card-pad maintenance-banner">
      {windows.data.map((w) => (
        <div key={w.id} className="maintenance-row">
          <Icon name="alert" size={16} />
          <span>
            <strong>{t("maintenance.paused", { what: w.label })}</strong>{" "}
            <span className="muted">
              {t("maintenance.remaining", { time: remaining(w.until) })}{w.reason ? ` · ${w.reason}` : ""}
            </span>
          </span>
          <span className="spacer" />
          {edit && (
            <button type="button" className="btn btn-small btn-ghost" disabled={end.isPending} onClick={() => end.mutate(w.id)}>
              {t("maintenance.end")}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

export function PauseDialog({ onClose, initial }: { onClose: () => void; initial?: { scope: string; target: string } }) {
  const { t } = useTranslation();
  const start = useStartMaintenance();
  const agents = useAgents();
  const services = useServices();
  const customers = useCustomers();
  const jobs = useJobs();
  const [scope, setScope] = useState(initial?.scope ?? "all");
  const [target, setTarget] = useState(initial?.target ?? "");
  const groups = useServerGroups();
  const [minutes, setMinutes] = useState(60);
  const [reason, setReason] = useState("");

  const options: Record<string, { id: string; name: string }[]> = {
    agent: (agents.data ?? []).filter((a) => !a.disabled).map((a) => ({ id: a.id, name: a.name })),
    service: (services.data ?? []).map((s) => ({ id: s.id, name: s.name })),
    customer: (customers.data ?? []).map((c) => ({ id: c.id, name: c.name })),
    job: (jobs.data ?? []).map((j) => ({ id: j.id, name: j.name })),
    group: (groups.data ?? []).map((g) => ({ id: g.id, name: g.name })),
    tag: [...new Set((agents.data ?? []).flatMap((a) => a.tags))].sort().map((x) => ({ id: x, name: `#${x}` })),
  };
  const needsTarget = scope in options;
  const list = options[scope] ?? [];

  return (
    <Dialog title={t("maintenance.title")} onClose={onClose}
            onSubmit={() => start.mutate({ scope, target: needsTarget ? target : "", minutes, reason }, { onSuccess: onClose })}
            footer={
              <>
                <span className="spacer" />
                <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
                <button type="submit" className="btn btn-primary" disabled={start.isPending || (needsTarget && !target)}>
                  {t("maintenance.start")}
                </button>
              </>
            }>
      <p className="muted" style={{ marginTop: 0 }}>{t("maintenance.text")}</p>
      <label className="field">
        {t("maintenance.scope")}
        <select className="input" value={scope} onChange={(e) => { setScope(e.target.value); setTarget(""); }}>
          <option value="all">{t("maintenance.scopes.all")}</option>
          <option value="local">{t("maintenance.scopes.local")}</option>
          {Object.keys(options).map((k) => options[k].length > 0 && (
            <option key={k} value={k}>{t(`maintenance.scopes.${k}`)}</option>
          ))}
        </select>
      </label>
      {needsTarget && (
        <label className="field">
          {t("maintenance.target")}
          <select className="input" required value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">–</option>
            {list.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </label>
      )}
      <div className="field">
        {t("maintenance.duration")}
        <div className="chips">
          {DURATIONS.map((m) => (
            <button key={m} type="button" className={`chip chip-button${minutes === m ? " selected" : ""}`} onClick={() => setMinutes(m)}>
              {m >= 60 ? `${m / 60} h` : `${m} min`}
            </button>
          ))}
        </div>
      </div>
      <label className="field">
        {t("maintenance.reason")}
        <input className="input" maxLength={200} value={reason} placeholder={t("maintenance.reasonHint")} onChange={(e) => setReason(e.target.value)} />
      </label>
      {start.error && <p className="error-text">{start.error.message}</p>}
    </Dialog>
  );
}
