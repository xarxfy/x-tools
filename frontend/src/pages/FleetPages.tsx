import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";
import { agentControl, localControl, useDocker, type SystemInfo } from "../api/docker";
import { AGENT_STALE, agentAge, useAgent, useAgents, type AgentSummary } from "../api/monitor";
import { useCan } from "../api/users";
import { Icon } from "../components/Icon";
import { Dot, Empty, Loading, PageHead } from "../components/ui";
import { ago, fmtDuration } from "../components/format";
import { MetricsChart } from "../components/history";
import { counts, DockerTab, ProxmoxTab, SystemMeters } from "./HostParts";
import "./HostParts.css";

/** Scroll to #agent-… / #local once the page has rendered its hosts. */
function useScrollToHash(ready: boolean) {
  const { hash } = useLocation();
  useEffect(() => {
    if (!ready || !hash) return;
    const timer = setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" }), 300);
    return () => clearTimeout(timer);
  }, [ready, hash]);
}

export function agentState(a: AgentSummary): "up" | "down" | "warn" {
  const age = agentAge(a);
  return age === null ? "warn" : age < AGENT_STALE ? "up" : "down";
}

export function reported(a: AgentSummary): string {
  const age = agentAge(a);
  const when = ago(Date.now() / 1000 - (age ?? 0));
  return age === null ? "" : age < AGENT_STALE ? i18n.t("servers.reported", { when }) : i18n.t("servers.silent", { when });
}

/** Header of one host: name, state, metrics and an optional chart. */
export function HostHead({ anchor, name, state, sub, sys, source }: {
  anchor: string; name: string; state: "up" | "down" | "warn"; sub: string; sys?: SystemInfo; source: string;
}) {
  const { t } = useTranslation();
  const [chart, setChart] = useState(false);
  return (
    <div className="host-head-wrap" id={anchor}>
      <div className="host-head">
        <span className="host-title"><Dot state={state} />{name}</span>
        <span className="muted">{sub}</span>
        <span className="spacer" />
        {sys && (
          <button type="button" className="btn btn-ghost btn-small" onClick={() => setChart((c) => !c)}>
            <Icon name="overview" size={14} />{chart ? t("fleet.hideChart") : t("fleet.showChart")}
          </button>
        )}
      </div>
      {sys && <div className="host-meters"><SystemMeters sys={sys} compact /></div>}
      {chart && <div style={{ marginTop: 12 }}><MetricsChart source={source} /></div>}
    </div>
  );
}

export function SetupHint({ kind }: { kind: "proxmox" | "docker" | "linux" }) {
  const { t } = useTranslation();
  const isAdmin = useCan()("admin.agents");
  return (
    <div className="card card-pad setup-hint">
      <span className="setup-icon"><Icon name={kind === "proxmox" ? "proxmox" : kind === "linux" ? "servers" : "docker"} size={26} /></span>
      <div>
        <h2>{t(`fleet.${kind}EmptyTitle`)}</h2>
        <p className="muted">{t(`fleet.${kind}EmptyText`)}</p>
        {isAdmin ? (
          <Link className="btn btn-primary" to="/admin?tab=agents">{t("fleet.installAgent")}</Link>
        ) : (
          <p className="muted small-note">{t("fleet.askAdmin")}</p>
        )}
      </div>
    </div>
  );
}

export function Pending({ agents }: { agents: AgentSummary[] }) {
  const { t } = useTranslation();
  if (!agents.length) return null;
  return (
    <div className="card card-pad pending-agents">
      <strong>{t("fleet.pendingTitle")}</strong>
      <ul className="plain-list">
        {agents.map((a) => <li key={a.id}><Dot state="warn" /> {a.name} <span className="muted">– {t("fleet.pending")}</span></li>)}
      </ul>
      <Link to="/admin?tab=agents" className="small-note">{t("fleet.pendingLink")}</Link>
    </div>
  );
}

export function ProxmoxPage() {
  const { t } = useTranslation();
  const agents = useAgents();
  useScrollToHash(!!agents.data);
  if (!agents.data) return <Loading error={agents.error} />;
  const all = agents.data.filter((a) => !a.disabled && (a.kind === "proxmox" || a.has_proxmox));
  const live = all.filter((a) => a.has_proxmox);
  const pending = all.filter((a) => !a.has_proxmox);
  return (
    <>
      <PageHead title="Proxmox" sub={live.length ? t("fleet.proxmoxSub", { count: live.length }) : undefined} />
      {!live.length && <SetupHint kind="proxmox" />}
      <Pending agents={pending} />
      {live.map((a) => <ProxmoxHost key={a.id} agent={a} />)}
    </>
  );
}

function ProxmoxHost({ agent }: { agent: AgentSummary }) {
  const { t } = useTranslation();
  const detail = useAgent(agent.id);
  const report = detail.data?.report;
  const px = report?.proxmox;
  return (
    <section className="host-section">
      <HostHead anchor={`agent-${agent.id}`} name={agent.name} state={agentState(agent)} source={agent.id}
                sys={report?.system}
                sub={[agent.hostname, reported(agent), report?.system?.uptime && t("servers.uptime", { duration: fmtDuration(report.system.uptime) })]
                  .filter(Boolean).join(" · ")} />
      {!detail.data ? <Loading error={detail.error} /> : px ? <ProxmoxTab px={px} agentId={agent.id} control={agent.control} />
        : <Empty>{t("fleet.noData")}</Empty>}
    </section>
  );
}

export function DockerPage() {
  const { t } = useTranslation();
  const docker = useDocker();
  const agents = useAgents();
  useScrollToHash(!!docker.data && !!agents.data);
  if (!docker.data || !agents.data) return <Loading error={docker.error ?? agents.error} />;
  const snap = docker.data.snapshot;
  const all = agents.data.filter((a) => !a.disabled && (a.kind === "docker" || a.has_docker));
  const live = all.filter((a) => a.has_docker);
  const pending = all.filter((a) => !a.has_docker && a.kind === "docker");
  const total = (snap ? 1 : 0) + live.length;
  return (
    <>
      <PageHead title="Docker" sub={total ? t("fleet.dockerSub", { count: total }) : undefined} />
      {!total && <SetupHint kind="docker" />}
      <Pending agents={pending} />
      {snap && (
        <section className="host-section">
          <HostHead anchor="local" name={t("servers.local")} source="local" sys={snap.system}
                    state={snap.error || docker.data.stale ? "down" : "up"}
                    sub={[snap.system?.hostname, !snap.error && t("servers.containersRunning", counts(snap)),
                      t("servers.updated", { when: ago(snap.collected_at) }),
                      snap.system?.uptime && t("servers.uptime", { duration: fmtDuration(snap.system.uptime) })].filter(Boolean).join(" · ")} />
          {snap.error && <p className="notice">{snap.error}</p>}
          {docker.data.stale && !snap.error && <p className="notice">{t("servers.stale", { when: ago(snap.collected_at) })}</p>}
          {!snap.error && <DockerTab snap={snap} protectedNames={docker.data.protected} readonly={false} control={localControl} />}
        </section>
      )}
      {live.map((a) => <DockerHost key={a.id} agent={a} />)}
    </>
  );
}

function DockerHost({ agent }: { agent: AgentSummary }) {
  const { t } = useTranslation();
  const detail = useAgent(agent.id);
  const report = detail.data?.report;
  const snap = report?.docker;
  return (
    <section className="host-section">
      <HostHead anchor={`agent-${agent.id}`} name={agent.name} state={agentState(agent)} source={agent.id}
                sys={report?.system}
                sub={[agent.hostname, snap && t("servers.containersRunning", counts(snap)), reported(agent)].filter(Boolean).join(" · ")} />
      {!detail.data ? <Loading error={detail.error} /> : snap ? (
        <DockerTab snap={snap} protectedNames={[]} readonly={!agent.control} agent
                   control={agent.control ? agentControl(agent.id) : undefined} />
      ) : <Empty>{t("fleet.noData")}</Empty>}
    </section>
  );
}

/** Old links (/servers, /servers/<id>, /servers/<id>/guest/…) lead to the new pages. */
export function ServerRedirect() {
  const { id, node, vmid } = useParams();
  const agents = useAgents();
  if (!id || id === "local") return <Navigate to="/docker" replace />;
  if (node && vmid) return <Navigate to={`/proxmox/${id}/${node}/${vmid}`} replace />;
  if (!agents.data) return <Loading error={agents.error} />;
  const agent = agents.data.find((a) => a.id === id);
  const to = agent?.kind === "linux" ? "/servers" : agent?.kind === "proxmox" || agent?.has_proxmox ? "/proxmox" : "/docker";
  return <Navigate to={`${to}#agent-${id}`} replace />;
}
