import { useState } from "react";
import { useTranslation } from "react-i18next";
import { agentAction } from "../api/docker";
import { manageAgent, useKeyInventory, type AgentSummary, type KeyEntry, type ServerGroup } from "../api/monitor";
import { useCan } from "../api/users";
import { Dialog, Empty } from "../components/ui";

export type Step = { label: string; run: () => Promise<unknown> };

/** Runs steps one after the other (one per server) and keeps a result text for each. */
export function useBulk() {
  const [results, setResults] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const run = async (steps: Step[]) => {
    setRunning(true);
    setResults({});
    for (const [i, step] of steps.entries()) {
      const key = `${i}`;
      setResults((r) => ({ ...r, [key]: "…" }));
      try {
        await step.run();
        setResults((r) => ({ ...r, [key]: "ok" }));
      } catch (e) {
        setResults((r) => ({ ...r, [key]: `error: ${(e as Error).message}` }));
      }
    }
    setRunning(false);
  };
  return { results, running, run, reset: () => setResults({}), started: Object.keys(results).length > 0 };
}

export function BulkResults({ steps, results }: { steps: Step[]; results: Record<string, string> }) {
  const { t } = useTranslation();
  return (
    <ul className="plain-list bulk-results">
      {steps.map((s, i) => {
        const r = results[`${i}`];
        return (
          <li key={i}>
            <strong>{s.label}</strong>{" "}
            {r === "ok" ? <span className="state-up">{t("bulk.ok")}</span>
              : r?.startsWith("error:") ? <span className="error-text">{r.slice(6)}</span>
                : <span className="muted">{r ?? t("bulk.waiting")}</span>}
          </li>
        );
      })}
    </ul>
  );
}

type Kind = "update" | "key_add" | "key_remove" | "firewall" | "restart";

/** One action for several servers: choose servers (by group, tag or one by one), the action, confirm, run. */
export function GroupActionsDialog({ servers, groups, initial, onClose }: {
  servers: AgentSummary[]; groups: ServerGroup[]; initial?: { kind?: Kind; selected?: string[]; user?: string; key?: string }; onClose: () => void;
}) {
  const { t } = useTranslation();
  const can = useCan();
  const kinds: Kind[] = [
    ...(can("servers.manage") ? (["update", "key_add", "key_remove", "firewall"] as Kind[]) : []),
    ...(can("servers.control") ? (["restart"] as Kind[]) : []),
  ];
  const eligible = servers.filter((s) => s.has_linux && s.control);
  const [kind, setKind] = useState<Kind>(initial?.kind ?? kinds[0]);
  const [selected, setSelected] = useState<Set<string>>(new Set(initial?.selected ?? []));
  const [f, setF] = useState({ user: initial?.user ?? "", key: initial?.key ?? "", fingerprint: "", service: "", rule: "allow", port: "", proto: "tcp", source: "" });
  const [confirm, setConfirm] = useState(false);
  const bulk = useBulk();
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  const tags = [...new Set(eligible.flatMap((s) => s.tags))].sort();
  const toggle = (id: string) => setSelected((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const pick = (ids: string[]) => setSelected(new Set(ids));
  const chosen = eligible.filter((s) => selected.has(s.id) && (kind !== "update" || s.updates));

  const valid = chosen.length > 0 && (
    kind === "update" ? true
      : kind === "key_add" ? !!f.user && !!f.key.trim()
        : kind === "key_remove" ? !!f.user && !!f.fingerprint.trim()
          : kind === "firewall" ? !!f.port : !!f.service);
  const steps: Step[] = chosen.map((s) => ({
    label: s.name,
    run: () => kind === "update" ? manageAgent(s.id, "system.update")
      : kind === "key_add" ? manageAgent(s.id, "user.key_add", f.user, { key: f.key.trim() })
        : kind === "key_remove" ? manageAgent(s.id, "user.key_remove", f.user, { fingerprint: f.fingerprint.trim() })
          : kind === "firewall" ? manageAgent(s.id, "ufw.add", "host", { rule: f.rule, port: f.port, proto: f.proto, source: f.source })
            : agentAction(s.id, { action: "systemd.restart", target: f.service.endsWith(".service") ? f.service : `${f.service}.service` }),
  }));

  return (
    <Dialog wide title={t("bulk.title")} onClose={onClose}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.close")}</button>
              {!bulk.started && !confirm && <button type="button" className="btn btn-primary" disabled={!valid} onClick={() => setConfirm(true)}>{t("bulk.review")}</button>}
              {!bulk.started && confirm && <>
                <button type="button" className="btn" onClick={() => setConfirm(false)}>{t("bulk.back")}</button>
                <button type="button" className="btn btn-danger" disabled={bulk.running} onClick={() => bulk.run(steps)}>{t("bulk.run", { count: chosen.length })}</button>
              </>}
            </>}>
      {bulk.started ? (
        <BulkResults steps={steps} results={bulk.results} />
      ) : confirm ? (
        <>
          <p>{t(`bulk.confirm.${kind}`, { count: chosen.length })}</p>
          <ul className="plain-list">{chosen.map((s) => <li key={s.id}>{s.name}</li>)}</ul>
        </>
      ) : eligible.length === 0 ? <Empty>{t("bulk.noServers")}</Empty> : (
        <>
          <label className="field">
            {t("bulk.action")}
            <select className="input" value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
              {kinds.map((k) => <option key={k} value={k}>{t(`bulk.kinds.${k}`)}</option>)}
            </select>
          </label>
          {kind === "key_add" && (<>
            <div className="grid-2">
              <label className="field">{t("bulk.user")}<input className="input" value={f.user} maxLength={32} onChange={set("user")} /></label>
            </div>
            <label className="field">{t("bulk.key")}<textarea className="input mono" rows={2} placeholder={t("admin.keyPlaceholder")} value={f.key} onChange={set("key")} /></label>
          </>)}
          {kind === "key_remove" && (
            <div className="grid-2">
              <label className="field">{t("bulk.user")}<input className="input" value={f.user} maxLength={32} onChange={set("user")} /></label>
              <label className="field">{t("bulk.fingerprint")}<input className="input mono" placeholder="SHA256:…" value={f.fingerprint} onChange={set("fingerprint")} /></label>
            </div>
          )}
          {kind === "firewall" && (
            <div className="grid-2">
              <label className="field">{t("admin.ruleAction")}
                <select className="input" value={f.rule} onChange={set("rule")}>
                  <option value="allow">{t("admin.allow")}</option><option value="deny">{t("admin.deny")}</option>
                  <option value="reject">{t("admin.reject")}</option><option value="limit">{t("admin.limit")}</option>
                </select></label>
              <label className="field">{t("admin.protocol")}
                <select className="input" value={f.proto} onChange={set("proto")}><option value="tcp">TCP</option><option value="udp">UDP</option><option value="any">{t("admin.anyProto")}</option></select></label>
              <label className="field">{t("admin.port")}<input className="input" placeholder="443  /  8000:8100" value={f.port} onChange={set("port")} /></label>
              <label className="field">{t("admin.source")}<input className="input" placeholder={t("admin.sourceHint")} value={f.source} onChange={set("source")} /></label>
            </div>
          )}
          {kind === "restart" && (
            <label className="field">{t("bulk.service")}<input className="input" placeholder="nginx" value={f.service} onChange={set("service")} /></label>
          )}
          <div className="field">
            {t("bulk.servers")}
            <div className="srv-tags bulk-quick">
              <button type="button" className="tag" onClick={() => pick(eligible.map((s) => s.id))}>{t("bulk.all")}</button>
              <button type="button" className="tag" onClick={() => pick([])}>{t("bulk.none")}</button>
              {groups.map((g) => <button key={g.id} type="button" className="tag" onClick={() => pick(eligible.filter((s) => s.group_id === g.id).map((s) => s.id))}>{g.name}</button>)}
              {tags.map((x) => <button key={x} type="button" className="tag" onClick={() => pick(eligible.filter((s) => s.tags.includes(x)).map((s) => s.id))}>#{x}</button>)}
            </div>
            <div className="bulk-list">
              {eligible.map((s) => (
                <label key={s.id} className="inline-check">
                  <input type="checkbox" checked={selected.has(s.id)} onChange={() => toggle(s.id)} />
                  {s.name}
                  {kind === "update" && !s.updates && <span className="muted small-note"> – {t("bulk.noUpdates")}</span>}
                </label>
              ))}
            </div>
            {servers.some((s) => s.has_linux && !s.control) && <span className="hint">{t("bulk.noControl")}</span>}
          </div>
        </>
      )}
    </Dialog>
  );
}

/** Which SSH key has access to which server and user – and removing or adding a key on many servers at once. */
export function SshKeysTab({ servers, groups }: { servers: AgentSummary[]; groups: ServerGroup[] }) {
  const { t } = useTranslation();
  const inventory = useKeyInventory();
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<KeyEntry | null>(null);
  const bulk = useBulk();
  if (!inventory.data) return <Empty>{t("app.loading")}</Empty>;
  const closeRemove = () => { setRemoving(null); bulk.reset(); inventory.refetch(); };
  const steps: Step[] = removing ? removing.installs.filter((i) => i.control).map((i) => ({
    label: `${i.agent} · ${i.user}`, run: () => manageAgent(i.agent_id, "user.key_remove", i.user, { fingerprint: removing.fingerprint }),
  })) : [];
  return (
    <>
      <div className="section-row">
        <p className="muted intro">{t("bulk.keysIntro")}</p>
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>{t("bulk.addKey")}</button>
      </div>
      {inventory.data.length === 0 ? <Empty>{t("bulk.noKeys")}</Empty> : (
        <div className="card list" style={{ marginTop: 16 }}>
          {inventory.data.map((k) => (
            <div key={k.fingerprint} className="list-row static-row">
              <div className="list-main">
                <div className="list-title">{k.comments.join(", ") || t("admin.keyNoComment")} <span className="badge">{k.type.replace("ssh-", "")}</span>
                  <span className="badge">{t("bulk.onServers", { count: k.installs.length })}</span></div>
                <div className="list-sub mono">{k.fingerprint}</div>
                <div className="srv-tags">
                  {k.installs.map((i) => <span key={`${i.agent_id}-${i.user}`} className="tag">{i.agent} · {i.user}</span>)}
                </div>
              </div>
              <button type="button" className="btn btn-small btn-ghost" onClick={() => setRemoving(k)}>{t("bulk.removeEverywhere")}</button>
            </div>
          ))}
        </div>
      )}
      {adding && <GroupActionsDialog servers={servers} groups={groups} initial={{ kind: "key_add" }} onClose={() => { setAdding(false); inventory.refetch(); }} />}
      {removing && (
        <Dialog wide title={t("bulk.removeEverywhere")} onClose={closeRemove}
                footer={<><span className="spacer" /><button type="button" className="btn" onClick={closeRemove}>{t("common.close")}</button>
                  {!bulk.started && <button type="button" className="btn btn-danger" disabled={steps.length === 0 || bulk.running} onClick={() => bulk.run(steps)}>{t("bulk.run", { count: steps.length })}</button>}</>}>
          <p className="mono small-note">{removing.fingerprint}</p>
          {!bulk.started && <p>{t("bulk.confirmRemove", { count: steps.length })}</p>}
          {removing.installs.some((i) => !i.control) && <p className="hint">{t("bulk.noControl")}</p>}
          <BulkResults steps={steps} results={bulk.results} />
        </Dialog>
      )}
    </>
  );
}
