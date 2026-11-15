import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAutoBackup, useRunAutoBackup, useSaveAutoBackup, type AutoBackup, type BackupLocation } from "../api/ops";
import { ago } from "../components/format";
import { Icon } from "../components/Icon";
import { Loading } from "../components/ui";
import { Toggle } from "./SettingsPage";

const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];

export function AutoBackupSettings() {
  const { t } = useTranslation();
  const q = useAutoBackup();
  const save = useSaveAutoBackup();
  const run = useRunAutoBackup();
  const [form, setForm] = useState<AutoBackup | null>(null);
  const [passphrase, setPassphrase] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => { if (q.data && !form) setForm(q.data); }, [q.data, form]);
  if (!q.data || !form) return <Loading error={q.error} />;

  const set = (patch: Partial<AutoBackup>) => { setSaved(false); setForm({ ...form, ...patch }); };
  const setLoc = (i: number, patch: Partial<BackupLocation>) =>
    set({ locations: form.locations.map((l, j) => (j === i ? { ...l, ...patch } : l)) });
  const addLoc = (type: "folder" | "webdav") =>
    set({ locations: [...form.locations, { name: type === "folder" ? t("autobackup.folder") : "WebDAV", type, path: type === "folder" ? q.data!.default_folder : "", url: "", username: "" }] });
  const last = q.data.last;

  const submit = () => save.mutate(
    { enabled: form.enabled, frequency: form.frequency, time: form.time, weekday: form.weekday, keep: form.keep,
      passphrase: passphrase || undefined,
      locations: form.locations.map(({ has_password, ...l }) => ({ ...l, has_password })) },
    { onSuccess: (data) => { setForm(data); setPassphrase(""); setSaved(true); } },
  );

  return (
    <>
      <h2 className="section-title">{t("autobackup.title")}</h2>
      <form className="card card-pad stack-lg" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Toggle checked={form.enabled} label={t("autobackup.enable")} hint={t("autobackup.enableHint")} onChange={(enabled) => set({ enabled })} />

        <div className="grid-2">
          <label className="field">
            {t("autobackup.frequency")}
            <select className="input" value={form.frequency} onChange={(e) => set({ frequency: e.target.value as "daily" | "weekly" })}>
              <option value="daily">{t("autobackup.daily")}</option>
              <option value="weekly">{t("autobackup.weekly")}</option>
            </select>
          </label>
          <label className="field">
            {t("autobackup.time")}
            <input className="input" type="time" required value={form.time} onChange={(e) => set({ time: e.target.value })} />
          </label>
          {form.frequency === "weekly" && (
            <label className="field">
              {t("autobackup.weekday")}
              <select className="input" value={form.weekday} onChange={(e) => set({ weekday: Number(e.target.value) })}>
                {WEEKDAYS.map((d) => <option key={d} value={d}>{t(`autobackup.days.${d}`)}</option>)}
              </select>
            </label>
          )}
          <label className="field">
            {t("autobackup.keep")}
            <span className="hint">{t("autobackup.keepHint")}</span>
            <input className="input" type="number" min={1} max={365} value={form.keep} onChange={(e) => set({ keep: Number(e.target.value) })} />
          </label>
        </div>

        <label className="field">
          {t("backup.passphrase")}
          <span className="hint">{form.has_passphrase ? t("autobackup.passphraseSaved") : t("autobackup.passphraseHint")}</span>
          <input className="input" type="password" autoComplete="new-password" minLength={10} value={passphrase}
                 placeholder={form.has_passphrase ? "••••••••••" : ""} required={form.enabled && !form.has_passphrase}
                 onChange={(e) => { setPassphrase(e.target.value); setSaved(false); }} />
        </label>

        <div className="field">
          {t("autobackup.locations")}
          <span className="hint">{t("autobackup.locationsHint")}</span>
          {form.locations.map((l, i) => (
            <div key={l.id ?? i} className="card-pad backup-loc">
              <div className="grid-2">
                <label className="field">
                  {t("autobackup.name")}
                  <input className="input" required maxLength={60} value={l.name} onChange={(e) => setLoc(i, { name: e.target.value })} />
                </label>
                {l.type === "folder" ? (
                  <label className="field">
                    {t("autobackup.path")}
                    <input className="input" required value={l.path} onChange={(e) => setLoc(i, { path: e.target.value })} />
                  </label>
                ) : (
                  <label className="field">
                    {t("autobackup.url")}
                    <input className="input" required placeholder="https://cloud.example.com/remote.php/dav/files/me/backups"
                           value={l.url} onChange={(e) => setLoc(i, { url: e.target.value })} />
                  </label>
                )}
              </div>
              {l.type === "webdav" && (
                <div className="grid-2">
                  <label className="field">
                    {t("autobackup.user")}
                    <input className="input" autoComplete="off" value={l.username} onChange={(e) => setLoc(i, { username: e.target.value })} />
                  </label>
                  <label className="field">
                    {t("autobackup.password")}
                    <input className="input" type="password" autoComplete="new-password" value={l.password ?? ""}
                           placeholder={l.has_password && l.password === undefined ? t("deploy.tokenSaved") : ""}
                           onChange={(e) => setLoc(i, { password: e.target.value })} />
                  </label>
                </div>
              )}
              <button type="button" className="btn btn-ghost btn-small" onClick={() => set({ locations: form.locations.filter((_, j) => j !== i) })}>
                {t("autobackup.remove")}
              </button>
            </div>
          ))}
          {form.locations.length < 5 && (
            <div className="channel-actions">
              <button type="button" className="btn btn-ghost btn-small" onClick={() => addLoc("folder")}><Icon name="plus" size={14} />{t("autobackup.addFolder")}</button>
              <button type="button" className="btn btn-ghost btn-small" onClick={() => addLoc("webdav")}><Icon name="plus" size={14} />{t("autobackup.addWebdav")}</button>
            </div>
          )}
        </div>

        <div className="channel-actions">
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button>
          <button type="button" className="btn" disabled={run.isPending || !q.data.has_passphrase || q.data.locations.length === 0}
                  onClick={() => run.mutate()}>
            {run.isPending ? t("autobackup.running") : t("autobackup.runNow")}
          </button>
          {saved && <span className="state-up">{t("autobackup.saved")}</span>}
          {(save.error || run.error) && <span className="error-text">{(save.error ?? run.error)!.message}</span>}
        </div>

        {last && (
          <div className="backup-last">
            <strong className={last.ok ? "state-up" : "error-text"}>
              {last.ok ? t("autobackup.lastOk", { when: ago(last.at) }) : t("autobackup.lastFailed", { when: ago(last.at) })}
            </strong>
            <ul className="plain-list">
              {last.results.map((r, i) => (
                <li key={i} className={r.ok ? "" : "error-text"}>{r.name}: {r.ok ? t("autobackup.written") : r.error}</li>
              ))}
            </ul>
          </div>
        )}
      </form>
    </>
  );
}
