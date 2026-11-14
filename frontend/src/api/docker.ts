import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface ContainerPort {
  public: number;
  private: number;
  proto: string;
  ip: string;
}

export interface Container {
  name: string;
  image: string;
  state: string;
  health: string;
  status: string;
  service: string;
  ports: ContainerPort[];
  created: number;
}

export interface ProjectFile {
  path: string;
  content: string | null;
  error: string | null;
}

export interface GitInfo {
  commit?: string;
  subject?: string;
  author?: string;
  time?: number;
  branch?: string;
  remote?: string;
  dirty?: number;
  error?: string;
}

export interface Project {
  name: string;
  working_dir: string;
  folder: string;
  containers: Container[];
  compose: ProjectFile[];
  dockerfiles: ProjectFile[];
  git: GitInfo | null;
  service: { id: string; name: string } | null;
}

export interface SystemInfo {
  cpus?: number;
  uptime?: number;
  load?: number[];
  mem_total?: number;
  mem_used?: number;
  disk_total?: number;
  disk_used?: number;
  hostname?: string;
}

export interface Snapshot {
  collected_at: number;
  error: string | null;
  docker: string;
  system?: SystemInfo;
  projects: Project[];
  containers: Container[];
}

export interface DockerState {
  snapshot: Snapshot | null;
  stale: boolean;
  protected: string[];
}

export const useDocker = () =>
  useQuery({ queryKey: ["docker"], queryFn: () => api<DockerState>("/docker"), refetchInterval: 15_000 });

export function useContainerAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { action: "start" | "stop" | "restart"; container: string }) =>
      api<{ ok: boolean }>("/docker/action", { method: "POST", body }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["docker"] }),
  });
}

export const fetchLogs = (container: string, lines: number) =>
  api<{ logs: string }>("/docker/logs", { method: "POST", body: { container, lines } });

/** Container actions – on this server (collector) or through an agent with control switched on. */
export interface DockerControl {
  action: (action: "start" | "stop" | "restart", container: string) => Promise<unknown>;
  logs: (container: string, lines: number) => Promise<{ logs: string }>;
}

export const localControl: DockerControl = {
  action: (action, container) => api("/docker/action", { method: "POST", body: { action, container } }),
  logs: fetchLogs,
};

export interface AgentActionBody {
  action: string;
  target: string;
  node?: string;
  type?: string;
  lines?: number;
}

export const agentAction = (agentId: string, body: AgentActionBody) =>
  api<{ ok: boolean; logs?: string }>(`/agents/${agentId}/action`, { method: "POST", body });

export const agentControl = (agentId: string): DockerControl => ({
  action: (action, container) => agentAction(agentId, { action: `docker.${action}`, target: container }),
  logs: async (container, lines) => ({
    logs: (await agentAction(agentId, { action: "docker.logs", target: container, lines })).logs ?? "",
  }),
});

export type State = "up" | "warn" | "down";

export function containerState(c: Container): [State, string] {
  if (c.state === "running") {
    if (c.health === "unhealthy") return ["warn", "unhealthy"];
    if (c.health === "health: starting") return ["warn", "starting"];
    return ["up", "running"];
  }
  if (c.state === "restarting") return ["warn", "restarting"];
  if (c.state === "paused") return ["warn", "paused"];
  if (c.state === "created") return ["warn", "created"];
  return ["down", "stopped"];
}

export function allContainers(snap: Snapshot | null | undefined): Container[] {
  if (!snap) return [];
  return [...snap.projects.flatMap((p) => p.containers), ...snap.containers];
}
