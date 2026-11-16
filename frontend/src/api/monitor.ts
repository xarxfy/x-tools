import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Snapshot, SystemInfo } from "./docker";

export interface Issue {
  key: string;
  kind: string;
  level: "down" | "warn";
  text: string;
  link: string;
  manual?: boolean;
  paused?: boolean;
}

export interface Overview {
  issues: Issue[];
  counts: {
    services: number;
    customers: number;
    servers: number;
    guests: number;
    guests_running: number;
    containers: number;
    containers_running: number;
    sites: number;
    sites_up: number;
  };
  system: SystemInfo | null;
  notifications: boolean;
  hosts: OverviewHost[];
  jobs: { total: number; ok: number; late: number; paused: number };
  backup: { enabled: boolean; last_at: number | null; last_ok: boolean | null };
  sites: { domain: string; level?: "up" | "warn" | "down"; cert_expires?: number }[];
}

export interface OverviewHost {
  name: string;
  link: string;
  state: "up" | "down" | "warn";
  kinds: string[];
  load: number | null;
  mem: number | null;
  disk: number | null;
  updates: number | null;
  reboot: boolean;
}

export interface SiteCheck {
  checked_at: number;
  level?: "up" | "warn" | "down";
  label?: string;
  status?: number;
  ms?: number;
  ips: string[];
  cloudflare: boolean;
  cert_expires?: number;
}

export interface Channel {
  enabled: boolean;
  has_token: boolean;
  chat_id?: string;
  server?: string;
  topic?: string;
}

export interface NotificationSettings {
  enabled: boolean;
  delay: number;
  recovery: boolean;
  events: Record<string, boolean>;
  telegram: Channel;
  ntfy: Channel;
  base_url?: string;
  last?: { time: number; title: string; results: Record<string, string | null> } | null;
  checked_at?: number | null;
  monitor_error?: string;
  open?: { text: string; since: number; sent: boolean }[];
  manual?: string[];
}

export type AgentKind = "proxmox" | "docker" | "linux";

export interface AgentSummary {
  id: string;
  name: string;
  kind: AgentKind;
  disabled: boolean;
  created_at: string;
  last_report_at: string | null;
  hostname: string;
  version: string;
  has_docker: boolean;
  has_proxmox: boolean;
  has_linux: boolean;
  outdated: boolean;
  latest_version: string;
  control: boolean;
  group_id: string | null;
  tags: string[];
  notes: string;
  load: number | null;
  mem: number | null;
  disk: number | null;
  updates: number | null;
  reboot: boolean;
  os: string;
  uptime: number | null;
}

export interface ProxmoxGuest {
  vmid: number;
  name: string;
  type: "lxc" | "qemu";
  status: string;
  node: string;
  cpu: number;
  maxcpu: number;
  mem: number;
  maxmem: number;
  uptime: number;
  tags?: string;
}

export interface PveDisk {
  key: string;
  volume: string;
  storage: string;
  size: string;
  size_bytes: number | null;
  mountpoint: string;
  backup: boolean;
}

export interface PveNet {
  key: string;
  name: string;
  bridge: string;
  mac: string;
  model: string;
  vlan: string;
  ip: string;
  gw: string;
  ip6: string;
  firewall: boolean;
  rate: string;
}

export interface PveConfig {
  cores: number;
  sockets: number;
  memory: number;
  swap: number | null;
  disks: PveDisk[];
  nets: PveNet[];
  ostype: string;
  hostname: string;
  onboot: boolean;
  startup: string;
  unprivileged: boolean | null;
  features: Record<string, string>;
  tags: string[];
  description: string;
  nameserver: string;
  agent: boolean | null;
}

export interface PveGuestDetails {
  fetched_at: number;
  error?: string;
  config?: PveConfig;
  ips?: { interface: string; address: string }[];
  snapshots?: { name: string; time: number | null; description: string; parent: string }[] | null;
  conf?: { path: string; source: "file" | "api"; content: string };
}

export interface PveBackup {
  vmid: number;
  storage: string;
  volid: string;
  time: number | null;
  size: number | null;
  notes: string;
  protected: boolean;
}

export interface PveNodeDetails {
  error?: string;
  pveversion?: string;
  kernel?: string;
  cpu_model?: string;
  boot_mode?: string;
  version?: string;
  release?: string;
  updates?: string[] | null;
  network?: {
    iface: string;
    type: string;
    active: boolean;
    autostart: boolean;
    cidr: string;
    cidr6: string;
    gateway: string;
    ports: string;
    vlan_aware: boolean;
    vlan_id: string;
    comments: string;
  }[] | null;
}

export interface Proxmox {
  error?: string;
  details?: {
    fetched_at: number;
    error?: string;
    guests: Record<string, PveGuestDetails>;
    backups: PveBackup[];
    nodes: Record<string, PveNodeDetails>;
  } | null;
  nodes?: { name: string; status: string; cpu: number; maxcpu: number; mem: number; maxmem: number; uptime: number }[];
  guests?: ProxmoxGuest[];
  storage?: { storage: string; node: string; disk: number; maxdisk: number }[];
}

export interface LinuxService {
  name: string;
  active: string;
  sub: string;
  enabled: string;
  description: string;
}

export interface SshKey {
  type: string;
  fingerprint: string;
  comment: string;
  options: boolean;
}

export interface LinuxUser {
  name: string;
  uid: number;
  home: string;
  shell: string;
  login: boolean;
  sudo: boolean;
  locked: boolean;
  password: boolean;
  last_login: number | null;
  keys: SshKey[];
}

export interface UfwRule {
  number: number;
  to: string;
  action: string;
  direction: string;
  from: string;
  comment: string;
}

export interface Firewall {
  installed: boolean;
  active?: boolean;
  default?: string;
  rules?: UfwRule[];
  ssh_ports?: number[];
  error?: string;
}

export interface UpdateJob {
  state: "running" | "ok" | "failed";
  log: string;
  started: number | null;
  finished: number | null;
  manager: string;
}

export interface LinuxInfo {
  os?: string;
  kernel?: string;
  arch?: string;
  updates?: string[] | null;
  reboot_required?: boolean;
  services?: LinuxService[] | null;
  ports?: { port: number; proto: string; address: string; process: string }[];
  disks?: { mount: string; fstype: string; used: number; total: number }[];
  users?: LinuxUser[] | null;
  firewall?: Firewall | null;
  update_job?: UpdateJob | null;
  error?: string;
}

export interface AgentReport {
  linux?: LinuxInfo | null;
  hostname?: string;
  system?: SystemInfo;
  docker?: Snapshot | null;
  proxmox?: Proxmox | null;
}

export interface AgentDetail extends AgentSummary {
  report: AgentReport | null;
}

export const AGENT_STALE = 300;

export function agentAge(a: AgentSummary): number | null {
  return a.last_report_at ? Date.now() / 1000 - Date.parse(a.last_report_at) / 1000 : null;
}

export const useOverview = () =>
  useQuery({ queryKey: ["overview"], queryFn: () => api<Overview>("/overview"), refetchInterval: 30_000 });

export const useSiteChecks = () =>
  useQuery({ queryKey: ["sitechecks"], queryFn: () => api<Record<string, SiteCheck>>("/sitechecks") });

export function useRunSiteChecks() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (customer_id?: string) =>
      api<Record<string, SiteCheck>>("/sitechecks", { method: "POST", body: { customer_id: customer_id ?? null } }),
    onSuccess: (data) => {
      qc.setQueryData(["sitechecks"], data);
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export const useNotificationSettings = () =>
  useQuery({ queryKey: ["notifications"], queryFn: () => api<NotificationSettings>("/settings/notifications") });

export function useSaveNotifications() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: unknown) => api<NotificationSettings>("/settings/notifications", { method: "PUT", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export const useTestNotification = () =>
  useMutation({
    mutationFn: (channel: "telegram" | "ntfy") =>
      api<{ ok: boolean }>("/settings/notifications/test", { method: "POST", body: { channel } }),
  });

export const useAgents = () =>
  useQuery({ queryKey: ["agents"], queryFn: () => api<AgentSummary[]>("/agents"), refetchInterval: 30_000 });

export const useAgent = (id: string, enabled = true) =>
  useQuery({
    queryKey: ["agents", id],
    enabled,
    retry: false,
    queryFn: () => api<AgentDetail>(`/agents/${id}`),
    refetchInterval: 30_000,
  });

function useAgentsInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["agents"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };
}

export interface InstallOptions {
  kind: AgentKind;
  control: boolean;
  docker: boolean;
  proxmox_url: string;
  proxmox_token_id: string;
  proxmox_token_secret: string;
  proxmox_verify_tls: boolean;
  cf_client_id: string;
  cf_client_secret: string;
  compose_roots: string;
}

export interface InstallInfo {
  command: string;
  expires_at: number;
  base_url: string;
}

export function useCreateAgent() {
  const invalidate = useAgentsInvalidate();
  return useMutation({
    mutationFn: (body: InstallOptions & { name: string }) =>
      api<AgentSummary & { key: string; install: InstallInfo }>("/agents", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export type StoredInstallOptions = Partial<InstallOptions> & {
  has_proxmox_token_secret?: boolean;
  has_cf_client_secret?: boolean;
};

export const useInstallOptions = (id: string) =>
  useQuery({
    queryKey: ["agents", id, "install-options"],
    staleTime: 0,
    gcTime: 0,
    queryFn: () => api<StoredInstallOptions>(`/agents/${id}/install-options`),
  });

export function useNewInstall() {
  const invalidate = useAgentsInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: InstallOptions }) =>
      api<{ key: string; install: InstallInfo }>(`/agents/${id}/install`, { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export interface Features {
  customers: boolean;
  cloudflare?: boolean;
}

export const useFeatures = () =>
  useQuery({ queryKey: ["features"], queryFn: () => api<Features>("/features"), staleTime: 60_000 });

export function useSaveFeatures() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Features) => api<Features>("/features", { method: "PUT", body }),
    onSuccess: (data) => {
      qc.setQueryData(["features"], data);
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useUpdateAgent() {
  const invalidate = useAgentsInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; disabled?: boolean; name?: string }) =>
      api<AgentSummary>(`/agents/${id}`, { method: "PUT", body }),
    onSuccess: invalidate,
  });
}

export function useDeleteAgent() {
  const invalidate = useAgentsInvalidate();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/agents/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export interface About {
  version: string;
  base_url: string;
  timezone: string;
  data_dir: string;
  secret_key_from_env: boolean;
  compose_roots: string[];
  protected: string[];
  collector_seen: number | null;
}

export const useAbout = () => useQuery({ queryKey: ["about"], queryFn: () => api<About>("/about") });

/** Server administration (updates, users, ufw) – administrators only. */
export const manageAgent = (agentId: string, action: string, target = "host", args: Record<string, unknown> = {}) =>
  api<{ ok: boolean }>(`/agents/${agentId}/manage`, { method: "POST", body: { action, target, args } });

// --- server groups and tags (free names) ---
export interface ServerGroup {
  id: string;
  name: string;
  position: number;
}

export const useServerGroups = () =>
  useQuery({ queryKey: ["server-groups"], queryFn: () => api<ServerGroup[]>("/server-groups") });

export function useGroupActions() {
  const qc = useQueryClient();
  const done = () => {
    qc.invalidateQueries({ queryKey: ["server-groups"] });
    qc.invalidateQueries({ queryKey: ["agents"] });
  };
  const add = useMutation({
    mutationFn: (name: string) => api<ServerGroup>("/server-groups", { method: "POST", body: { name } }),
    onSuccess: done,
  });
  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api<ServerGroup>(`/server-groups/${id}`, { method: "PUT", body: { name } }),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/server-groups/${id}`, { method: "DELETE" }),
    onSuccess: done,
  });
  const order = useMutation({
    mutationFn: (ids: string[]) => api<ServerGroup[]>("/server-groups/order", { method: "PUT", body: { ids } }),
    onSuccess: done,
  });
  return { add, rename, remove, order };
}

export function useSaveAgentMeta(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { group_id: string | null; tags: string[]; notes?: string }) =>
      api<AgentSummary>(`/agents/${agentId}/meta`, { method: "PUT", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

// --- SSH key inventory (from the reports of the Linux agents) ---
export interface KeyInstall {
  agent_id: string;
  agent: string;
  user: string;
  control: boolean;
  options: boolean;
}

export interface KeyEntry {
  fingerprint: string;
  type: string;
  comments: string[];
  installs: KeyInstall[];
}

export const useKeyInventory = (enabled = true) =>
  useQuery({ queryKey: ["agents", "keys"], queryFn: () => api<KeyEntry[]>("/agents/keys"), enabled, refetchInterval: 60_000 });
