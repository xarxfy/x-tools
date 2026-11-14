import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import {
  allContainers, containerState, fetchLogs, useContainerAction, useDocker,
  type Container, type DockerState, type Project, type ProjectFile, type Snapshot, type SystemInfo,
} from "../api/docker";
import {
  AGENT_STALE, agentAge, useAgent as useAgentQueryBase, useAgents,
  type AgentReport, type AgentSummary, type Proxmox,
} from "../api/monitor";
import { Icon } from "../components/Icon";
import { Dialog, Dot, Empty, Loading, PageHead, SearchField, matches } from "../components/ui";
import { ago, fmtBytes, fmtDuration, level, pct } from "../components/format";
import { ServiceDialog } from "./ServicesPage";
import "./ServersPage.css";

const useAgentQuery = (id: string, enabled: boolean) => useAgentQueryBase(id, enabled);

function Meter({ label, value, detail }: { label: string; value: number; detail?: string }) {
  return (
    <div className="meter">
      <div className="meter-top">
        <span>{label}</span>
        <b>{value.toFixed(0)} %</b>
      </div>
      <div className="bar">
        <span className={`bar-${level(value)}`} style={{ width: `${Math.min(100, value)}%` }} />
      </div>
      {detail && <div className="meter-detail">{detail}</div>}
    </div>
  );
}

function SystemMeters({ sys, compact }: { sys?: SystemInfo; compact?: boolean }) {
  const { t } = useTranslation();
  if (!sys || (!sys.load && !sys.mem_total && !sys.disk_total)) {
    return <span className="muted">{t("servers.noMetrics")}</span>;
  }
  return (
    <div className={compact ? "meters meters-compact" : "meters"}>
      {sys.load && (
        <Meter label={t("servers.load")} value={(sys.load[0] / Math.max(1, sys.cpus ?? 1)) * 100}
               detail={compact ? undefined : t("servers.loadDetail", { load: sys.load.map((l) => l.toFixed(2)).join(" · "), cpus: sys.cpus })} />
      )}
      {sys.mem_total !== undefined && (
        <Meter label={t("servers.memory")} value={pct(sys.mem_used, sys.mem_total)}
               detail={compact ? undefined : `${fmtBytes(sys.mem_used)} / ${fmtBytes(sys.mem_total)}`} />
      )}
      {sys.disk_total !== undefined && (
        <Meter label={t("servers.disk")} value={pct(sys.disk_used, sys.disk_total)}
               detail={compact ? undefined : `${fmtBytes(sys.disk_used)} / ${fmtBytes(sys.disk_total)}`} />
      )}
    </div>
  );
}

function counts(snap: Snapshot | null | undefined) {
  const all = allContainers(snap);
  return { running: all.filter((c) => containerState(c)[0] === "up").length, total: all.length };
}

/** One server as the pages need it – the machine X-TOOLS runs on, or an agent. */
interface ServerView {
  id: string;
  name: string;
  host: string;
  state: "up" | "warn" | "down";
  stateText: string;
  sys?: SystemInfo;
  snap: Snapshot | null;
  stale: boolean;
  proxmox: Proxmox | null;
  readonly: boolean;
  reported: boolean;
}

function localServer(t: TFunction, data: DockerState): ServerView {
  const snap = data.snapshot;
  return {
    id: "local", name: t("servers.local"), host: snap?.system?.hostname ?? "", snap, stale: data.stale,
    state: !snap ? "warn" : snap.error || data.stale ? "down" : "up",
    stateText: !snap ? t("servers.noSnapshot") : snap.error ?? t("servers.updated", { when: ago(snap.collected_at) }),
    sys: snap?.system, proxmox: null, readonly: false, reported: true,
  };
}

function agentServer(t: TFunction, a: AgentSummary, report?: AgentReport | null): ServerView {
  const age = agentAge(a);
  const fresh = age !== null && age < AGENT_STALE;
  return {
    id: a.id, name: a.name, host: a.hostname, snap: report?.docker ?? null, stale: false,
    state: age === null ? "warn" : fresh ? "up" : "down",
    stateText: age === null ? t("servers.neverReported")
      : fresh ? t("servers.reported", { when: ago(Date.now() / 1000 - age) })
        : t("servers.silent", { when: ago(Date.now() / 1000 - age) }),
    sys: report?.system, proxmox: report?.proxmox ?? null, readonly: true, reported: age !== null,
  };
}

export function ServersPage() {
  const { t } = useTranslation();
  const docker = useDocker();
  const agents = useAgents();
  if (!docker.data) return <Loading error={docker.error} retry={() => docker.refetch()} />;
  const active = (agents.data ?? []).filter((a) => !a.disabled);
  const groups: [string, ServerView[]][] = [
    ["local", [localServer(t, docker.data)]],
    ["proxmox", active.filter((a) => a.kind === "proxmox").map((a) => agentServer(t, a))],
    ["docker", active.filter((a) => a.kind !== "proxmox").map((a) => agentServer(t, a))],
  ];
  const total = 1 + active.length;
  return (
    <>
      <PageHead title={t("nav.servers")} sub={t("servers.count", { count: total })} />
      {groups.filter(([, list]) => list.length).map(([key, list]) => (
        <section key={key}>
          {total > 1 && <h2 className="section-title">{t(`servers.groups.${key}`)}</h2>}
          <div className="server-grid">
            {list.map((srv) => <ServerCard key={srv.id} srv={srv} />)}
          </div>
        </section>
      ))}
      {total === 1 && (
        <div className="card card-pad soft-note">
          <strong>{t("servers.moreTitle")}</strong>
          <p className="muted">
            {t("servers.moreText")} <Link to="/settings?tab=agents">{t("servers.setupAgent")}</Link>
          </p>
        </div>
      )}
    </>
  );
}

function ServerCard({ srv }: { srv: ServerView }) {
  const { t } = useTranslation();
  const agent = useAgentReport(srv.id);
  const full = srv.readonly && agent ? { ...srv, sys: agent.system, snap: agent.docker ?? null, proxmox: agent.proxmox ?? null } : srv;
  const c = counts(full.snap);
  const guests = full.proxmox?.guests;
  return (
    <Link to={`/servers/${srv.id}`} className="card server-card">
      <span className="list-title">
        <Dot state={srv.state} />
        {srv.name}
        {srv.host && <span className="muted server-host">{srv.host}</span>}
      </span>
      <span className="list-sub">{srv.stateText}</span>
      <SystemMeters sys={full.sys} compact />
      <span className="chips">
        {guests && (
          <span className="chip">
            {t("servers.guestsRunning", { running: guests.filter((g) => g.status === "running").length, total: guests.length })}
          </span>
        )}
        {full.snap && !full.snap.error && (
          <span className="chip">{t("servers.containersRunning", { running: c.running, total: c.total })}</span>
        )}
      </span>
    </Link>
  );
}

/** Report of an agent for the cards (null for the local server). */
function useAgentReport(id: string): AgentReport | null {
  const enabled = id !== "local";
  const q = useAgentQuery(id, enabled);
  return enabled ? q.data?.report ?? null : null;
}

export function ServerPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const docker = useDocker();
  const agent = useAgentQuery(id, id !== "local");
  const [params, setParams] = useSearchParams();

  if (!docker.data || (id !== "local" && !agent.data && !agent.error)) {
    return <Loading error={docker.error} retry={() => docker.refetch()} />;
  }
  if (id !== "local" && !agent.data) {
    return (
      <div className="center-state">
        <div>
          <h1>{t("servers.notFound")}</h1>
          <Link to="/servers">{t("servers.back")}</Link>
        </div>
      </div>
    );
  }
  const srv = id === "local" ? localServer(t, docker.data) : agentServer(t, agent.data!, agent.data!.report);
  const snap = srv.snap;
  const c = counts(snap);
  const tabs = [
    "overview",
    ...(srv.proxmox ? ["proxmox"] : []),
    ...(snap || !srv.readonly ? ["docker"] : []),
  ];
  const tab = tabs.includes(params.get("tab") ?? "") ? params.get("tab")! : "overview";

  return (
    <>
      <p style={{ margin: "0 0 6px" }}>
        <Link to="/servers">‹ {t("nav.servers")}</Link>
      </p>
      <PageHead title={srv.name} sub={[srv.host, srv.stateText].filter(Boolean).join(" · ")} />
      {tabs.length > 1 && (
        <div className="tabs" role="tablist">
          {tabs.map((k) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""}
                    onClick={() => setParams(k === "overview" ? {} : { tab: k })}>
              {t(`servers.tab.${k}`)}
              {k === "docker" && snap && <span className="tab-count">{c.total}</span>}
              {k === "proxmox" && srv.proxmox?.guests && <span className="tab-count">{srv.proxmox.guests.length}</span>}
            </button>
          ))}
        </div>
      )}

      {!srv.reported ? (
        <Empty>
          {t("servers.agentPending")} <Link to="/settings?tab=agents">{t("servers.setupAgent")}</Link>
        </Empty>
      ) : tab === "proxmox" && srv.proxmox ? (
        <ProxmoxTab px={srv.proxmox} />
      ) : !snap && tab === "docker" ? (
        <Empty>{t("servers.noSnapshotLong")}</Empty>
      ) : (
        <>
          {snap?.error && <p className="notice">{snap.error}</p>}
          {srv.stale && snap && !snap.error && <p className="notice">{t("servers.stale", { when: ago(snap.collected_at) })}</p>}
          {tab === "overview" ? (
            <Overview srv={srv} onTab={(k) => setParams({ tab: k })} />
          ) : (
            snap && <DockerTab snap={snap} protectedNames={docker.data.protected} readonly={srv.readonly} />
          )}
        </>
      )}
    </>
  );
}

function Overview({ srv, onTab }: { srv: ServerView; onTab: (tab: string) => void }) {
  const { t } = useTranslation();
  const snap = srv.snap;
  const c = counts(snap);
  const problems = allContainers(snap).filter((x) => containerState(x)[0] !== "up");
  const px = srv.proxmox;
  return (
    <>
      <h2 className="section-title">{t("servers.system")}</h2>
      <div className="card card-pad">
        <SystemMeters sys={srv.sys} />
        {srv.sys?.uptime && (
          <p className="muted" style={{ margin: "14px 0 0" }}>
            {t("servers.uptime", { duration: fmtDuration(srv.sys.uptime) })}
            {snap?.docker && ` · Docker ${snap.docker}`}
          </p>
        )}
      </div>
      {px && (
        <>
          <h2 className="section-title">Proxmox</h2>
          {px.error ? (
            <p className="notice">{px.error}</p>
          ) : (
            <div className="card card-pad">
              <div className="stat-row">
                <div>
                  <b>{px.guests?.filter((g) => g.status === "running").length ?? 0}/{px.guests?.length ?? 0}</b>
                  <span className="muted">{t("servers.guestsUp")}</span>
                </div>
                <div><b>{px.nodes?.length ?? 0}</b><span className="muted">{t("servers.nodes")}</span></div>
              </div>
              {px.storage && px.storage.length > 0 && (
                <div className="meters" style={{ marginTop: 18 }}>
                  {px.storage.map((st) => (
                    <Meter key={`${st.node}/${st.storage}`} label={st.storage} value={pct(st.disk, st.maxdisk)}
                           detail={`${fmtBytes(st.disk)} / ${fmtBytes(st.maxdisk)}`} />
                  ))}
                </div>
              )}
              <button type="button" className="btn" style={{ marginTop: 14 }} onClick={() => onTab("proxmox")}>
                {t("servers.allGuests")}
                <Icon name="chevron" size={14} />
              </button>
            </div>
          )}
        </>
      )}
      {snap && !snap.error && (
        <>
          <h2 className="section-title">Docker</h2>
          <div className="card card-pad">
            <div className="stat-row">
              <div><b>{c.running}/{c.total}</b><span className="muted">{t("servers.containersUp")}</span></div>
              <div><b>{snap.projects.length}</b><span className="muted">{t("servers.projects")}</span></div>
            </div>
            {problems.length > 0 && (
              <ul className="plain-list">
                {problems.slice(0, 8).map((x) => (
                  <li key={x.name}>
                    <Dot state={containerState(x)[0]} /> {x.name} – {t(`docker.state.${containerState(x)[1]}`)}
                  </li>
                ))}
              </ul>
            )}
            <button type="button" className="btn" style={{ marginTop: 14 }} onClick={() => onTab("docker")}>
              {t("servers.allContainers")}
              <Icon name="chevron" size={14} />
            </button>
          </div>
        </>
      )}
    </>
  );
}

function ProxmoxTab({ px }: { px: Proxmox }) {
  const { t } = useTranslation();
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  if (px.error) return <p className="notice">{px.error}</p>;
  const guests = px.guests ?? [];
  const running = guests.filter((g) => g.status === "running").length;
  const lxc = guests.filter((g) => g.type === "lxc").length;
  const filters: [string, string][] = [
    ["all", t("proxmox.all", { count: guests.length })],
    ["running", t("proxmox.running", { count: running })],
    ["stopped", t("proxmox.stopped", { count: guests.length - running })],
    ["lxc", `LXC ${lxc}`],
    ["qemu", `VM ${guests.length - lxc}`],
  ];
  const list = guests.filter((g) =>
    (filter === "all" || (filter === "running" ? g.status === "running" : filter === "stopped" ? g.status !== "running" : g.type === filter))
    && matches(query, g.name, String(g.vmid)));
  return (
    <>
      {px.nodes && px.nodes.length > 0 && (
        <div className="server-grid" style={{ marginTop: 16 }}>
          {px.nodes.map((n) => (
            <div key={n.name} className="card card-pad">
              <div className="list-title" style={{ marginBottom: 12 }}>
                <Dot state={n.status === "online" ? "up" : "down"} /> {t("proxmox.node", { name: n.name })}
              </div>
              <div className="meters" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <Meter label="CPU" value={n.cpu * 100} detail={t("proxmox.cores", { count: n.maxcpu })} />
                <Meter label={t("servers.memory")} value={pct(n.mem, n.maxmem)} detail={`${fmtBytes(n.mem)} / ${fmtBytes(n.maxmem)}`} />
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="toolbar">
        <div className="chips">
          {filters.map(([k, label]) => (
            <button key={k} type="button" className={`chip chip-btn${filter === k ? " chip-on" : ""}`} onClick={() => setFilter(k)}>
              {label}
            </button>
          ))}
        </div>
        <SearchField value={query} onChange={setQuery} />
      </div>
      {list.length === 0 ? (
        <Empty>{t("common.noMatch")}</Empty>
      ) : (
        <div className="card list">
          {list.map((g) => {
            const on = g.status === "running";
            return (
              <div key={g.vmid} className="list-row static-row">
                <Dot state={on ? "up" : "off"} />
                <div className="list-main">
                  <div className="list-title">
                    <span className="muted mono">{g.vmid}</span> {g.name}
                    <span className="badge">{g.type === "lxc" ? "LXC" : "VM"}</span>
                  </div>
                  <div className="list-sub">
                    {on
                      ? [`CPU ${(g.cpu * 100).toFixed(0)} % / ${g.maxcpu}`, `RAM ${fmtBytes(g.mem)} / ${fmtBytes(g.maxmem)}`,
                        t("proxmox.upFor", { duration: fmtDuration(g.uptime) })].join(" · ")
                      : `${t(`proxmox.status.${g.status}`, { defaultValue: g.status })} · RAM ${fmtBytes(g.maxmem)}`}
                  </div>
                </div>
                {on && g.maxmem > 0 && (
                  <div className="guest-bar">
                    <div className="bar">
                      <span className={`bar-${level(pct(g.mem, g.maxmem))}`} style={{ width: `${Math.min(100, pct(g.mem, g.maxmem))}%` }} />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

function DockerTab({ snap, protectedNames, readonly }: { snap: Snapshot; protectedNames: string[]; readonly: boolean }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<ProjectFile | null>(null);
  const [logs, setLogs] = useState<string | null>(null);
  const [adopt, setAdopt] = useState<Project | null>(null);

  if (!snap.projects.length && !snap.containers.length) return <Empty>{t("docker.none")}</Empty>;
  const row = (c: Container) => (
    <ContainerRow key={c.name} c={c} readonly={readonly} isProtected={protectedNames.includes(c.name)}
                  onLogs={() => setLogs(c.name)} />
  );

  return (
    <>
      {snap.projects.map((p) => (
        <section key={p.name} className="card project" id={`project-${p.name}`}>
          <header className="project-head">
            <div className="list-main">
              <div className="list-title">{p.name}</div>
              <div className="list-sub">{p.folder}</div>
            </div>
            {readonly ? null : p.service ? (
              <span className="badge" title={t("docker.listedHint")}>{t("docker.service", { name: p.service.name })}</span>
            ) : (
              <button type="button" className="btn btn-ghost" onClick={() => setAdopt(p)}>
                <Icon name="plus" size={14} />
                {t("docker.adopt")}
              </button>
            )}
          </header>
          <div className="list">{p.containers.map(row)}</div>
          {(p.compose.length > 0 || p.dockerfiles.length > 0 || p.git) && (
            <footer className="project-foot">
              <span className="chips">
                {[...p.compose, ...p.dockerfiles].map((f) => (
                  <button key={f.path} type="button" className="chip chip-btn" title={f.path} onClick={() => setFile(f)}>
                    {f.path.startsWith(p.working_dir + "/") ? f.path.slice(p.working_dir.length + 1) : f.path.split("/").pop()}
                  </button>
                ))}
              </span>
              {p.git && (
                <span className="list-sub git">
                  {p.git.error ? p.git.error : (
                    <>
                      <code>{p.git.branch}</code> · <code>{p.git.commit}</code> {p.git.subject} · {ago(p.git.time)}
                      {!!p.git.dirty && <span className="warn-text"> · {t("docker.dirty", { count: p.git.dirty })}</span>}
                    </>
                  )}
                </span>
              )}
            </footer>
          )}
        </section>
      ))}
      {snap.containers.length > 0 && (
        <section className="card project">
          <header className="project-head">
            <div className="list-title">{t("docker.standalone")}</div>
          </header>
          <div className="list">{snap.containers.map(row)}</div>
        </section>
      )}
      <p className="muted small-note">
        {readonly && `${t("docker.readonlyNote")} `}
        {t("docker.maskedNote")}
      </p>

      {file && (
        <Dialog wide title={file.path.split("/").pop() ?? ""} onClose={() => setFile(null)}>
          <p className="list-sub" style={{ margin: 0 }}>{file.path}</p>
          {file.error ? <p className="error-text">{file.error}</p> : <pre className="code">{file.content}</pre>}
        </Dialog>
      )}
      {logs && <LogsDialog container={logs} onClose={() => setLogs(null)} />}
      {adopt && (
        <ServiceDialog
          service={null}
          initial={{
            name: adopt.name,
            folder: adopt.folder,
            type: "Docker Compose",
            ports: [...new Map(adopt.containers.flatMap((c) => c.ports)
              .filter((x) => x.proto === "tcp").map((x) => [x.public, { port: x.public, label: "" }])).values()],
          }}
          onClose={() => setAdopt(null)}
        />
      )}
    </>
  );
}

function ContainerRow({ c, isProtected, readonly, onLogs }: {
  c: Container;
  isProtected: boolean;
  readonly: boolean;
  onLogs: () => void;
}) {
  const { t } = useTranslation();
  const action = useContainerAction();
  const [state, label] = containerState(c);
  const running = ["running", "restarting", "paused"].includes(c.state);
  const run = (a: "start" | "stop" | "restart") => action.mutate({ action: a, container: c.name });
  return (
    <div className="list-row static-row">
      <Dot state={state} />
      <div className="list-main">
        <div className="list-title">
          {c.name}
          <span className={`state-text state-${state}`} title={c.status}>{t(`docker.state.${label}`)}</span>
        </div>
        <div className="list-sub mono" title={c.image}>{c.image}</div>
        {c.ports.length > 0 && (
          <div className="chips">
            {c.ports.map((p) => (
              <span key={`${p.ip}${p.public}${p.proto}`} className="chip">
                {p.ip && `${p.ip}:`}{p.public} → {p.private}{p.proto !== "tcp" && `/${p.proto}`}
              </span>
            ))}
          </div>
        )}
        {action.error && <p className="error-text">{action.error.message}</p>}
      </div>
      {!readonly && <div className="list-side">
        <button type="button" className="btn btn-small" onClick={onLogs}>{t("docker.logs")}</button>
        {isProtected ? (
          <span className="muted small-note" title={t("docker.protectedHint")}>{t("docker.protected")}</span>
        ) : action.isPending ? (
          <span className="muted small-note">{t("docker.working")}</span>
        ) : running ? (
          <>
            <button type="button" className="btn btn-small" onClick={() => run("restart")}>{t("docker.restart")}</button>
            <button type="button" className="btn btn-small btn-stop" onClick={() => run("stop")}>{t("docker.stop")}</button>
          </>
        ) : (
          <button type="button" className="btn btn-small btn-start" onClick={() => run("start")}>{t("docker.start")}</button>
        )}
      </div>}
    </div>
  );
}

function LogsDialog({ container, onClose }: { container: string; onClose: () => void }) {
  const { t } = useTranslation();
  const [lines, setLines] = useState(300);
  const [state, setState] = useState<{ text?: string; error?: string; loading: boolean }>({ loading: false });
  const load = async (n = lines) => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const r = await fetchLogs(container, n);
      setState({ text: r.logs, loading: false });
      requestAnimationFrame(() => {
        const el = document.getElementById("log-view");
        if (el) el.scrollTop = el.scrollHeight;
      });
    } catch (e) {
      setState({ error: e instanceof Error ? e.message : String(e), loading: false });
    }
  };
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Dialog
      wide
      title={t("docker.logsTitle", { name: container })}
      onClose={onClose}
      footer={
        <>
          <select className="input" style={{ width: "auto" }} value={lines} aria-label={t("docker.lines")}
                  onChange={(e) => { const n = Number(e.target.value); setLines(n); void load(n); }}>
            {[100, 300, 1000].map((n) => <option key={n} value={n}>{t("docker.lastLines", { count: n })}</option>)}
          </select>
          <span className="spacer" />
          <button type="button" className="btn" disabled={state.loading} onClick={() => load()}>{t("docker.reload")}</button>
          <button type="button" className="btn btn-primary" onClick={onClose}>{t("common.done")}</button>
        </>
      }
    >
      {state.error ? <p className="error-text">{state.error}</p>
        : state.text === undefined ? <Loading />
          : <pre id="log-view" className="code logs">{state.text || t("docker.noLogs")}</pre>}
    </Dialog>
  );
}
