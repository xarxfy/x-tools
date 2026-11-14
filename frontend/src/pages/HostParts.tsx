import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  agentAction, allContainers, containerState,
  type Container, type DockerControl, type Project, type ProjectFile, type Snapshot, type SystemInfo,
} from "../api/docker";
import { type Proxmox, type ProxmoxGuest, type PveNodeDetails } from "../api/monitor";
import { Icon } from "../components/Icon";
import { Dialog, Dot, Empty, Loading, SearchField, matches } from "../components/ui";
import { ago, fmtBytes, fmtDuration, level, pct } from "../components/format";
import { ServiceDialog } from "./ServicesPage";
import { useCan } from "../api/users";
import "./HostParts.css";

export function Meter({ label, value, detail }: { label: string; value: number; detail?: string }) {
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

export function SystemMeters({ sys, compact }: { sys?: SystemInfo; compact?: boolean }) {
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

export function counts(snap: Snapshot | null | undefined) {
  const all = allContainers(snap);
  return { running: all.filter((c) => containerState(c)[0] === "up").length, total: all.length };
}

/** One server as the pages need it – the machine X-TOOLS runs on, or an agent. */
export function ProxmoxTab({ px, agentId, control = false }: { px: Proxmox; agentId: string; control?: boolean }) {
  const { t } = useTranslation();
  const canControl = useCan()("operator") && control;
  const [showUpdates, setShowUpdates] = useState<string | null>(null);
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
              <NodeInfo info={px.details?.nodes?.[n.name]} onUpdates={() => setShowUpdates(n.name)} />
            </div>
          ))}
        </div>
      )}
      {px.details?.nodes && Object.entries(px.details.nodes).some(([, d]) => d.network?.length) && (
        <>
          <h2 className="section-title">{t("proxmox.hostNetwork")}</h2>
          {Object.entries(px.details.nodes).map(([name, d]) => d.network?.length ? (
            <div key={name} className="card list host-net">
              {d.network.map((nw) => (
                <div key={nw.iface} className="list-row static-row">
                  <Dot state={nw.active ? "up" : "off"} />
                  <div className="list-main">
                    <div className="list-title">
                      {nw.iface}<span className="badge">{nw.type}</span>
                      {nw.vlan_aware && <span className="badge">{t("proxmox.vlanAware")}</span>}
                      {Object.keys(px.details!.nodes).length > 1 && <span className="muted">{name}</span>}
                    </div>
                    <div className="list-sub">
                      {[nw.cidr, nw.cidr6, nw.gateway && `→ ${nw.gateway}`, nw.ports && t("proxmox.ports", { ports: nw.ports }),
                        nw.vlan_id && `VLAN ${nw.vlan_id}`, nw.comments].filter(Boolean).join(" · ") || "–"}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : null)}
        </>
      )}
      {showUpdates && (
        <Dialog title={t("proxmox.updatesTitle", { name: showUpdates })} onClose={() => setShowUpdates(null)}
                footer={<><span className="spacer" /><button type="button" className="btn btn-primary" onClick={() => setShowUpdates(null)}>{t("common.done")}</button></>}>
          <pre className="code">{(px.details?.nodes?.[showUpdates]?.updates ?? []).join("\n")}</pre>
          <p className="muted small-note" style={{ margin: 0 }}>{t("proxmox.updatesHint")}</p>
        </Dialog>
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
                    <Link to={`/proxmox/${agentId}/${g.node}/${g.vmid}`} className="guest-link">
                      <span className="muted mono">{g.vmid}</span> {g.name}
                    </Link>
                    <span className="badge">{g.type === "lxc" ? "LXC" : "VM"}</span>
                  </div>
                  <div className="list-sub">
                    {on
                      ? [`CPU ${(g.cpu * 100).toFixed(0)} % / ${g.maxcpu}`, `RAM ${fmtBytes(g.mem)} / ${fmtBytes(g.maxmem)}`,
                        t("proxmox.upFor", { duration: fmtDuration(g.uptime) })].join(" · ")
                      : `${t(`proxmox.status.${g.status}`, { defaultValue: g.status })} · RAM ${fmtBytes(g.maxmem)}`}
                  </div>
                </div>
                {canControl && <GuestActions agentId={agentId!} guest={g} />}
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

export function DockerTab({ snap, protectedNames, readonly: agentReadonly, agent = false, control }: {
  snap: Snapshot;
  protectedNames: string[];
  readonly: boolean;
  agent?: boolean;
  control?: DockerControl;
}) {
  const { t } = useTranslation();
  const canOperate = useCan()("operator");
  const readonly = agentReadonly || !canOperate || !control;
  const [file, setFile] = useState<ProjectFile | null>(null);
  const [logs, setLogs] = useState<string | null>(null);
  const [adopt, setAdopt] = useState<Project | null>(null);

  if (!snap.projects.length && !snap.containers.length) return <Empty>{t("docker.none")}</Empty>;
  const row = (c: Container) => (
    <ContainerRow key={c.name} c={c} readonly={readonly} control={control} isProtected={protectedNames.includes(c.name)}
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
            {readonly || agent ? null : p.service ? (
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
        {agent && agentReadonly && `${t("docker.readonlyNote")} `}
        {t("docker.maskedNote")}
      </p>

      {file && (
        <Dialog wide title={file.path.split("/").pop() ?? ""} onClose={() => setFile(null)}>
          <p className="list-sub" style={{ margin: 0 }}>{file.path}</p>
          {file.error ? <p className="error-text">{file.error}</p> : <pre className="code">{file.content}</pre>}
        </Dialog>
      )}
      {logs && control && <LogsDialog container={logs} control={control} onClose={() => setLogs(null)} />}
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

function ContainerRow({ c, isProtected, readonly, control, onLogs }: {
  c: Container;
  isProtected: boolean;
  readonly: boolean;
  control?: DockerControl;
  onLogs: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const action = useMutation({
    mutationFn: ({ action: a, container }: { action: "start" | "stop" | "restart"; container: string }) =>
      control!.action(a, container),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["docker"] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
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

function LogsDialog({ container, control, onClose }: { container: string; control: DockerControl; onClose: () => void }) {
  const { t } = useTranslation();
  const [lines, setLines] = useState(300);
  const [state, setState] = useState<{ text?: string; error?: string; loading: boolean }>({ loading: false });
  const load = async (n = lines) => {
    setState((s) => ({ ...s, loading: true }));
    try {
      const r = await control.logs(container, n);
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

export function GuestActions({ agentId, guest }: { agentId: string; guest: ProxmoxGuest }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState<"" | "stop" | "reboot" | "shutdown">("");
  const run = useMutation({
    mutationFn: (action: string) =>
      agentAction(agentId, { action: `proxmox.${action}`, target: String(guest.vmid), node: guest.node, type: guest.type }),
    onSettled: () => {
      setConfirm("");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["agents"] }), 4000);
    },
  });
  const on = guest.status === "running";
  if (run.isPending) return <span className="muted small-note">{t("docker.working")}</span>;
  return (
    <div className="list-side guest-actions">
      {run.error && <span className="error-text small-note" title={run.error.message}>{t("proxmox.failed")}</span>}
      {run.isSuccess && <span className="state-up small-note">{t("proxmox.sent")}</span>}
      {confirm ? (
        <>
          <span className="muted small-note">{t(`proxmox.confirm.${confirm}`, { name: guest.name })}</span>
          <button type="button" className="btn btn-small btn-danger" onClick={() => run.mutate(confirm)}>{t("proxmox.yes")}</button>
          <button type="button" className="btn btn-small btn-ghost" onClick={() => setConfirm("")}>{t("common.cancel")}</button>
        </>
      ) : on ? (
        <>
          <button type="button" className="btn btn-small" onClick={() => setConfirm("reboot")}>{t("proxmox.reboot")}</button>
          <button type="button" className="btn btn-small" onClick={() => setConfirm("shutdown")}>{t("proxmox.shutdown")}</button>
          <button type="button" className="btn btn-small btn-stop" onClick={() => setConfirm("stop")}>{t("proxmox.stop")}</button>
        </>
      ) : (
        <button type="button" className="btn btn-small btn-start" onClick={() => run.mutate("start")}>{t("docker.start")}</button>
      )}
    </div>
  );
}

function NodeInfo({ info, onUpdates }: { info?: PveNodeDetails; onUpdates: () => void }) {
  const { t } = useTranslation();
  if (!info) return null;
  return (
    <div className="node-info">
      {info.version && <span>Proxmox VE {info.version}</span>}
      {info.kernel && <span className="muted">{info.kernel.replace(/^Linux /, "Kernel ").split(" #")[0]}</span>}
      {info.updates === null || info.updates === undefined ? (
        <span className="muted" title={t("proxmox.updatesUnknownHint")}>{t("proxmox.updatesUnknown")}</span>
      ) : info.updates.length ? (
        <button type="button" className="badge badge-warn badge-btn" onClick={onUpdates}>
          {t("proxmox.updates", { count: info.updates.length })}
        </button>
      ) : (
        <span className="state-up">{t("proxmox.upToDate")}</span>
      )}
    </div>
  );
}
