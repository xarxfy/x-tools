import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface DeployStatus {
  state: "none" | "queued" | "running" | "ok" | "failed";
  action?: "deploy" | "stop" | "remove";
  started?: number;
  finished?: number;
  commit?: string;
  subject?: string;
  log?: string;
}

export interface Site {
  id: string;
  name: string;
  slug: string;
  customer_id: string | null;
  service_id: string | null;
  repo_url: string;
  branch: string;
  compose_file: string;
  port: number | null;
  has_token: boolean;
  env_keys: string[];
  folder: string;
  status: DeployStatus;
}

export interface SiteInput {
  name: string;
  customer_id: string | null;
  repo_url: string;
  branch: string;
  compose_file: string;
  port: number | null;
  token?: string; // undefined: keep, "": remove
  env: { key: string; value?: string }[]; // no value: keep the stored one
}

const busy = (s: Site) => s.status.state === "queued" || s.status.state === "running";

export const useSites = (customerId?: string) =>
  useQuery({
    queryKey: ["sites", customerId ?? ""],
    queryFn: () =>
      api<{ deployer: boolean; sites: Site[] }>(`/sites${customerId ? `?customer_id=${customerId}` : ""}`),
    refetchInterval: (q) => (q.state.data?.sites.some(busy) ? 2_000 : 20_000),
  });

export const useSiteLog = (id: string) =>
  useQuery({
    queryKey: ["site", id],
    queryFn: () => api<Site>(`/sites/${id}`),
    refetchInterval: (q) => (q.state.data && busy(q.state.data) ? 1_500 : false),
  });

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["sites"] });
    qc.invalidateQueries({ queryKey: ["site"] });
    qc.invalidateQueries({ queryKey: ["services"] });
  };
}

export function useSaveSite() {
  const done = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: SiteInput }) =>
      id ? api<Site>(`/sites/${id}`, { method: "PUT", body }) : api<Site>("/sites", { method: "POST", body }),
    onSuccess: done,
  });
}

export function useSiteAction() {
  const done = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: "deploy" | "stop" }) =>
      api<Site>(`/sites/${id}/${action}`, { method: "POST" }),
    onSuccess: done,
  });
}

export function useDeleteSite() {
  const done = useInvalidate();
  return useMutation({
    mutationFn: ({ id, purge }: { id: string; purge: boolean }) =>
      api<void>(`/sites/${id}?purge=${purge}`, { method: "DELETE" }),
    onSuccess: done,
  });
}
