import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  manageAgent, useAgent, useAgents, useGroupActions, useSaveAgentMeta, useServerGroups,
  type AgentSummary, type ServerGroup,
} from "../api/monitor";
import { useCan } from "../api/users";
import { Icon } from "../components/Icon";
import { PauseDialog } from "../components/Maintenance";
import { ReportDialog } from "../components/ReportDialog";
import { Dialog, Dot, Empty, Hub, Loading, PageHead, SearchField, ConfirmDelete, matches } from "../components/ui";
import { level } from "../components/format";
import { HostHead, Pending, ServerRedirect, SetupHint, agentState, reported } from "./FleetPages";
import { LinuxTab, type ServerTab } from "./LinuxTab";
import { GroupActionsDialog, SshKeysTab } from "./GroupActions";
import { InventoryTab, NetworkTab } from "./InventoryTabs";
import { fmtDuration } from "../components/format";
import { AddAgentButton, AgentManageBar } from "./AgentManage";
import { NoteText } from "../components/NoteText";
import "./ServersPage.css";

const isLinux = (a: AgentSummary) => !a.disabled && (a.kind === "linux" || a.has_linux);

// --- the list ----------------------------------------------------------------------------------------

function Meters({ a }: { a: AgentSummary }) {
  const { t } = useTranslation();
  const items: [string, number | null][] = [["load", a.load], ["mem", a.mem], ["disk", a.disk]];
  return (
    <div className="srv-meters">
      {items.map(([k, v]) => v === null ? null : (
        <div key={k} className="srv-mini" title={`${t(`overview.${k}`)} ${v} %`}>
          <span>{t(`overview.${k}`)}</span>
          <b>{v} %</b>
          <div className="bar"><span className={`bar-${level(v)}`} style={{ width: `${Math.min(100, v)}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

function ServerRow({ a, onTag }: { a: AgentSummary; onTag: (tag: string) => void }) {
  const { t } = useTranslation();
  return (
    <Link to={`/servers/${a.id}`} className="list-row srv-row">
      <Dot state={agentState(a)} />
      <div className="list-main">
        <div className="list-title">
          {a.name}
          {a.updates ? <span className="badge badge-warn srv-badge">{t("linux.updates", { count: a.updates })}</span> : null}
          {a.reboot && <span className="badge badge-warn srv-badge">{t("overview.reboot")}</span>}
        </div>
        <div className="list-sub">{[a.os || a.hostname, a.uptime ? t("servers.uptime", { duration: fmtDuration(a.uptime) }) : ""].filter(Boolean).join(" · ")}</div>
        {a.tags.length > 0 && (
          <div className="srv-tags">
            {a.tags.map((tag) => (
              <button key={tag} type="button" className="tag" onClick={(e) => { e.preventDefault(); onTag(tag); }}>#{tag}</button>
            ))}
          </div>
        )}
      </div>
      <Meters a={a} />
      <Icon name="chevron" size={16} />
    </Link>
  );
}

/** Installs updates on several servers one after the other (they run in the background on each server). */
function BulkUpdate({ servers }: { servers: AgentSummary[] }) {
  const { t } = useTranslation();
  const canAdmin = useCan()("servers.manage");
  const eligible = servers.filter((s) => s.control && s.has_linux && s.updates);
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  if (!canAdmin || eligible.length === 0) return null;
  const start = async () => {
    setRunning(true);
    for (const s of eligible) {
      setResults((r) => ({ ...r, [s.id]: "…" }));
      try {
        await manageAgent(s.id, "system.update");
        setResults((r) => ({ ...r, [s.id]: t("servers.list.started") }));
      } catch (e) {
        setResults((r) => ({ ...r, [s.id]: `${t("servers.list.failed")}: ${(e as Error).message}` }));
      }
    }
    setRunning(false);
  };
  const close = () => { setOpen(false); setResults({}); };
  return (
    <>
      <button type="button" className="btn btn-small" onClick={() => setOpen(true)}>{t("servers.list.updatesAll", { count: eligible.length })}</button>
      {open && (
        <Dialog title={t("servers.list.updatesAllTitle")} onClose={close}
                footer={<><span className="spacer" /><button type="button" className="btn" onClick={close}>{t("common.close")}</button>
                  {Object.keys(results).length === 0 && <button type="button" className="btn btn-primary" disabled={running} onClick={start}>{t("servers.list.startAll")}</button>}</>}>
          <p className="muted">{t("servers.list.updatesAllText")}</p>
          <ul className="plain-list">
            {eligible.map((s) => (
              <li key={s.id}><strong>{s.name}</strong> <span className="muted">{t("linux.updates", { count: s.updates ?? 0 })}</span>
                {results[s.id] && <span className="srv-result"> – {results[s.id]}</span>}</li>
            ))}
          </ul>
        </Dialog>
      )}
    </>
  );
}

export function GroupsDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const groups = useServerGroups().data ?? [];
  const { add, rename, remove, order } = useGroupActions();
  const [name, setName] = useState("");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const error = add.error ?? rename.error ?? remove.error ?? order.error;
  const move = (index: number, by: number) => {
    const ids = groups.map((g) => g.id);
    [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
    order.mutate(ids);
  };
  const commit = (g: ServerGroup) => {
    const v = (edits[g.id] ?? g.name).trim();
    if (v && v !== g.name) rename.mutate({ id: g.id, name: v });
    setEdits((x) => { const { [g.id]: _, ...rest } = x; return rest; });
  };
  return (
    <Dialog title={t("servers.list.groupsTitle")} onClose={onClose}
            onSubmit={() => name.trim() && add.mutate(name.trim(), { onSuccess: () => setName("") })}
            footer={<><span className="spacer" /><button type="button" className="btn" onClick={onClose}>{t("common.close")}</button></>}>
      <p className="hint">{t("servers.list.groupsHint")}</p>
      {groups.map((g, i) => (
        <div key={g.id} className="category-row">
          <input className="input" maxLength={40} value={edits[g.id] ?? g.name}
                 onChange={(e) => setEdits((x) => ({ ...x, [g.id]: e.target.value }))} onBlur={() => commit(g)} />
          <button type="button" className="btn btn-ghost btn-small" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t("servers.list.up")}>↑</button>
          <button type="button" className="btn btn-ghost btn-small" disabled={i === groups.length - 1} onClick={() => move(i, 1)} aria-label={t("servers.list.down")}>↓</button>
          <ConfirmDelete compact busy={remove.isPending} onConfirm={() => remove.mutate(g.id)} />
        </div>
      ))}
      <div className="category-row">
        <input className="input" maxLength={40} placeholder={t("servers.list.groupPlaceholder")} value={name} onChange={(e) => setName(e.target.value)} />
        <button type="submit" className="btn btn-primary btn-small" disabled={!name.trim() || add.isPending}>{t("servers.list.addGroup")}</button>
      </div>
      {error && <p className="error-text">{error.message}</p>}
    </Dialog>
  );
}

function ServersList() {
  const { t } = useTranslation();
  const agents = useAgents();
  const groups = useServerGroups();
  const { hash } = useLocation();
  const can = useCan();
  const edit = can("servers.organize");
  const [query, setQuery] = useState("");
  const [params] = useSearchParams();
  const [tag, setTag] = useState(params.get("tag") ?? "");
  useEffect(() => { const x = params.get("tag"); if (x !== null) setTag(x); }, [params]); // from the global search
  const [managing, setManaging] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [acting, setActing] = useState(false);
  const [pause, setPause] = useState<{ scope: string; target: string } | null>(null);
  if (hash.startsWith("#agent-")) return <Navigate to={`/servers/${hash.slice(7)}`} replace />; // old links
  if (!agents.data) return <Loading error={agents.error} />;

  const all = agents.data.filter(isLinux);
  const live = all.filter((a) => a.has_linux);
  const pending = all.filter((a) => !a.has_linux);
  const groupList = groups.data ?? [];
  const groupName = new Map(groupList.map((g) => [g.id, g.name]));
  const tags = [...new Set(live.flatMap((a) => a.tags))].sort((x, y) => x.localeCompare(y));
  const shown = live.filter((a) =>
    (!tag || a.tags.some((x) => x.toLowerCase() === tag.toLowerCase())) &&
    matches(query, a.name, a.hostname, a.os, groupName.get(a.group_id ?? ""), ...a.tags));
  const sections: { id: string; name: string | null; servers: AgentSummary[] }[] = [
    ...groupList.map((g) => ({ id: g.id, name: g.name, servers: shown.filter((a) => a.group_id === g.id) })),
    { id: "", name: groupList.length ? t("servers.list.noGroup") : null,
      servers: shown.filter((a) => !a.group_id || !groupName.has(a.group_id)) },
  ].filter((s) => s.servers.length > 0);

  return (
    <>
      <PageHead title={t("nav.servers")} sub={live.length ? t("fleet.linuxSub", { count: live.length }) : undefined}>
        {live.length > 0 && <SearchField value={query} onChange={setQuery} />}
        {edit && live.length > 0 && <button type="button" className="btn" onClick={() => setManaging(true)}>{t("servers.list.manageGroups")}</button>}
        {live.length > 0 && (can("servers.manage") || can("servers.control")) && (
          <button type="button" className="btn" onClick={() => setActing(true)}>{t("bulk.button")}</button>
        )}
        <button type="button" className="btn" onClick={() => setReporting(true)}>{t("report.button")}</button>
        <AddAgentButton kind="linux" />
      </PageHead>
      {reporting && <ReportDialog onClose={() => setReporting(false)} />}
      {!live.length && <SetupHint kind="linux" />}
      <Pending agents={pending} />
      {tags.length > 0 && (
        <div className="category-bar">
          <button type="button" className={`category-pill${tag === "" ? " active" : ""}`} onClick={() => setTag("")}>{t("servers.list.allTags")}</button>
          {tags.map((x) => (
            <button key={x} type="button" className={`category-pill${tag.toLowerCase() === x.toLowerCase() ? " active" : ""}`} onClick={() => setTag(tag === x ? "" : x)}>#{x}</button>
          ))}
        </div>
      )}
      {live.length > 0 && sections.length === 0 && <Empty>{t("servers.list.emptyFilter")}</Empty>}
      {sections.map((s) => (
        <section key={s.id || "none"} className="srv-section">
          {(s.name || sections.length > 1) && (
            <div className="section-row">
              <h2 className="section-title">{s.name ?? t("servers.list.noGroup")}<span className="muted srv-count">{t("servers.list.serverCount", { count: s.servers.length })}</span></h2>
              <div className="section-tools">
                {can("alerts.pause") && s.id && <button type="button" className="btn btn-ghost btn-small" onClick={() => setPause({ scope: "group", target: s.id })}>{t("servers.list.pause")}</button>}
                <BulkUpdate servers={s.servers} />
              </div>
            </div>
          )}
          {!s.name && sections.length === 1 && <div className="srv-bulk"><BulkUpdate servers={s.servers} /></div>}
          <div className="card list">
            {s.servers.map((a) => <ServerRow key={a.id} a={a} onTag={setTag} />)}
          </div>
        </section>
      ))}
      {managing && <GroupsDialog onClose={() => setManaging(false)} />}
      {acting && <GroupActionsDialog servers={live} groups={groupList} initial={{ selected: shown.map((a) => a.id) }} onClose={() => setActing(false)} />}
      {pause && <PauseDialog initial={pause} onClose={() => setPause(null)} />}
    </>
  );
}

// --- the page of one server --------------------------------------------------------------------------------

function MetaDialog({ agent, onClose }: { agent: AgentSummary; onClose: () => void }) {
  const { t } = useTranslation();
  const save = useSaveAgentMeta(agent.id);
  const groups = useServerGroups().data ?? [];
  const known = [...new Set((useAgents().data ?? []).flatMap((a) => a.tags))].sort();
  const [group, setGroup] = useState(agent.group_id ?? "");
  const [tags, setTags] = useState<string[]>(agent.tags);
  const [input, setInput] = useState("");
  const [managing, setManaging] = useState(false);
  const addTag = () => {
    const v = input.trim().replace(/^#/, "");
    if (v && !tags.some((x) => x.toLowerCase() === v.toLowerCase())) setTags([...tags, v]);
    setInput("");
  };
  return (
    <>
      <Dialog title={t("servers.page.edit")} onClose={onClose}
              onSubmit={() => { const pending = input.trim().replace(/^#/, ""); const all = pending && !tags.some((x) => x.toLowerCase() === pending.toLowerCase()) ? [...tags, pending] : tags;
                save.mutate({ group_id: group || null, tags: all }, { onSuccess: onClose }); }}
              footer={<><span className="spacer" /><button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
                <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button></>}>
        <label className="field">
          {t("servers.page.group")}
          <select className="input" value={group} onChange={(e) => setGroup(e.target.value)}>
            <option value="">{t("servers.page.noGroup")}</option>
            {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
          <button type="button" className="link-button small-note" onClick={() => setManaging(true)}>{t("servers.list.manageGroups")}</button>
        </label>
        <div className="field">
          {t("servers.page.tags")}
          <span className="hint">{t("servers.page.tagsHint")}</span>
          <div className="srv-tags">
            {tags.map((x) => (
              <button key={x} type="button" className="tag" title={t("common.remove")} onClick={() => setTags(tags.filter((y) => y !== x))}>#{x} ×</button>
            ))}
          </div>
          <input className="input" list="known-tags" maxLength={30} placeholder={t("servers.page.tagPlaceholder")} value={input}
                 onChange={(e) => setInput(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addTag(); } }} />
          <datalist id="known-tags">{known.map((x) => <option key={x} value={x} />)}</datalist>
        </div>
        {save.error && <p className="error-text">{save.error.message}</p>}
      </Dialog>
      {managing && <GroupsDialog onClose={() => setManaging(false)} />}
    </>
  );
}

function NotesDialog({ agent, onClose }: { agent: AgentSummary; onClose: () => void }) {
  const { t } = useTranslation();
  const save = useSaveAgentMeta(agent.id);
  const [text, setText] = useState(agent.notes);
  return (
    <Dialog wide title={t("servers.page.notes")} onClose={onClose}
            onSubmit={() => save.mutate({ group_id: agent.group_id, tags: agent.tags, notes: text }, { onSuccess: onClose })}
            footer={<><span className="spacer" /><button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button></>}>
      <p className="hint">{t("servers.page.notesHint")}</p>
      <textarea className="input" rows={10} maxLength={5000} autoFocus value={text} onChange={(e) => setText(e.target.value)} />
      {save.error && <p className="error-text">{save.error.message}</p>}
    </Dialog>
  );
}

/** What is this server for – free text for the team. */
function NotesCard({ agent }: { agent: AgentSummary }) {
  const { t } = useTranslation();
  const edit = useCan()("servers.organize");
  const [open, setOpen] = useState(false);
  if (!agent.notes && !edit) return null;
  return (
    <>
      <section className="card card-pad notes-card">
        <div className="notes-head">
          <strong>{t("servers.page.notes")}</strong>
          {edit && <button type="button" className="btn btn-ghost btn-small" onClick={() => setOpen(true)}>{agent.notes ? t("common.edit") : t("servers.page.addNotes")}</button>}
        </div>
        {agent.notes ? <NoteText text={agent.notes} /> : <span className="muted">{t("servers.page.noNotes")}</span>}
      </section>
      {open && <NotesDialog agent={agent} onClose={() => setOpen(false)} />}
    </>
  );
}

export function ServerPage({ agent }: { agent: AgentSummary }) {
  const { t } = useTranslation();
  const detail = useAgent(agent.id);
  const [params, setParams] = useSearchParams();
  const can = useCan();
  const edit = can("servers.organize");
  const groups = useServerGroups().data ?? [];
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [pausing, setPausing] = useState(false);
  const report = detail.data?.report;
  const info = report?.linux;
  const tab = (["overview", "services", "network", "users"] as ServerTab[]).find((x) => x === params.get("tab")) ?? "overview";
  const failed = (info?.services ?? []).filter((s) => s.active === "failed").length;
  const groupName = groups.find((g) => g.id === agent.group_id)?.name;

  return (
    <>
      <p style={{ margin: "0 0 6px" }}><Link to="/servers">‹ {t("servers.page.back")}</Link></p>
      <HostHead anchor={`agent-${agent.id}`} name={agent.name} state={agentState(agent)} source={agent.id} sys={report?.system}
                sub={[agent.hostname, reported(agent), report?.system?.uptime && t("servers.uptime", { duration: fmtDuration(report.system.uptime) })]
                  .filter(Boolean).join(" · ")} />
      <div className="srv-meta">
        {groupName && <span className="badge">{groupName}</span>}
        {agent.tags.map((x) => <span key={x} className="tag">#{x}</span>)}
        <span className="spacer" />
        {edit && <button type="button" className="btn btn-ghost btn-small" onClick={() => setEditing(true)}>{t("servers.page.edit")}</button>}
        {can("alerts.pause") && <button type="button" className="btn btn-ghost btn-small" onClick={() => setPausing(true)}>{t("servers.list.pause")}</button>}
        {agent.kind === "linux" && <AgentManageBar agent={agent} onRemoved={() => navigate("/servers")} />}
      </div>
      <div className="tabs server-tabs" role="tablist">
        {(["overview", "services", "network", "users"] as ServerTab[]).map((x) => (
          <button key={x} type="button" role="tab" aria-selected={tab === x} className={tab === x ? "active" : ""}
                  onClick={() => setParams(x === "overview" ? {} : { tab: x }, { replace: true })}>
            {t(`servers.page.tabs.${x}`)}
            {x === "services" && failed > 0 && <span className="badge badge-down">{failed}</span>}
          </button>
        ))}
      </div>
      {tab === "overview" && <NotesCard agent={agent} />}
      {!detail.data ? <Loading error={detail.error} /> : info ? <LinuxTab agent={agent} info={info} tab={tab} />
        : <Empty>{t("fleet.noData")}</Empty>}
      {editing && <MetaDialog agent={agent} onClose={() => setEditing(false)} />}
      {pausing && <PauseDialog initial={{ scope: "agent", target: agent.id }} onClose={() => setPausing(false)} />}
    </>
  );
}

/** /servers/<id>: the page of a Linux server; old links for other kinds of hosts go to Docker/Proxmox. */
export function ServerRoute() {
  const { id } = useParams();
  const { t } = useTranslation();
  const agents = useAgents();
  if (!agents.data) return <Loading error={agents.error} />;
  const agent = agents.data.find((a) => a.id === id);
  if (agent && !agent.disabled && (agent.kind === "linux" || agent.has_linux)) return <ServerPage agent={agent} />;
  if (!agent && id !== "local") {
    return <div className="center-state"><div><h1>{t("servers.page.notFound")}</h1><Link to="/servers">{t("servers.back")}</Link></div></div>;
  }
  return <ServerRedirect />;
}

/** The Servers page: the list, and (for people who may manage servers) the overview of SSH keys. */
export function ServersPage() {
  const { t } = useTranslation();
  const can = useCan();
  const agents = useAgents();
  const groups = useServerGroups();
  const [params, setParams] = useSearchParams();
  const keys = ["servers", "inventory", "network", ...(can("servers.manage") ? ["keys"] : [])];
  const view = keys.find((k) => k === params.get("view")) ?? "servers";
  const setView = (k: string) => setParams((p) => { const n = new URLSearchParams(p); if (k === "servers") n.delete("view"); else n.set("view", k); return n; }, { replace: true });
  return (
    <Hub title={t("nav.servers")} tab={view} onTab={setView}
         tabs={keys.map((k) => ({ key: k, label: t(k === "servers" ? "hub.serversTab" : k === "keys" ? "bulk.keysTab" : `inventory.tab.${k}`) }))}>
      {view === "keys" ? <SshKeysTab servers={(agents.data ?? []).filter(isLinux)} groups={groups.data ?? []} />
        : view === "inventory" ? <InventoryTab /> : view === "network" ? <NetworkTab /> : <ServersList />}
    </Hub>
  );
}
