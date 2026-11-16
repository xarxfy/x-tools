import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface InventoryRow {
  id: string;
  name: string;
  kind: string;
  group: string;
  tags: string[];
  hostname: string;
  os: string;
  kernel: string;
  arch: string;
  support: { state: "ok" | "soon" | "eol" | "unknown"; until: string };
  version: string;
  outdated: boolean;
  uptime: number | null;
  updates: number | null;
  reboot: boolean;
  last_report_at: string | null;
  ips: string[];
  link: string;
}

export interface NetItem {
  ip: string;
  name: string;
  kind: "server" | "guest" | "manual";
  source: string;
  link: string;
  iface: string;
  mac: string;
  network: string;
  virtual: boolean;
  entry_id: string;
  notes: string;
  conflict: boolean;
}

export interface NetworkData {
  items: NetItem[];
  conflicts: { ip: string; names: string[] }[];
}

export const useInventory = () =>
  useQuery({ queryKey: ["inventory"], queryFn: () => api<InventoryRow[]>("/inventory"), refetchInterval: 60_000 });

export const useNetwork = () =>
  useQuery({ queryKey: ["network"], queryFn: () => api<NetworkData>("/network"), refetchInterval: 60_000 });

export function useNetworkEntries() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ["network"] });
  const save = useMutation({
    mutationFn: ({ id, ...body }: { id?: string; ip: string; name: string; notes: string }) =>
      id ? api(`/network/entries/${id}`, { method: "PUT", body }) : api("/network/entries", { method: "POST", body }),
    onSuccess: done,
  });
  const remove = useMutation({ mutationFn: (id: string) => api<void>(`/network/entries/${id}`, { method: "DELETE" }), onSuccess: done });
  return { save, remove };
}
