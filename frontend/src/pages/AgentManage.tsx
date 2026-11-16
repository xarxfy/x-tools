import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useCreateAgent, useDeleteAgent, useInstallOptions, useNewInstall, useUpdateAgent,
  type AgentKind, type AgentSummary, type InstallInfo, type InstallOptions, type StoredInstallOptions,
} from "../api/monitor";
import { useCan } from "../api/users";
import { Icon } from "../components/Icon";
import { ConfirmDelete, CopyButton, Dialog, Loading } from "../components/ui";
import { Toggle } from "./AdminSettings";
import "./AdminSettings.css";

/** Removes the agent from the target system – systemd installation and Docker variant. Contains no secrets. */
const UNINSTALL =
  "systemctl disable --now x-tools-agent 2>/dev/null; " +
  "rm -rf /opt/x-tools-agent /etc/x-tools-agent /etc/systemd/system/x-tools-agent.service; " +
  "systemctl daemon-reload 2>/dev/null; docker rm -f x-tools-agent 2>/dev/null; echo 'X-TOOLS agent removed'";

const NO_INSTALL: InstallOptions = {
  kind: "linux", control: false, docker: false, proxmox_url: "https://127.0.0.1:8006", proxmox_token_id: "", proxmox_token_secret: "",
  proxmox_verify_tls: false, cf_client_id: "", cf_client_secret: "", compose_roots: "/opt,/srv,/home,/root",
};

/** Proxmox host or Docker host – decides what the agent reports. */
function KindPicker({ value, onChange }: { value: AgentKind; onChange: (k: AgentKind) => void }) {
  const { t } = useTranslation();
  return (
    <div className="kind-picker" role="radiogroup" aria-label={t("agents.kind")}>
      {(["linux", "proxmox", "docker"] as const).map((k) => (
        <button key={k} type="button" role="radio" aria-checked={value === k}
                className={`kind-option${value === k ? " selected" : ""}`} onClick={() => onChange(k)}>
          <Icon name={k === "proxmox" ? "proxmox" : k === "linux" ? "servers" : "docker"} size={22} />
          <strong>{t(`agents.kinds.${k}`)}</strong>
          <span>{t(`agents.kinds.${k}Hint`)}</span>
        </button>
      ))}
    </div>
  );
}

/** Values for the install command: Proxmox API token (Proxmox hosts), Cloudflare service token, folders. */
function InstallFields({ value, onChange, stored, lockKind = false }: {
  value: InstallOptions;
  onChange: (v: InstallOptions) => void;
  stored?: StoredInstallOptions;
  lockKind?: boolean;
}) {
  const { t } = useTranslation();
  const [cf, setCf] = useState(!!value.cf_client_id);
  const [more, setMore] = useState(false);
  const set = (patch: Partial<InstallOptions>) => onChange({ ...value, ...patch });
  return (
    <>
      {!lockKind && <KindPicker value={value.kind} onChange={(kind) => set({ kind })} />}
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
            {stored?.has_proxmox_token_secret && <span className="hint">{t("agents.secretStored")}</span>}
            <input className="input secret" required={!stored?.has_proxmox_token_secret} type="password" autoComplete="off"
                   placeholder={stored?.has_proxmox_token_secret ? "••••••••" : "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"}
                   value={value.proxmox_token_secret} onChange={(e) => set({ proxmox_token_secret: e.target.value })} />
          </label>
          <label className="inline-check">
            <input type="checkbox" checked={value.proxmox_verify_tls} onChange={(e) => set({ proxmox_verify_tls: e.target.checked })} />
            {t("agents.verifyTls")}
          </label>
          <p className="muted small-note" style={{ margin: 0 }}>{t("agents.proxmoxHowto")}</p>
        </div>
      )}
      {value.kind === "linux" && (
        <Toggle checked={value.docker} label={t("agents.alsoDocker")} hint={t("agents.alsoDockerHint")}
                onChange={(docker) => set({ docker })} />
      )}
      <Toggle checked={value.control} label={t("agents.control")}
              hint={t(`agents.controlHint${value.kind === "proxmox" ? "Proxmox" : value.kind === "linux" ? "Linux" : "Docker"}`)}
              onChange={(control) => set({ control })} />
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
            {stored?.has_cf_client_secret && <span className="hint">{t("agents.secretStored")}</span>}
            <input className="input secret" required={!stored?.has_cf_client_secret} type="password" autoComplete="off"
                   placeholder={stored?.has_cf_client_secret ? "••••••••" : ""} value={value.cf_client_secret}
                   onChange={(e) => set({ cf_client_secret: e.target.value })} />
          </label>
        </div>
      )}
      {(value.kind === "docker" || (value.kind === "linux" && value.docker)) && (
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

function CreateAgentDialog({ kind, onClose, onCreated }: { kind: AgentKind; onClose: () => void; onCreated: (r: InstallResult) => void }) {
  const { t } = useTranslation();
  const create = useCreateAgent();
  const [name, setName] = useState("");
  const [opts, setOpts] = useState<InstallOptions>({ ...NO_INSTALL, kind });
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
      <InstallFields value={opts} onChange={setOpts} lockKind />
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
  const stored = useInstallOptions(agent.id);
  const [opts, setOpts] = useState<InstallOptions | null>(null);

  useEffect(() => {
    if (stored.data && !opts) {
      const { has_proxmox_token_secret: _a, has_cf_client_secret: _b, ...rest } = stored.data;
      setOpts({ ...NO_INSTALL, kind: agent.kind, ...rest, proxmox_token_secret: "", cf_client_secret: "" });
    }
  }, [stored.data, opts, agent.kind]);

  return (
    <Dialog wide title={t("agents.reinstallTitle", { name: agent.name })} onClose={onClose}
            onSubmit={() => opts && install.mutate({ id: agent.id, body: opts }, { onSuccess: (r) => onCreated({ name: agent.name, ...r }) })}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={install.isPending || !opts}>{t("agents.createCommand")}</button>
            </>}>
      <p className="notice" style={{ margin: 0 }}>{t("agents.reinstallNote")}</p>
      {!opts ? <Loading error={stored.error} /> : (
        <>
          {stored.data?.proxmox_token_id || stored.data?.cf_client_id ? (
            <p className="muted small-note" style={{ margin: 0 }}>{t("agents.prefilled")}</p>
          ) : null}
          <InstallFields value={opts} onChange={setOpts} stored={stored.data} />
        </>
      )}
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


/** "Add Linux server / Docker host / Proxmox host" – shown on the page of that kind, for people who may manage agents. */
export function AddAgentButton({ kind }: { kind: AgentKind }) {
  const { t } = useTranslation();
  const allowed = useCan()("agents.manage");
  const [creating, setCreating] = useState(false);
  const [result, setResult] = useState<InstallResult | null>(null);
  if (!allowed) return null;
  return (
    <>
      <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
        <Icon name="plus" size={16} />{t(`agents.add.${kind}`)}
      </button>
      {creating && <CreateAgentDialog kind={kind} onClose={() => setCreating(false)} onCreated={(r) => { setCreating(false); setResult(r); }} />}
      {result && <InstallDialog result={result} onClose={() => setResult(null)} />}
    </>
  );
}

/** Rename, install command, switch off, delete – for one host, on its own page. */
export function AgentManageBar({ agent, onRemoved }: { agent: AgentSummary; onRemoved?: () => void }) {
  const { t } = useTranslation();
  const allowed = useCan()("agents.manage");
  const update = useUpdateAgent();
  const remove = useDeleteAgent();
  const [reinstall, setReinstall] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [removed, setRemoved] = useState(false);
  const [result, setResult] = useState<InstallResult | null>(null);
  if (!allowed) return null;
  return (
    <>
      <span className="agent-bar">
        {agent.disabled && <span className="badge">{t("agents.disabled")}</span>}
        {agent.outdated && <span className="badge badge-warn" title={t("agents.updateHint")}>{t("agents.update", { version: agent.latest_version })}</span>}
        <button type="button" className="btn btn-ghost btn-small" onClick={() => setRenaming(true)}>{t("agents.rename")}</button>
        <button type="button" className="btn btn-ghost btn-small" onClick={() => setReinstall(true)}>{t("agents.installCommand")}</button>
        <button type="button" className="btn btn-ghost btn-small" disabled={update.isPending} onClick={() => update.mutate({ id: agent.id, disabled: !agent.disabled })}>
          {agent.disabled ? t("agents.enable") : t("agents.disable")}
        </button>
        <ConfirmDelete compact onConfirm={() => remove.mutate(agent.id, { onSuccess: () => setRemoved(true) })} busy={remove.isPending} />
      </span>
      {remove.error && <p className="error-text">{remove.error.message}</p>}
      {renaming && <RenameDialog agent={agent} onClose={() => setRenaming(false)} />}
      {reinstall && <ReinstallDialog agent={agent} onClose={() => setReinstall(false)} onCreated={(r) => { setReinstall(false); setResult(r); }} />}
      {result && <InstallDialog result={result} onClose={() => setResult(null)} />}
      {removed && <UninstallDialog agent={agent} onClose={() => { setRemoved(false); onRemoved?.(); }} />}
    </>
  );
}
