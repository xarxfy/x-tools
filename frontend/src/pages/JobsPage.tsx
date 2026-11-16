import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDeleteJob, useJobs, useNewJobToken, useSaveJob, type Job } from "../api/ops";
import { useCan } from "../api/users";
import { ago } from "../components/format";
import { Icon } from "../components/Icon";
import { ConfirmDelete, CopyButton, Dialog, Dot, Empty, Loading, PageHead } from "../components/ui";

const DOT = { paused: "off", waiting: "warn", ok: "up", late: "down", fail: "down" } as const;
const UNITS = [["minutes", 1], ["hours", 60], ["days", 1440]] as const;

function every(minutes: number): string {
  for (const [name, factor] of [["d", 1440], ["h", 60]] as const) if (minutes % factor === 0) return `${minutes / factor} ${name}`;
  return `${minutes} min`;
}

export const pingUrl = (token: string) => `${window.location.origin}/api/heartbeat/${token}`;

export function JobsPage() {
  const { t } = useTranslation();
  const jobs = useJobs();
  const edit = useCan()("jobs.edit");
  const [dialog, setDialog] = useState<Job | "new" | null>(null);
  const [howto, setHowto] = useState<Job | null>(null);
  if (!jobs.data) return <Loading error={jobs.error} retry={() => jobs.refetch()} />;
  const list = jobs.data;
  return (
    <>
      <PageHead title={t("nav.jobs")} sub={list.length ? t("jobs.sub", { count: list.length }) : undefined}>
        {edit && (
          <button type="button" className="btn btn-primary" onClick={() => setDialog("new")}>
            <Icon name="plus" size={16} />{t("jobs.add")}
          </button>
        )}
      </PageHead>
      {list.length === 0 ? (
        <Empty>{t("jobs.empty")}</Empty>
      ) : (
        <div className="card list">
          {list.map((j) => (
            <div key={j.id} className="list-row static-row">
              <Dot state={DOT[j.state]} />
              <div className="list-main">
                <div className="list-title">
                  {j.name}
                  <span className={`state-text state-${DOT[j.state] === "off" ? "off" : DOT[j.state]}`}>{t(`jobs.state.${j.state}`)}</span>
                </div>
                <div className="list-sub">
                  {[
                    t("jobs.every", { interval: every(j.interval_minutes) }),
                    j.last_ok_at ? t("jobs.lastOk", { when: ago(Date.parse(j.last_ok_at) / 1000) }) : t("jobs.neverReported"),
                  ].join(" · ")}
                </div>
              </div>
              {edit && (
                <div className="deploy-actions">
                  <button type="button" className="btn btn-ghost btn-small" onClick={() => setHowto(j)}>{t("jobs.address")}</button>
                  <button type="button" className="btn btn-ghost btn-icon" aria-label={t("common.edit")} title={t("common.edit")}
                          onClick={() => setDialog(j)}><Icon name="edit" size={16} /></button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {dialog && <JobDialog job={dialog === "new" ? null : dialog} onClose={() => setDialog(null)}
                            onCreated={(j) => setHowto(j)} />}
      {howto && <HowtoDialog job={list.find((j) => j.id === howto.id) ?? howto} onClose={() => setHowto(null)} />}
    </>
  );
}

function JobDialog({ job, onClose, onCreated }: { job: Job | null; onClose: () => void; onCreated: (j: Job) => void }) {
  const { t } = useTranslation();
  const save = useSaveJob();
  const remove = useDeleteJob();
  const initial = job?.interval_minutes ?? 1440;
  const unit = [...UNITS].reverse().find(([, f]) => initial % f === 0) ?? UNITS[0];
  const [name, setName] = useState(job?.name ?? "");
  const [amount, setAmount] = useState(String(initial / unit[1]));
  const [factor, setFactor] = useState<number>(unit[1]);
  const [grace, setGrace] = useState(String(job?.grace_minutes ?? 30));
  const [paused, setPaused] = useState(job?.paused ?? false);
  return (
    <Dialog title={job ? t("jobs.edit") : t("jobs.add")} onClose={onClose}
            onSubmit={() => save.mutate(
              { id: job?.id, body: { name, interval_minutes: Math.max(1, Math.round(Number(amount) * factor)), grace_minutes: Number(grace) || 0, paused } },
              { onSuccess: (j) => { onClose(); if (!job) onCreated(j); } })}
            footer={
              <>
                {job && <ConfirmDelete busy={remove.isPending} onConfirm={() => remove.mutate(job.id, { onSuccess: onClose })} />}
                <span className="spacer" />
                <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
                <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button>
              </>
            }>
      <label className="field">
        {t("jobs.name")}
        <input className="input" required maxLength={80} autoFocus value={name} placeholder={t("jobs.nameHint")} onChange={(e) => setName(e.target.value)} />
      </label>
      <div className="field">
        {t("jobs.expected")}
        <span className="hint">{t("jobs.expectedHint")}</span>
        <div className="grid-2">
          <input className="input" type="number" min={1} required value={amount} onChange={(e) => setAmount(e.target.value)} />
          <select className="input" value={factor} onChange={(e) => setFactor(Number(e.target.value))}>
            {UNITS.map(([n, f]) => <option key={n} value={f}>{t(`jobs.units.${n}`)}</option>)}
          </select>
        </div>
      </div>
      <label className="field">
        {t("jobs.grace")}
        <span className="hint">{t("jobs.graceHint")}</span>
        <input className="input" type="number" min={0} value={grace} onChange={(e) => setGrace(e.target.value)} />
      </label>
      {job && (
        <label className="inline-check">
          <input type="checkbox" checked={paused} onChange={(e) => setPaused(e.target.checked)} />
          {t("jobs.pause")}
        </label>
      )}
      {save.error && <p className="error-text">{save.error.message}</p>}
      {remove.error && <p className="error-text">{remove.error.message}</p>}
    </Dialog>
  );
}

function HowtoDialog({ job, onClose }: { job: Job; onClose: () => void }) {
  const { t } = useTranslation();
  const newToken = useNewJobToken();
  const [confirm, setConfirm] = useState(false);
  if (!job.token) return null;
  const url = pingUrl(job.token);
  const lines = [
    [t("jobs.howtoSimple"), `curl -fsS -m 10 --retry 3 ${url}`],
    [t("jobs.howtoCron"), `0 3 * * *  /path/backup.sh && curl -fsS -m 10 --retry 3 ${url} || curl -fsS -m 10 ${url}/fail`],
  ];
  return (
    <Dialog wide title={`${job.name} – ${t("jobs.address")}`} onClose={onClose}
            footer={<>
              {confirm ? (
                <>
                  <span className="muted small-note">{t("jobs.newTokenConfirm")}</span>
                  <button type="button" className="btn btn-small btn-danger" onClick={() => newToken.mutate(job.id, { onSuccess: () => setConfirm(false) })}>{t("proxmox.yes")}</button>
                  <button type="button" className="btn btn-small btn-ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</button>
                </>
              ) : <button type="button" className="btn btn-ghost btn-small" onClick={() => setConfirm(true)}>{t("jobs.newToken")}</button>}
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.close")}</button>
            </>}>
      <p className="muted" style={{ marginTop: 0 }}>{t("jobs.howto")}</p>
      <div className="field">
        {t("jobs.pingUrl")}
        <div className="file-block"><div className="file-head"><code style={{ overflowWrap: "anywhere" }}>{url}</code><span className="spacer" /><CopyButton value={url} label={t("common.copy")} /></div></div>
      </div>
      {lines.map(([label, cmd]) => (
        <div key={label} className="field">
          {label}
          <div className="file-block"><div className="file-head"><code style={{ overflowWrap: "anywhere" }}>{cmd}</code><span className="spacer" /><CopyButton value={cmd} label={t("common.copy")} /></div></div>
        </div>
      ))}
      <p className="muted small-note">{t("jobs.accessHint")}</p>
    </Dialog>
  );
}
