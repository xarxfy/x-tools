import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  allContainers, containerState, fetchLogs, useContainerAction, useDocker,
  type Container, type Project, type ProjectFile, type Snapshot, type SystemInfo,
} from "../api/docker";
import { Icon } from "../components/Icon";
import { Dialog, Dot, Empty, Loading, PageHead } from "../components/ui";
import { ago, fmtBytes, fmtDuration, level, pct } from "../components/format";
import { ServiceDialog } from "./ServicesPage";
import "./ServersPage.css";

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

export function ServersPage() {
  const { t } = useTranslation();
  const docker = useDocker();
  if (!docker.data) return <Loading error={docker.error} retry={() => docker.refetch()} />;
  const snap = docker.data.snapshot;
  const c = counts(snap);
  const state = !snap ? "warn" : snap.error || docker.data.stale ? "down" : "up";
  return (
    <>
      <PageHead title={t("nav.servers")} sub={t("servers.sub")} />
      <div className="server-grid">
        <Link to="/servers/local" className="card server-card">
          <span className="list-title">
            <Dot state={state} />
            {t("servers.local")}
            {snap?.system?.hostname && <span className="muted server-host">{snap.system.hostname}</span>}
          </span>
          <span className="list-sub">
            {!snap ? t("servers.noSnapshot") : snap.error ? snap.error
              : t("servers.updated", { when: ago(snap.collected_at) })}
          </span>
          <SystemMeters sys={snap?.system} compact />
          {snap && !snap.error && (
            <span className="chips">
              <span className="chip">{t("servers.containersRunning", { running: c.running, total: c.total })}</span>
            </span>
          )}
        </Link>
      </div>
      <div className="card card-pad soft-note">
        <strong>{t("servers.moreTitle")}</strong>
        <p className="muted">{t("servers.moreText")}</p>
      </div>
    </>
  );
}

export function ServerPage() {
  const { id } = useParams();
  const { t } = useTranslation();
  const docker = useDocker();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "docker" ? "docker" : "overview";

  if (id !== "local") {
    return (
      <div className="center-state">
        <div>
          <h1>{t("servers.notFound")}</h1>
          <Link to="/servers">{t("servers.back")}</Link>
        </div>
      </div>
    );
  }
  if (!docker.data) return <Loading error={docker.error} retry={() => docker.refetch()} />;
  const { snapshot: snap, stale } = docker.data;
  const c = counts(snap);

  return (
    <>
      <p style={{ margin: "0 0 6px" }}>
        <Link to="/servers">‹ {t("nav.servers")}</Link>
      </p>
      <PageHead
        title={t("servers.local")}
        sub={[snap?.system?.hostname, snap && t("servers.updated", { when: ago(snap.collected_at) })]
          .filter(Boolean).join(" · ")}
      />
      <div className="tabs" role="tablist">
        {(["overview", "docker"] as const).map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""}
                  onClick={() => setParams(k === "overview" ? {} : { tab: k })}>
            {t(`servers.tab.${k}`)}
            {k === "docker" && snap && <span className="tab-count">{c.total}</span>}
          </button>
        ))}
      </div>

      {!snap ? (
        <Empty>{t("servers.noSnapshotLong")}</Empty>
      ) : (
        <>
          {snap.error && <p className="notice">{snap.error}</p>}
          {stale && !snap.error && <p className="notice">{t("servers.stale", { when: ago(snap.collected_at) })}</p>}
          {tab === "overview" ? <Overview snap={snap} onDocker={() => setParams({ tab: "docker" })} />
            : <DockerTab snap={snap} protectedNames={docker.data.protected} />}
        </>
      )}
    </>
  );
}

function Overview({ snap, onDocker }: { snap: Snapshot; onDocker: () => void }) {
  const { t } = useTranslation();
  const c = counts(snap);
  const problems = allContainers(snap).filter((x) => containerState(x)[0] !== "up");
  return (
    <>
      <h2 className="section-title">{t("servers.system")}</h2>
      <div className="card card-pad">
        <SystemMeters sys={snap.system} />
        {snap.system?.uptime && (
          <p className="muted" style={{ margin: "14px 0 0" }}>
            {t("servers.uptime", { duration: fmtDuration(snap.system.uptime) })}
            {snap.docker && ` · Docker ${snap.docker}`}
          </p>
        )}
      </div>
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
        <button type="button" className="btn" style={{ marginTop: 14 }} onClick={onDocker}>
          {t("servers.allContainers")}
          <Icon name="chevron" size={14} />
        </button>
      </div>
    </>
  );
}

function DockerTab({ snap, protectedNames }: { snap: Snapshot; protectedNames: string[] }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<ProjectFile | null>(null);
  const [logs, setLogs] = useState<string | null>(null);
  const [adopt, setAdopt] = useState<Project | null>(null);

  if (!snap.projects.length && !snap.containers.length) return <Empty>{t("docker.none")}</Empty>;
  const row = (c: Container) => (
    <ContainerRow key={c.name} c={c} isProtected={protectedNames.includes(c.name)} onLogs={() => setLogs(c.name)} />
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
            {p.service ? (
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
      <p className="muted small-note">{t("docker.maskedNote")}</p>

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

function ContainerRow({ c, isProtected, onLogs }: { c: Container; isProtected: boolean; onLogs: () => void }) {
  const { t } = useTranslation();
  const action = useContainerAction();
  const [state, label] = containerState(c);
  const running = ["running", "restarting", "paused"].includes(c.state);
  const run = (a: "start" | "stop" | "restart") => action.mutate({ action: a, container: c.name });
  return (
    <div className="list-row container-row">
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
      <div className="list-side">
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
      </div>
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
