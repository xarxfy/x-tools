import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { agentControl, localControl, useDocker } from "../api/docker";
import { AGENT_STALE, agentAge, useAgent, useAgents, type AgentSummary } from "../api/monitor";
import { Icon } from "../components/Icon";
import { Dot, Empty, Loading, PageHead } from "../components/ui";
import { ago } from "../components/format";
import { counts, DockerTab, ProxmoxTab } from "./ServersPage";

function agentState(a: AgentSummary): "up" | "down" | "warn" {
  const age = agentAge(a);
  return age === null ? "warn" : age < AGENT_STALE ? "up" : "down";
}

function HostHead({ to, name, state, sub }: { to: string; name: string; state: "up" | "down" | "warn"; sub: string }) {
  return (
    <div className="host-head">
      <Link to={to} className="host-title">
        <Dot state={state} />
        {name}
        <Icon name="chevron" size={16} />
      </Link>
      <span className="muted">{sub}</span>
    </div>
  );
}

/** Proxmox hosts reported by agents – used for the sidebar entry and the page. */
export function useProxmoxHosts() {
  const agents = useAgents();
  return { ...agents, hosts: (agents.data ?? []).filter((a) => !a.disabled && a.has_proxmox) };
}

/** Docker hosts: this server (collector) and agents that report containers. */
export function useDockerHosts() {
  const agents = useAgents();
  const docker = useDocker();
  return {
    docker,
    agents,
    local: !!docker.data?.snapshot && !docker.data.snapshot.error,
    hosts: (agents.data ?? []).filter((a) => !a.disabled && a.has_docker),
  };
}

export function ProxmoxPage() {
  const { t } = useTranslation();
  const { hosts, data, error } = useProxmoxHosts();
  if (!data) return <Loading error={error} />;
  return (
    <>
      <PageHead title="Proxmox" sub={t("fleet.proxmoxSub", { count: hosts.length })} />
      {hosts.length === 0 ? (
        <Empty>{t("fleet.noProxmox")} <Link to="/settings?tab=agents">{t("servers.setupAgent")}</Link></Empty>
      ) : (
        hosts.map((a) => <ProxmoxHost key={a.id} agent={a} />)
      )}
    </>
  );
}

function ProxmoxHost({ agent }: { agent: AgentSummary }) {
  const { t } = useTranslation();
  const detail = useAgent(agent.id);
  const px = detail.data?.report?.proxmox;
  const age = agentAge(agent);
  return (
    <section className="host-section">
      <HostHead to={`/servers/${agent.id}`} name={agent.name} state={agentState(agent)}
                sub={[agent.hostname, age !== null && t("servers.reported", { when: ago(Date.now() / 1000 - age) })].filter(Boolean).join(" · ")} />
      {!detail.data ? <Loading error={detail.error} /> : px ? <ProxmoxTab px={px} agentId={agent.control ? agent.id : undefined} /> : <Empty>{t("fleet.noData")}</Empty>}
    </section>
  );
}

export function DockerPage() {
  const { t } = useTranslation();
  const { docker, agents, local, hosts } = useDockerHosts();
  if (!docker.data || !agents.data) return <Loading error={docker.error ?? agents.error} />;
  const snap = docker.data.snapshot;
  const total = (local ? 1 : 0) + hosts.length;
  return (
    <>
      <PageHead title="Docker" sub={t("fleet.dockerSub", { count: total })} />
      {total === 0 && <Empty>{t("fleet.noDocker")}</Empty>}
      {local && snap && (
        <section className="host-section">
          <HostHead to="/servers/local?tab=docker" name={t("servers.local")}
                    state={docker.data.stale ? "down" : "up"}
                    sub={[snap.system?.hostname, t("servers.containersRunning", counts(snap)),
                      t("servers.updated", { when: ago(snap.collected_at) })].filter(Boolean).join(" · ")} />
          <DockerTab snap={snap} protectedNames={docker.data.protected} readonly={false} control={localControl} />
        </section>
      )}
      {hosts.map((a) => <DockerHost key={a.id} agent={a} />)}
    </>
  );
}

function DockerHost({ agent }: { agent: AgentSummary }) {
  const { t } = useTranslation();
  const detail = useAgent(agent.id);
  const snap = detail.data?.report?.docker;
  return (
    <section className="host-section">
      <HostHead to={`/servers/${agent.id}?tab=docker`} name={agent.name} state={agentState(agent)}
                sub={[agent.hostname, snap && t("servers.containersRunning", counts(snap))].filter(Boolean).join(" · ")} />
      {!detail.data ? <Loading error={detail.error} /> : snap ? (
        <DockerTab snap={snap} protectedNames={[]} readonly={!agent.control} agent
                   control={agent.control ? agentControl(agent.id) : undefined} />
      ) : <Empty>{t("fleet.noData")}</Empty>}
    </section>
  );
}
