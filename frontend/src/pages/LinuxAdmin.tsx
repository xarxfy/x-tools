import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { manageAgent, type AgentSummary, type Firewall, type LinuxInfo, type LinuxUser, type UfwRule } from "../api/monitor";
import { ago } from "../components/format";
import { Collapsible, Dialog, Dot, Empty } from "../components/ui";
import "./LinuxAdmin.css";

/** Runs one administration action; the report of the server (with the new state) arrives a few seconds later. */
function useManage(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ action, target, args }: { action: string; target?: string; args?: Record<string, unknown> }) =>
      manageAgent(agentId, action, target, args),
    onSettled: () => {
      // the agent reports right after the action; ask a few times until the new state is there
      for (const ms of [0, 1500, 4000, 8000]) setTimeout(() => qc.invalidateQueries({ queryKey: ["agents"] }), ms);
    },
  });
}

function Footer({ onClose, children }: { onClose: () => void; children?: React.ReactNode }) {
  const { t } = useTranslation();
  return (
    <>
      <span className="spacer" />
      <button type="button" className="btn" onClick={onClose}>{t("common.close")}</button>
      {children}
    </>
  );
}

// --- updates ---------------------------------------------------------------------------------------

export function UpdateControl({ agent, info, canManage }: { agent: AgentSummary; info: LinuxInfo; canManage: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const run = useManage(agent.id);
  const [open, setOpen] = useState(false);
  const job = info.update_job;
  const running = job?.state === "running";

  // while the dialog is open, fetch the report often – the agent reports every 10 s during an update
  useEffect(() => {
    if (!open || !running) return;
    const timer = setInterval(() => qc.invalidateQueries({ queryKey: ["agents"] }), 8000);
    return () => clearInterval(timer);
  }, [open, running, qc]);

  if (!canManage && !job) return null;
  const pending = info.updates?.length ?? 0;
  return (
    <>
      {running ? (
        <button type="button" className="btn btn-small" onClick={() => setOpen(true)}>{t("admin.updateRunning")}</button>
      ) : canManage ? (
        <button type="button" className="btn btn-small" onClick={() => setOpen(true)}>{t("admin.installUpdates")}</button>
      ) : null}
      {!running && job && (
        <button type="button" className={`badge badge-button ${job.state === "ok" ? "" : "badge-down"}`} onClick={() => setOpen(true)}>
          {t(job.state === "ok" ? "admin.lastUpdateOk" : "admin.lastUpdateFailed", { when: ago(job.finished ?? undefined) })}
        </button>
      )}
      {open && (
        <Dialog wide title={t("admin.updatesTitle")} onClose={() => setOpen(false)}
                footer={<Footer onClose={() => setOpen(false)}>
                  {canManage && !running && (
                    <button type="button" className="btn btn-primary" disabled={run.isPending}
                            onClick={() => run.mutate({ action: "system.update" })}>
                      {run.isPending ? t("docker.working") : t("admin.startUpdate")}
                    </button>
                  )}
                </Footer>}>
          {!job && <p className="hint">{t("admin.updateHint", { count: pending })}</p>}
          {job && (
            <>
              <p className="muted">
                {running ? t("admin.updateRunningHint") : t(job.state === "ok" ? "admin.updateDone" : "admin.updateFailed")}
                {info.reboot_required && !running && <> {t("admin.rebootNeeded")}</>}
              </p>
              <pre className="code deploy-log update-log">{job.log || t("deploy.noLog")}</pre>
            </>
          )}
          {run.error && <p className="error-text">{run.error.message}</p>}
        </Dialog>
      )}
    </>
  );
}

// --- users and SSH keys ----------------------------------------------------------------------------

function UserDialog({ agent, info, name, onClose }: { agent: AgentSummary; info: LinuxInfo; name: string; onClose: () => void }) {
  const { t } = useTranslation();
  const run = useManage(agent.id);
  const user = (info.users ?? []).find((u) => u.name === name);
  const [key, setKey] = useState("");
  const [confirm, setConfirm] = useState<"" | "delete">("");
  const [removeHome, setRemoveHome] = useState(false);
  const [sent, setSent] = useState(false);
  if (!user) return null;
  const system = user.uid < 1000;
  const act = (action: string, args?: Record<string, unknown>, then?: () => void) =>
    run.mutate({ action, target: name, args }, { onSuccess: () => { setSent(true); then?.(); onCloseIf(action); } });
  const onCloseIf = (action: string) => { if (action === "user.delete") onClose(); };
  return (
    <Dialog wide title={t("admin.userTitle", { name })} onClose={onClose} footer={<Footer onClose={onClose} />}>
      <div className="user-facts">
        <span className="muted">{user.home} · {user.shell}</span>
        {user.sudo && <span className="badge">sudo</span>}
        {user.locked && <span className="badge badge-down">{t("admin.locked")}</span>}
        {!user.login && <span className="badge">{t("admin.noShell")}</span>}
      </div>
      {!system && (
        <div className="user-actions">
          <button type="button" className="btn btn-small" disabled={run.isPending} onClick={() => act(user.sudo ? "user.nosudo" : "user.sudo")}>
            {user.sudo ? t("admin.revokeSudo") : t("admin.grantSudo")}
          </button>
          <button type="button" className="btn btn-small" disabled={run.isPending} onClick={() => act(user.locked ? "user.unlock" : "user.lock")}>
            {user.locked ? t("admin.unlock") : t("admin.lock")}
          </button>
          {confirm === "delete" ? (
            <>
              <label className="inline-check small-note">
                <input type="checkbox" checked={removeHome} onChange={(e) => setRemoveHome(e.target.checked)} />
                {t("admin.removeHome")}
              </label>
              <button type="button" className="btn btn-small btn-danger" disabled={run.isPending}
                      onClick={() => act("user.delete", { remove_home: removeHome })}>{t("admin.reallyDelete")}</button>
              <button type="button" className="btn btn-small btn-ghost" onClick={() => setConfirm("")}>{t("common.cancel")}</button>
            </>
          ) : (
            <button type="button" className="btn btn-small btn-danger" onClick={() => setConfirm("delete")}>{t("admin.deleteUser")}</button>
          )}
        </div>
      )}
      {system && <p className="hint">{t("admin.systemAccount")}</p>}

      <h3 className="sub-title">{t("admin.sshKeys")}</h3>
      {user.keys.length === 0 ? <p className="hint">{t("admin.noKeys")}</p> : (
        <div className="card list">
          {user.keys.map((k) => (
            <div key={k.fingerprint} className="list-row static-row">
              <div className="list-main">
                <div className="list-title">{k.comment || t("admin.keyNoComment")} <span className="badge">{k.type.replace("ssh-", "")}</span>{k.options && <span className="badge badge-warn">{t("admin.keyOptions")}</span>}</div>
                <div className="list-sub mono">{k.fingerprint}</div>
              </div>
              <button type="button" className="btn btn-small btn-ghost" disabled={run.isPending}
                      onClick={() => window.confirm(t("admin.confirmRemoveKey")) && act("user.key_remove", { fingerprint: k.fingerprint })}>
                {t("common.remove")}
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="key-add">
        <textarea className="input mono" rows={2} placeholder={t("admin.keyPlaceholder")} value={key} onChange={(e) => setKey(e.target.value)} />
        <button type="button" className="btn btn-small btn-primary" disabled={!key.trim() || run.isPending}
                onClick={() => act("user.key_add", { key: key.trim() }, () => setKey(""))}>{t("admin.addKey")}</button>
      </div>
      {run.error && <p className="error-text">{run.error.message}</p>}
      {sent && !run.error && !run.isPending && <p className="state-up small-note">{t("admin.applied")}</p>}
    </Dialog>
  );
}

function AddUserDialog({ agent, onClose }: { agent: AgentSummary; onClose: () => void }) {
  const { t } = useTranslation();
  const run = useManage(agent.id);
  const [name, setName] = useState("");
  const [sudo, setSudo] = useState(false);
  const [key, setKey] = useState("");
  return (
    <Dialog title={t("admin.addUser")} onClose={onClose}
            onSubmit={() => run.mutate({ action: "user.create", target: name, args: { sudo, key: key.trim() } }, { onSuccess: onClose })}
            footer={<><span className="spacer" /><button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={run.isPending || !name}>{run.isPending ? t("docker.working") : t("common.save")}</button></>}>
      <label className="field">
        {t("admin.userName")}
        <input className="input" required autoFocus maxLength={32} pattern="[a-z_][a-z0-9_\-]*" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="inline-check">
        <input type="checkbox" checked={sudo} onChange={(e) => setSudo(e.target.checked)} />
        {t("admin.sudoRight")}
      </label>
      <label className="field">
        {t("admin.sshKey")}
        <span className="hint">{t("admin.newUserHint")}</span>
        <textarea className="input mono" rows={3} placeholder={t("admin.keyPlaceholder")} value={key} onChange={(e) => setKey(e.target.value)} />
      </label>
      {run.error && <p className="error-text">{run.error.message}</p>}
    </Dialog>
  );
}

export function UsersSection({ agent, info, canManage }: { agent: AgentSummary; info: LinuxInfo; canManage: boolean }) {
  const { t } = useTranslation();
  const [edit, setEdit] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const users = info.users;
  if (!users) return null;
  const state = (u: LinuxUser): "up" | "down" | "off" => (u.locked ? "down" : u.login ? "up" : "off");
  return (
    <>
      <Collapsible title={t("admin.users")} summary={<span>{t("admin.userCount", { count: users.length })}</span>}
                   tools={canManage && <button type="button" className="btn btn-ghost btn-small" onClick={() => setAdding(true)}>{t("admin.addUser")}</button>}>
        <div className="card list">
          {users.map((u) => (
            <div key={u.name} className="list-row static-row">
              <Dot state={state(u)} />
              <div className="list-main">
                <div className="list-title">
                  {u.name}
                  {u.sudo && <span className="badge user-badge">sudo</span>}
                  {u.locked && <span className="badge badge-down user-badge">{t("admin.locked")}</span>}
                </div>
                <div className="list-sub">
                  {[t("admin.keyCount", { count: u.keys.length }), u.last_login ? t("admin.lastLogin", { when: ago(u.last_login) }) : t("admin.neverLoggedIn")].join(" · ")}
                </div>
              </div>
              {canManage && <button type="button" className="btn btn-small btn-ghost" onClick={() => setEdit(u.name)}>{t("admin.manage")}</button>}
            </div>
          ))}
        </div>
      </Collapsible>
      {edit && <UserDialog agent={agent} info={info} name={edit} onClose={() => setEdit(null)} />}
      {adding && <AddUserDialog agent={agent} onClose={() => setAdding(false)} />}
    </>
  );
}

// --- firewall (ufw) ----------------------------------------------------------------------------------

function RuleForm({ agent, onDone }: { agent: AgentSummary; onDone: () => void }) {
  const { t } = useTranslation();
  const run = useManage(agent.id);
  const [f, setF] = useState({ rule: "allow", port: "", proto: "tcp", source: "", comment: "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  return (
    <Dialog title={t("admin.addRule")} onClose={onDone} onSubmit={() => run.mutate({ action: "ufw.add", args: f }, { onSuccess: onDone })}
            footer={<><span className="spacer" /><button type="button" className="btn" onClick={onDone}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={run.isPending || !f.port}>{run.isPending ? t("docker.working") : t("common.save")}</button></>}>
      <div className="grid-2">
        <label className="field">{t("admin.ruleAction")}
          <select className="input" value={f.rule} onChange={set("rule")}>
            <option value="allow">{t("admin.allow")}</option>
            <option value="deny">{t("admin.deny")}</option>
            <option value="reject">{t("admin.reject")}</option>
            <option value="limit">{t("admin.limit")}</option>
          </select>
        </label>
        <label className="field">{t("admin.protocol")}
          <select className="input" value={f.proto} onChange={set("proto")}>
            <option value="tcp">TCP</option><option value="udp">UDP</option><option value="any">{t("admin.anyProto")}</option>
          </select>
        </label>
        <label className="field">{t("admin.port")}
          <input className="input" required autoFocus placeholder="443  /  8000:8100" value={f.port} onChange={set("port")} />
        </label>
        <label className="field">{t("admin.source")}
          <input className="input" placeholder={t("admin.sourceHint")} value={f.source} onChange={set("source")} />
        </label>
      </div>
      <label className="field">{t("admin.comment")}
        <input className="input" maxLength={60} value={f.comment} onChange={set("comment")} />
      </label>
      {run.error && <p className="error-text">{run.error.message}</p>}
    </Dialog>
  );
}

function RuleRow({ agent, rule, canManage }: { agent: AgentSummary; rule: UfwRule; canManage: boolean }) {
  const { t } = useTranslation();
  const run = useManage(agent.id);
  const [confirm, setConfirm] = useState(false);
  const tone = rule.action === "ALLOW" ? "up" : rule.action === "LIMIT" ? "warn" : "down";
  return (
    <div className="list-row static-row">
      <Dot state={tone} />
      <div className="list-main">
        <div className="list-title"><span className="mono">{rule.to}</span> <span className="badge">{rule.action}</span></div>
        <div className="list-sub">{[t("admin.fromWhere", { from: rule.from }), rule.comment].filter(Boolean).join(" · ")}</div>
      </div>
      {canManage && (confirm ? (
        <div className="list-side">
          <button type="button" className="btn btn-small btn-danger" disabled={run.isPending}
                  onClick={() => run.mutate({ action: "ufw.delete", args: { number: rule.number, to: rule.to, action: rule.action, from: rule.from } }, { onSettled: () => setConfirm(false) })}>
            {t("proxmox.yes")}
          </button>
          <button type="button" className="btn btn-small btn-ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</button>
        </div>
      ) : (
        <button type="button" className="btn btn-small btn-ghost" onClick={() => setConfirm(true)}>{t("common.delete")}</button>
      ))}
      {run.error && <span className="error-text small-note" title={run.error.message}>{run.error.message}</span>}
    </div>
  );
}

function FirewallSwitch({ agent, fw }: { agent: AgentSummary; fw: Firewall }) {
  const { t } = useTranslation();
  const run = useManage(agent.id);
  const [confirm, setConfirm] = useState(false);
  const action = fw.active ? "ufw.disable" : "ufw.enable";
  return confirm ? (
    <>
      <span className="muted small-note">{fw.active ? t("admin.confirmDisable") : t("admin.confirmEnable", { ports: (fw.ssh_ports ?? [22]).join(", ") })}</span>
      <button type="button" className="btn btn-small btn-danger" disabled={run.isPending}
              onClick={() => run.mutate({ action }, { onSettled: () => setConfirm(false) })}>{t("proxmox.yes")}</button>
      <button type="button" className="btn btn-small btn-ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</button>
    </>
  ) : (
    <>
      {run.error && <span className="error-text small-note" title={run.error.message}>{run.error.message}</span>}
      <button type="button" className="btn btn-small" onClick={() => setConfirm(true)}>{fw.active ? t("admin.disableFirewall") : t("admin.enableFirewall")}</button>
    </>
  );
}

export function FirewallSection({ agent, info, canManage }: { agent: AgentSummary; info: LinuxInfo; canManage: boolean }) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const fw = info.firewall;
  if (!fw) return null;
  const ok = fw.installed && !fw.error;
  return (
    <>
      <Collapsible title={t("admin.firewall")}
                   summary={ok ? <>
                     <span className={`badge ${fw.active ? "" : "badge-warn"}`}>{fw.active ? t("admin.fwActive") : t("admin.fwInactive")}</span>
                     <span>{t("admin.ruleCount", { count: fw.rules?.length ?? 0 })}</span>
                   </> : <span>{fw.installed ? "" : t("admin.noUfw")}</span>}
                   tools={canManage && ok && <>
                     <FirewallSwitch agent={agent} fw={fw} />
                     <button type="button" className="btn btn-ghost btn-small" onClick={() => setAdding(true)}>{t("admin.addRule")}</button>
                   </>}>
        {!fw.installed ? <Empty>{t("admin.noUfw")}</Empty> : fw.error ? <Empty>{fw.error}</Empty> : (
          <>
            {fw.default && <p className="hint fw-default">{t("admin.defaultPolicy")}: {fw.default}</p>}
            {!fw.rules?.length ? <Empty>{fw.active ? t("admin.noRules") : t("admin.noRulesInactive")}</Empty> : (
              <div className="card list">
                {fw.rules.map((r) => <RuleRow key={`${r.number}${r.to}${r.from}`} agent={agent} rule={r} canManage={canManage} />)}
              </div>
            )}
          </>
        )}
      </Collapsible>
      {adding && <RuleForm agent={agent} onDone={() => setAdding(false)} />}
    </>
  );
}
