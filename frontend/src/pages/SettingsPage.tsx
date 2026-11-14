import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  agentAge, AGENT_STALE, useAbout, useAgents, useCreateAgent, useDeleteAgent, useFeatures, useNewInstall,
  useNotificationSettings, useSaveFeatures, useSaveNotifications, useTestNotification, useUpdateAgent,
  type AgentKind, type AgentSummary, type InstallInfo, type InstallOptions, type NotificationSettings,
} from "../api/monitor";
import { Icon } from "../components/Icon";
import { ConfirmDelete, CopyButton, Dialog, Dot, Empty, Loading, PageHead } from "../components/ui";
import { ago } from "../components/format";
import "./SettingsPage.css";

const TABS = ["general", "notifications", "agents", "about"] as const;
const EVENTS = ["port", "container", "docker", "system", "site", "agent"];

export function SettingsPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((k) => k === params.get("tab")) ?? "general";
  return (
    <>
      <PageHead title={t("nav.settings")} />
      <div className="tabs" role="tablist">
        {TABS.map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""}
                  onClick={() => setParams(k === "general" ? {} : { tab: k })}>
            {t(`settings.tab.${k}`)}
          </button>
        ))}
      </div>
      {tab === "general" ? <General /> : tab === "notifications" ? <Notifications />
        : tab === "agents" ? <Agents /> : <About />}
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

/** Removes the agent from the target system – systemd installation and Docker variant. Contains no secrets. */
const UNINSTALL =
  "systemctl disable --now x-tools-agent 2>/dev/null; " +
  "rm -rf /opt/x-tools-agent /etc/x-tools-agent /etc/systemd/system/x-tools-agent.service; " +
  "systemctl daemon-reload 2>/dev/null; docker rm -f x-tools-agent 2>/dev/null; echo 'X-TOOLS agent removed'";

const NO_INSTALL: InstallOptions = {
  kind: "docker", proxmox_url: "https://127.0.0.1:8006", proxmox_token_id: "", proxmox_token_secret: "",
  proxmox_verify_tls: false, cf_client_id: "", cf_client_secret: "", compose_roots: "/opt,/srv,/home,/root",
};

/** Proxmox host or Docker host – decides what the agent reports. */
function KindPicker({ value, onChange }: { value: AgentKind; onChange: (k: AgentKind) => void }) {
  const { t } = useTranslation();
  return (
    <div className="kind-picker" role="radiogroup" aria-label={t("agents.kind")}>
      {(["proxmox", "docker"] as const).map((k) => (
        <button key={k} type="button" role="radio" aria-checked={value === k}
                className={`kind-option${value === k ? " selected" : ""}`} onClick={() => onChange(k)}>
          <Icon name={k === "proxmox" ? "servers" : "docker"} size={22} />
          <strong>{t(`agents.kinds.${k}`)}</strong>
          <span>{t(`agents.kinds.${k}Hint`)}</span>
        </button>
      ))}
    </div>
  );
}

/** Values for the install command: Proxmox API token (Proxmox hosts), Cloudflare service token, folders. */
function InstallFields({ value, onChange }: { value: InstallOptions; onChange: (v: InstallOptions) => void }) {
  const { t } = useTranslation();
  const [cf, setCf] = useState(!!value.cf_client_id);
  const [more, setMore] = useState(false);
  const set = (patch: Partial<InstallOptions>) => onChange({ ...value, ...patch });
  return (
    <>
      <KindPicker value={value.kind} onChange={(kind) => set({ kind })} />
      {value.kind === "proxmox" && (
        <div className="stack-md">
          <div className="grid-2">
            <label className="field">
              {t("agents.proxmoxUrl")}
              <span className="hint">{t("agents.proxmoxUrlHint")}</span>
              <input className="input" required value={value.proxmox_url} onChange={(e) => set({ proxmox_url: e.target.value })} />
            </label>
            <label className="field">
              {t("agents.tokenId")}
              <span className="hint">{t("agents.tokenIdHint")}</span>
              <input className="input" required placeholder="root@pam!xtools" value={value.proxmox_token_id}
                     onChange={(e) => set({ proxmox_token_id: e.target.value })} />
            </label>
          </div>
          <label className="field">
            {t("agents.tokenSecret")}
            <input className="input secret" required type="password" autoComplete="off" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                   value={value.proxmox_token_secret} onChange={(e) => set({ proxmox_token_secret: e.target.value })} />
          </label>
          <label className="inline-check">
            <input type="checkbox" checked={value.proxmox_verify_tls} onChange={(e) => set({ proxmox_verify_tls: e.target.checked })} />
            {t("agents.verifyTls")}
          </label>
          <p className="muted small-note" style={{ margin: 0 }}>{t("agents.proxmoxHowto")}</p>
        </div>
      )}
      <Toggle checked={cf} label={t("agents.cf")} hint={t("agents.cfHint")}
              onChange={(v) => { setCf(v); if (!v) set({ cf_client_id: "", cf_client_secret: "" }); }} />
      {cf && (
        <div className="sub-fields grid-2">
          <label className="field">
            {t("agents.cfId")}
            <input className="input" required value={value.cf_client_id} onChange={(e) => set({ cf_client_id: e.target.value })} />
          </label>
          <label className="field">
            {t("agents.cfSecret")}
            <input className="input secret" required type="password" autoComplete="off" value={value.cf_client_secret}
                   onChange={(e) => set({ cf_client_secret: e.target.value })} />
          </label>
        </div>
      )}
      {value.kind === "docker" && (
        <>
          <button type="button" className="btn btn-ghost add-link" onClick={() => setMore((m) => !m)}>
            {more ? t("agents.lessOptions") : t("agents.moreOptions")}
          </button>
          {more && (
            <label className="field">
              {t("agents.composeRoots")}
              <span className="hint">{t("agents.composeRootsHint")}</span>
              <input className="input" value={value.compose_roots} onChange={(e) => set({ compose_roots: e.target.value })} />
            </label>
          )}
        </>
      )}
    </>
  );
}

function Agents() {
  const { t } = useTranslation();
  const agents = useAgents();
  const update = useUpdateAgent();
  const remove = useDeleteAgent();
  const [creating, setCreating] = useState(false);
  const [reinstall, setReinstall] = useState<AgentSummary | null>(null);
  const [renaming, setRenaming] = useState<AgentSummary | null>(null);
  const [removed, setRemoved] = useState<AgentSummary | null>(null);
  const [result, setResult] = useState<{ name: string; key: string; install: InstallInfo } | null>(null);
  if (!agents.data) return <Loading error={agents.error} />;

  const row = (a: AgentSummary) => {
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
          <button type="button" className="btn btn-ghost btn-icon" title={t("agents.rename")} aria-label={t("agents.rename")}
                  onClick={() => setRenaming(a)}>
            <Icon name="edit" size={15} />
          </button>
          <button type="button" className="btn btn-small" onClick={() => setReinstall(a)}>{t("agents.installCommand")}</button>
          <button type="button" className="btn btn-small" onClick={() => update.mutate({ id: a.id, disabled: !a.disabled })}>
            {a.disabled ? t("agents.enable") : t("agents.disable")}
          </button>
          <ConfirmDelete onConfirm={() => remove.mutate(a.id, { onSuccess: () => setRemoved(a) })} busy={remove.isPending} />
        </div>
      </div>
    );
  };

  return (
    <>
      <div className="section-row">
        <p className="muted intro">{t("agents.intro")}</p>
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
          <Icon name="plus" size={16} />
          {t("agents.create")}
        </button>
      </div>

      {agents.data.length === 0 ? (
        <Empty>{t("agents.none")}</Empty>
      ) : (
        (["proxmox", "docker"] as const).map((kind) => {
          const list = agents.data.filter((a) => a.kind === kind);
          return list.length > 0 && (
            <section key={kind}>
              <h2 className="section-title">{t(`agents.groups.${kind}`)}</h2>
              <div className="card list">{list.map(row)}</div>
            </section>
          );
        })
      )}

      {creating && <CreateAgentDialog onClose={() => setCreating(false)} onCreated={(r) => { setCreating(false); setResult(r); }} />}
      {reinstall && (
        <ReinstallDialog agent={reinstall} onClose={() => setReinstall(null)}
                         onCreated={(r) => { setReinstall(null); setResult(r); }} />
      )}
      {renaming && <RenameDialog agent={renaming} onClose={() => setRenaming(null)} />}
      {removed && <UninstallDialog agent={removed} onClose={() => setRemoved(null)} />}
      {result && <InstallDialog result={result} onClose={() => setResult(null)} />}
    </>
  );
}

function UninstallDialog({ agent, onClose }: { agent: AgentSummary; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <Dialog wide title={t("agents.removedTitle", { name: agent.name })} onClose={onClose}
            footer={<><span className="spacer" /><button type="button" className="btn btn-primary" onClick={onClose}>{t("common.done")}</button></>}>
      <p style={{ margin: 0 }}>{t("agents.removedText", { host: agent.hostname || agent.name })}</p>
      <div className="field">
        {t("agents.uninstallRun")}
        <span className="hint">{t("agents.uninstallHint")}</span>
        <div className="key-row">
          <pre className="code command">{UNINSTALL}</pre>
          <CopyButton value={UNINSTALL} label={t("common.copy")} />
        </div>
      </div>
      <p className="muted small-note" style={{ margin: 0 }}>{t("agents.uninstallNote")}</p>
    </Dialog>
  );
}

function RenameDialog({ agent, onClose }: { agent: AgentSummary; onClose: () => void }) {
  const { t } = useTranslation();
  const update = useUpdateAgent();
  const [name, setName] = useState(agent.name);
  return (
    <Dialog title={t("agents.rename")} onClose={onClose}
            onSubmit={() => update.mutate({ id: agent.id, name }, { onSuccess: onClose })}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={update.isPending}>{t("common.save")}</button>
            </>}>
      <label className="field">
        {t("agents.name")}
        <input className="input" required autoFocus maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {update.error && <p className="error-text">{update.error.message}</p>}
    </Dialog>
  );
}

type InstallResult = { name: string; key: string; install: InstallInfo };

function CreateAgentDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (r: InstallResult) => void }) {
  const { t } = useTranslation();
  const create = useCreateAgent();
  const [name, setName] = useState("");
  const [opts, setOpts] = useState<InstallOptions>(NO_INSTALL);
  return (
    <Dialog wide title={t("agents.createTitle")} onClose={onClose}
            onSubmit={() => create.mutate({ name, ...opts }, { onSuccess: (a) => onCreated({ name: a.name, key: a.key, install: a.install }) })}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={create.isPending}>{t("agents.createAndInstall")}</button>
            </>}>
      <label className="field">
        {t("agents.name")}
        <input className="input" required autoFocus maxLength={60} placeholder={t("agents.namePlaceholder")} value={name}
               onChange={(e) => setName(e.target.value)} />
      </label>
      <InstallFields value={opts} onChange={setOpts} />
      {create.error && <p className="error-text">{create.error.message}</p>}
    </Dialog>
  );
}

function ReinstallDialog({ agent, onClose, onCreated }: {
  agent: AgentSummary;
  onClose: () => void;
  onCreated: (r: InstallResult) => void;
}) {
  const { t } = useTranslation();
  const install = useNewInstall();
  const [opts, setOpts] = useState<InstallOptions>({ ...NO_INSTALL, kind: agent.kind });
  return (
    <Dialog wide title={t("agents.reinstallTitle", { name: agent.name })} onClose={onClose}
            onSubmit={() => install.mutate({ id: agent.id, body: opts }, { onSuccess: (r) => onCreated({ name: agent.name, ...r }) })}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={install.isPending}>{t("agents.createCommand")}</button>
            </>}>
      <p className="notice" style={{ margin: 0 }}>{t("agents.reinstallNote")}</p>
      <InstallFields value={opts} onChange={setOpts} />
      {install.error && <p className="error-text">{install.error.message}</p>}
    </Dialog>
  );
}

function InstallDialog({ result, onClose }: { result: InstallResult; onClose: () => void }) {
  const { t } = useTranslation();
  const [docker, setDocker] = useState(false);
  const env = `XT_AGENT_URL=${result.install.base_url}\nXT_AGENT_KEY=${result.key}\n`;
  return (
    <Dialog wide title={t("agents.installTitle", { name: result.name })} onClose={onClose}
            footer={<><span className="spacer" /><button type="button" className="btn btn-primary" onClick={onClose}>{t("common.done")}</button></>}>
      <div className="field">
        {t("agents.runThis")}
        <span className="hint">{t("agents.runThisHint")}</span>
        <div className="key-row">
          <pre className="code command">{result.install.command}</pre>
          <CopyButton value={result.install.command} label={t("common.copy")} />
        </div>
      </div>
      <ul className="facts">
        <li>{t("agents.fact1")}</li>
        <li>{t("agents.fact2")}</li>
        <li>{t("agents.fact3")}</li>
      </ul>
      <button type="button" className="btn btn-ghost add-link" onClick={() => setDocker((d) => !d)}>
        {t("agents.dockerAlt")}
      </button>
      {docker && (
        <div className="field">
          <span className="hint">{t("agents.dockerAltHint")}</span>
          <div className="key-row">
            <pre className="code" style={{ flex: 1 }}>{env}</pre>
            <CopyButton value={env} label={t("common.copy")} />
          </div>
        </div>
      )}
    </Dialog>
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
