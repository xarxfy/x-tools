import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  agentAge, AGENT_STALE, useAbout, useAgents, useCreateAgent, useDeleteAgent, useNotificationSettings,
  useSaveNotifications, useTestNotification, useUpdateAgent, type NotificationSettings,
} from "../api/monitor";
import { Icon } from "../components/Icon";
import { ConfirmDelete, CopyButton, Dialog, Dot, Empty, Loading, PageHead } from "../components/ui";
import { ago } from "../components/format";
import "./SettingsPage.css";

const TABS = ["notifications", "agents", "about"] as const;
const EVENTS = ["port", "container", "docker", "system", "site", "agent"];

export function SettingsPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((k) => k === params.get("tab")) ?? "notifications";
  return (
    <>
      <PageHead title={t("nav.settings")} />
      <div className="tabs" role="tablist">
        {TABS.map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""}
                  onClick={() => setParams(k === "notifications" ? {} : { tab: k })}>
            {t(`settings.tab.${k}`)}
          </button>
        ))}
      </div>
      {tab === "notifications" ? <Notifications /> : tab === "agents" ? <Agents /> : <About />}
    </>
  );
}

type Form = Omit<NotificationSettings, "telegram" | "ntfy" | "last" | "base_url"> & {
  telegram: { enabled: boolean; chat_id: string; token: string; has_token: boolean; clear_token?: boolean };
  ntfy: { enabled: boolean; server: string; topic: string; token: string; has_token: boolean; clear_token?: boolean };
};

function Notifications() {
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

  return (
    <form className="settings" onSubmit={(e) => { e.preventDefault(); submit(); }}>
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

function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string }) {
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

function Agents() {
  const { t } = useTranslation();
  const agents = useAgents();
  const create = useCreateAgent();
  const update = useUpdateAgent();
  const remove = useDeleteAgent();
  const [name, setName] = useState("");
  const [created, setCreated] = useState<{ name: string; key: string } | null>(null);
  if (!agents.data) return <Loading error={agents.error} />;

  return (
    <>
      <p className="muted intro">{t("agents.intro")}</p>
      <form className="card card-pad add-agent" onSubmit={(e) => {
        e.preventDefault();
        create.mutate(name, { onSuccess: (a) => { setCreated({ name: a.name, key: a.key }); setName(""); } });
      }}>
        <label className="field" style={{ flex: 1 }}>
          {t("agents.name")}
          <input className="input" required maxLength={60} placeholder={t("agents.namePlaceholder")} value={name}
                 onChange={(e) => setName(e.target.value)} />
        </label>
        <button type="submit" className="btn btn-primary" disabled={create.isPending}>
          <Icon name="plus" size={16} />
          {t("agents.create")}
        </button>
        {create.error && <p className="error-text" style={{ flexBasis: "100%" }}>{create.error.message}</p>}
      </form>

      {agents.data.length === 0 ? (
        <Empty>{t("agents.none")}</Empty>
      ) : (
        <div className="card list" style={{ marginTop: 16 }}>
          {agents.data.map((a) => {
            const age = agentAge(a);
            const st = a.disabled ? "off" : age === null ? "warn" : age < AGENT_STALE ? "up" : "down";
            return (
              <div key={a.id} className="list-row static-row">
                <Dot state={st} />
                <div className="list-main">
                  <div className="list-title">
                    <Link to={`/servers/${a.id}`}>{a.name}</Link>
                    {a.disabled && <span className="badge">{t("agents.disabled")}</span>}
                  </div>
                  <div className="list-sub">
                    {[a.hostname, age === null ? t("servers.neverReported") : t("servers.reported", { when: ago(Date.now() / 1000 - age) }),
                      a.version && t("agents.version", { version: a.version })].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <div className="list-side">
                  <button type="button" className="btn btn-small" onClick={() => update.mutate({ id: a.id, disabled: !a.disabled })}>
                    {a.disabled ? t("agents.enable") : t("agents.disable")}
                  </button>
                  <ConfirmDelete onConfirm={() => remove.mutate(a.id)} busy={remove.isPending} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {created && <AgentSetup agent={created} onClose={() => setCreated(null)} />}
    </>
  );
}

function AgentSetup({ agent, onClose }: { agent: { name: string; key: string }; onClose: () => void }) {
  const { t } = useTranslation();
  const about = useAbout();
  const base = about.data?.base_url || window.location.origin;
  const env = `XT_AGENT_URL=${base}\nXT_AGENT_KEY=${agent.key}\nCF_ACCESS_CLIENT_ID=\nCF_ACCESS_CLIENT_SECRET=\nXT_TIMEZONE=${about.data?.timezone ?? "UTC"}\n`;
  return (
    <Dialog wide title={t("agents.createdTitle", { name: agent.name })} onClose={onClose}
            footer={<><span className="spacer" /><button type="button" className="btn btn-primary" onClick={onClose}>{t("common.done")}</button></>}>
      <p className="notice" style={{ margin: 0 }}>{t("agents.keyOnce")}</p>
      <div className="field">
        {t("agents.key")}
        <div className="key-row">
          <code className="secret">{agent.key}</code>
          <CopyButton value={agent.key} label={t("common.copy")} />
        </div>
      </div>
      <div className="field">
        {t("agents.steps")}
        <ol className="steps">
          <li>{t("agents.step1")} <code>git clone … x-tools &amp;&amp; cd x-tools/deploy/agent</code></li>
          <li>{t("agents.step2")}</li>
        </ol>
        <div className="key-row">
          <pre className="code" style={{ flex: 1 }}>{env}</pre>
          <CopyButton value={env} label={t("common.copy")} />
        </div>
        <ol className="steps" start={3}>
          <li>{t("agents.step3")} <code>docker compose up -d --build</code></li>
          <li>{t("agents.step4")}</li>
        </ol>
      </div>
    </Dialog>
  );
}

function About() {
  const { t } = useTranslation();
  const about = useAbout();
  if (!about.data) return <Loading error={about.error} />;
  const a = about.data;
  const rows: [string, React.ReactNode][] = [
    [t("about.version"), a.version],
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
      <h2 className="section-title">{t("about.backupTitle")}</h2>
      <section className="card card-pad">
        <p style={{ marginTop: 0 }}>{a.secret_key_from_env ? t("about.keyEnv") : t("about.keyFile", { dir: a.data_dir })}</p>
        <p className="muted" style={{ marginBottom: 0 }}>{t("about.backupHint")}</p>
      </section>
      <p className="muted small-note">{t("about.config")}</p>
    </>
  );
}
