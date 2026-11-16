import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useAbout, useFeatures, useNotificationSettings, useSaveFeatures, useSaveNotifications, useTestNotification,
  type NotificationSettings,
} from "../api/monitor";
import { useCheckUpdate, useUpdateInfo } from "../api/ops";
import { Loading } from "../components/ui";
import { ago } from "../components/format";
import "./AdminSettings.css";

const EVENTS = ["port", "container", "docker", "system", "site", "agent", "cloudflare", "job"];

type Form = Omit<NotificationSettings, "telegram" | "ntfy" | "last" | "base_url"> & {
  telegram: { enabled: boolean; chat_id: string; token: string; has_token: boolean; clear_token?: boolean };
  ntfy: { enabled: boolean; server: string; topic: string; token: string; has_token: boolean; clear_token?: boolean };
};

export function Notifications() {
  const { t } = useTranslation();
  const settings = useNotificationSettings();
  const save = useSaveNotifications();
  const test = useTestNotification();
  const [form, setForm] = useState<Form | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (settings.data && !form) {
      const d = settings.data;
      setForm({
        enabled: d.enabled, delay: d.delay, recovery: d.recovery, events: { ...d.events },
        telegram: { enabled: d.telegram.enabled, chat_id: d.telegram.chat_id ?? "", token: "", has_token: d.telegram.has_token },
        ntfy: { enabled: d.ntfy.enabled, server: d.ntfy.server ?? "https://ntfy.sh", topic: d.ntfy.topic ?? "", token: "", has_token: d.ntfy.has_token },
      });
    }
  }, [settings.data, form]);

  if (!settings.data || !form) return <Loading error={settings.error} />;
  const set = (patch: Partial<Form>) => { setForm({ ...form, ...patch }); setSaved(false); };
  const setTg = (patch: Partial<Form["telegram"]>) => set({ telegram: { ...form.telegram, ...patch } });
  const setNt = (patch: Partial<Form["ntfy"]>) => set({ ntfy: { ...form.ntfy, ...patch } });
  const submit = () =>
    save.mutate(form, {
      onSuccess: (d) => {
        setSaved(true);
        setForm({
          ...form,
          telegram: { ...form.telegram, token: "", clear_token: false, has_token: d.telegram.has_token },
          ntfy: { ...form.ntfy, token: "", clear_token: false, has_token: d.ntfy.has_token },
        });
      },
    });
  const last = settings.data.last;
  const d = settings.data;
  const channelOn = d.telegram.enabled || d.ntfy.enabled;

  return (
    <form className="settings" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      {!d.enabled && channelOn && <p className="notice" style={{ marginTop: 0 }}>{t("notify.masterOff")}</p>}
      <section className="card card-pad monitor-status">
        <span>
          {d.monitor_error ? <span className="error-text">{t("notify.monitorError", { error: d.monitor_error })}</span>
            : d.checked_at ? t("notify.monitorOk", { when: ago(d.checked_at) }) : t("notify.monitorWaiting")}
        </span>
        {(d.open?.length ?? 0) > 0 && (
          <ul className="plain-list">
            {d.open!.map((o) => (
              <li key={o.text}>
                <span className={o.sent ? "state-up" : "muted"}>{o.sent ? t("notify.sent") : t("notify.pending")}</span> {o.text}
              </li>
            ))}
          </ul>
        )}
        {(d.manual?.length ?? 0) > 0 && <span className="muted small-note">{t("notify.manual", { names: d.manual!.join(", ") })}</span>}
      </section>
      <section className="card card-pad stack-lg">
        <Toggle checked={form.enabled} onChange={(v) => set({ enabled: v })} label={t("notify.enabled")} hint={t("notify.enabledHint")} />
        <div className="grid-2">
          <label className="field">
            {t("notify.delay")}
            <span className="hint">{t("notify.delayHint")}</span>
            <input className="input" type="number" min={0} max={120} value={form.delay}
                   onChange={(e) => set({ delay: Number(e.target.value) })} />
          </label>
          <div className="field">
            {t("notify.recovery")}
            <Toggle checked={form.recovery} onChange={(v) => set({ recovery: v })} label={t("notify.recoveryHint")} />
          </div>
        </div>
        <div className="field">
          {t("notify.events")}
          <div className="check-list">
            {EVENTS.map((k) => (
              <label key={k}>
                <input type="checkbox" checked={!!form.events[k]} onChange={(e) => set({ events: { ...form.events, [k]: e.target.checked } })} />
                {t(`notify.event.${k}`)}
              </label>
            ))}
          </div>
        </div>
      </section>

      <h2 className="section-title">Telegram</h2>
      <section className="card card-pad stack-lg">
        <Toggle checked={form.telegram.enabled} onChange={(v) => setTg({ enabled: v })} label={t("notify.useTelegram")} />
        <div className="grid-2">
          <label className="field">
            {t("notify.botToken")}
            <span className="hint">{form.telegram.has_token ? t("notify.tokenStored") : t("notify.botTokenHint")}</span>
            <input className="input secret" type="password" autoComplete="off" placeholder={form.telegram.has_token ? "••••••••" : "123456:ABC…"}
                   value={form.telegram.token} onChange={(e) => setTg({ token: e.target.value })} />
          </label>
          <label className="field">
            {t("notify.chatId")}
            <span className="hint">{t("notify.chatIdHint")}</span>
            <input className="input" value={form.telegram.chat_id} onChange={(e) => setTg({ chat_id: e.target.value })} />
          </label>
        </div>
        <ChannelActions channel="telegram" hasToken={form.telegram.has_token} test={test}
                        onClear={() => setTg({ clear_token: true, token: "", has_token: false })} />
      </section>

      <h2 className="section-title">ntfy</h2>
      <section className="card card-pad stack-lg">
        <Toggle checked={form.ntfy.enabled} onChange={(v) => setNt({ enabled: v })} label={t("notify.useNtfy")} />
        <div className="grid-2">
          <label className="field">
            {t("notify.server")}
            <input className="input" value={form.ntfy.server} onChange={(e) => setNt({ server: e.target.value })} />
          </label>
          <label className="field">
            {t("notify.topic")}
            <input className="input" value={form.ntfy.topic} placeholder="my-x-tools-alerts" onChange={(e) => setNt({ topic: e.target.value })} />
          </label>
          <label className="field">
            {t("notify.accessToken")}
            <span className="hint">{form.ntfy.has_token ? t("notify.tokenStored") : t("notify.optional")}</span>
            <input className="input secret" type="password" autoComplete="off" value={form.ntfy.token}
                   onChange={(e) => setNt({ token: e.target.value })} />
          </label>
        </div>
        <ChannelActions channel="ntfy" hasToken={form.ntfy.has_token} test={test}
                        onClear={() => setNt({ clear_token: true, token: "", has_token: false })} />
      </section>

      <div className="save-bar">
        {save.error && <p className="error-text">{save.error.message}</p>}
        {saved && <span className="muted">{t("common.saved")}</span>}
        {last && (
          <span className="muted last-sent">
            {t("notify.last", { when: ago(last.time), title: last.title })}
            {Object.entries(last.results).filter(([, e]) => e).map(([c, e]) => ` · ${c}: ${e}`).join("")}
          </span>
        )}
        <span className="spacer" />
        <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button>
      </div>
      {!settings.data.base_url && <p className="muted small-note">{t("notify.noBaseUrl")}</p>}
    </form>
  );
}

function ChannelActions({ channel, hasToken, test, onClear }: {
  channel: "telegram" | "ntfy";
  hasToken: boolean;
  test: ReturnType<typeof useTestNotification>;
  onClear: () => void;
}) {
  const { t } = useTranslation();
  const mine = test.variables === channel;
  return (
    <div className="channel-actions">
      <button type="button" className="btn" disabled={test.isPending} onClick={() => test.mutate(channel)}>
        {t("notify.test")}
      </button>
      {hasToken && <button type="button" className="btn btn-ghost" onClick={onClear}>{t("notify.removeToken")}</button>}
      {mine && test.isSuccess && <span className="state-up">{t("notify.testSent")}</span>}
      {mine && test.error && <span className="error-text">{test.error.message}</span>}
      <span className="muted small-note">{t("notify.testHint")}</span>
    </div>
  );
}

export function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
  return (
    <label className="toggle">
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch" aria-hidden="true" />
      <span>
        <span className="toggle-label">{label}</span>
        {hint && <span className="toggle-hint">{hint}</span>}
      </span>
    </label>
  );
}

function General() {
  const { t } = useTranslation();
  const features = useFeatures();
  const save = useSaveFeatures();
  if (!features.data) return <Loading error={features.error} />;
  return (
    <section className="card card-pad stack-lg" style={{ marginTop: 16 }}>
      <Toggle checked={features.data.customers} label={t("general.customers")} hint={t("general.customersHint")}
              onChange={(v) => save.mutate({ ...features.data!, customers: v })} />
      {save.error && <p className="error-text">{save.error.message}</p>}
    </section>
  );
}

function About() {
  const { t } = useTranslation();
  const about = useAbout();
  const update = useUpdateInfo();
  const check = useCheckUpdate();
  if (!about.data) return <Loading error={about.error} />;
  const a = about.data;
  const u = update.data;
  const rows: [string, React.ReactNode][] = [
    [t("about.version"), a.version],
    [t("update.title"), !u ? "…" : !u.enabled ? <span className="muted">{t("update.off")}</span> : (
      <span className="update-row">
        {u.available ? <span className="state-warn">{t("update.available", { version: u.latest })}</span>
          : u.latest ? <span className="state-up">{t("update.current")}</span> : <span className="muted">{t("update.unknown")}</span>}
        {u.checked_at && <span className="muted small-note"> · {t("update.checked", { when: ago(u.checked_at) })}</span>}
        <button type="button" className="btn btn-ghost btn-small" disabled={check.isPending} onClick={() => check.mutate()}>{t("update.check")}</button>
        {u.error && <span className="error-text small-note">{u.error}</span>}
        {check.error && <span className="error-text small-note">{check.error.message}</span>}
        {u.available && <span className="small-note">{t("update.how")} <code>sudo x-tools-ctl update</code></span>}
      </span>
    )],
    [t("about.baseUrl"), a.base_url || <span className="muted">{t("about.notSet")}</span>],
    [t("about.timezone"), a.timezone],
    [t("about.dataDir"), <code>{a.data_dir}</code>],
    [t("about.composeRoots"), a.compose_roots.map((r) => <code key={r}>{r} </code>)],
    [t("about.protected"), a.protected.join(", ")],
    [t("about.collector"), a.collector_seen ? ago(a.collector_seen) : <span className="muted">{t("about.never")}</span>],
  ];
  return (
    <>
      <section className="card card-pad" style={{ marginTop: 16 }}>
        <dl className="details">
          {rows.map(([k, v]) => (<div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{v}</dd></div>))}
        </dl>
      </section>
      <section className="card card-pad vibe-note" style={{ marginTop: 16 }}>
        <strong>{t("about.vibeTitle")}</strong>
        <p style={{ margin: "6px 0 0" }}>{t("about.vibeText")}</p>
      </section>
      <h2 className="section-title">{t("about.backupTitle")}</h2>
      <section className="card card-pad">
        <p style={{ marginTop: 0 }}>{a.secret_key_from_env ? t("about.keyEnv") : t("about.keyFile", { dir: a.data_dir })}</p>
        <p className="muted" style={{ marginBottom: 0 }}>{t("about.backupHint")}</p>
      </section>
      <p className="muted small-note">{t("about.config")}</p>
    </>
  );
}

/** Administration → System: switches (customers area), version and update, the instance's settings. */
export function SystemSettings() {
  return (
    <>
      <General />
      <About />
    </>
  );
}
