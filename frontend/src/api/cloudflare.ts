import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface CfRecord {
  id: string;
  type: string;
  name: string;
  content: string;
  proxied: boolean;
  ttl: number;
}

export interface CfSnapshot {
  fetched_at: number;
  errors: Record<string, string>;
  zones: { id: string; name: string; status: string; records: CfRecord[] }[];
  tunnels: {
    id: string;
    account_id: string;
    name: string;
    status: string;
    connections: number;
    remote_config: boolean;
    ingress: { hostname: string; service: string; path: string }[] | null;
  }[];
  access_apps: { name: string; type: string; domains: string[] }[];
}

export interface CfHost {
  hostname: string;
  zone: string | null;
  dns: { type: string; content: string; proxied: boolean } | null;
  tunnel: { id: string; name: string; status: string } | null;
  route: { tunnel: string; service: string; path: string; status: string } | null;
  access: { name: string; path: string }[];
  service: { id: string; name: string; ports: number[] } | null;
  problems: string[];
}

export interface CfOverview {
  configured: boolean;
  allow_write: boolean;
  snapshot: CfSnapshot | null;
  hosts: CfHost[];
}

export const useCloudflare = () =>
  useQuery({ queryKey: ["cloudflare"], queryFn: () => api<CfOverview>("/cloudflare"), refetchInterval: 120_000 });

export function useRefreshCloudflare() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<CfOverview>("/cloudflare/refresh", { method: "POST" }),
    onSuccess: (data) => {
      qc.setQueryData(["cloudflare"], data);
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export interface CfSettings {
  configured: boolean;
  allow_write: boolean;
  fetched_at: number | null;
  errors: Record<string, string>;
  zones: number;
  tunnels: number;
  access_apps: number;
}

export const useCloudflareSettings = () =>
  useQuery({ queryKey: ["cloudflare", "settings"], queryFn: () => api<CfSettings>("/cloudflare/settings") });

function useInvalidateAll() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["cloudflare"] });
    qc.invalidateQueries({ queryKey: ["features"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };
}

export function useSaveCloudflareToken() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (token: string) => api<unknown>("/cloudflare/settings", { method: "PUT", body: { token } }),
    onSuccess: invalidate,
  });
}

export function useRemoveCloudflare() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: () => api<void>("/cloudflare/settings", { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export interface RecordBody {
  zone_id: string;
  type: string;
  name: string;
  content: string;
  proxied: boolean;
}

export interface RouteBody {
  tunnel_id: string;
  hostname: string;
  service: string;
  dns: boolean;
}

function useCfChange<B>(fn: (body: B) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["cloudflare"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export const useSaveRecord = () =>
  useCfChange(({ id, ...body }: RecordBody & { id?: string }) =>
    id ? api(`/cloudflare/dns/${id}`, { method: "PUT", body }) : api("/cloudflare/dns", { method: "POST", body }));
export const useDeleteRecord = () =>
  useCfChange(({ zone_id, id }: { zone_id: string; id: string }) => api(`/cloudflare/dns/${zone_id}/${id}`, { method: "DELETE" }));
export const useSaveRoute = () => useCfChange((body: RouteBody) => api("/cloudflare/routes", { method: "POST", body }));
export const useDeleteRoute = () => useCfChange((body: RouteBody) => api("/cloudflare/routes/delete", { method: "POST", body }));

export function useAllowWrite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (allow_write: boolean) => api("/cloudflare/settings/write", { method: "PUT", body: { allow_write } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cloudflare"] }),
  });
}
