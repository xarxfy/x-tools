import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

// --- maintenance windows ---
export interface MaintenanceWindow {
  id: string;
  scope: "all" | "local" | "agent" | "service" | "job" | "customer";
  target: string;
  label: string;
  reason: string;
  until: number;
  created_by: string;
}

export const useMaintenance = () =>
  useQuery({ queryKey: ["maintenance"], queryFn: () => api<MaintenanceWindow[]>("/maintenance"), refetchInterval: 30_000 });

function useRefreshIssues() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["maintenance"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };
}

export function useStartMaintenance() {
  const done = useRefreshIssues();
  return useMutation({
    mutationFn: (body: { scope: string; target: string; minutes: number; reason: string }) =>
      api<MaintenanceWindow>("/maintenance", { method: "POST", body }),
    onSuccess: done,
  });
}

export function useEndMaintenance() {
  const done = useRefreshIssues();
  return useMutation({ mutationFn: (id: string) => api<void>(`/maintenance/${id}`, { method: "DELETE" }), onSuccess: done });
}

// --- jobs (heartbeats) ---
export interface Job {
  id: string;
  name: string;
  interval_minutes: number;
  grace_minutes: number;
  paused: boolean;
  state: "paused" | "waiting" | "ok" | "late" | "fail";
  last_ping_at: string | null;
  last_ok_at: string | null;
  last_status: string;
  token: string | null;
}

export interface JobInput {
  name: string;
  interval_minutes: number;
  grace_minutes: number;
  paused: boolean;
}

export const useJobs = () =>
  useQuery({ queryKey: ["jobs"], queryFn: () => api<Job[]>("/jobs"), refetchInterval: 30_000 });

function useJobsDone() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["jobs"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };
}

export function useSaveJob() {
  const done = useJobsDone();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: JobInput }) =>
      id ? api<Job>(`/jobs/${id}`, { method: "PUT", body }) : api<Job>("/jobs", { method: "POST", body }),
    onSuccess: done,
  });
}

export function useDeleteJob() {
  const done = useJobsDone();
  return useMutation({ mutationFn: (id: string) => api<void>(`/jobs/${id}`, { method: "DELETE" }), onSuccess: done });
}

export function useNewJobToken() {
  const done = useJobsDone();
  return useMutation({ mutationFn: (id: string) => api<Job>(`/jobs/${id}/new-token`, { method: "POST" }), onSuccess: done });
}

// --- automatic backup ---
export interface BackupLocation {
  id?: string;
  name: string;
  type: "folder" | "webdav";
  path: string;
  url: string;
  username: string;
  has_password?: boolean;
  password?: string | null;
}

export interface AutoBackup {
  enabled: boolean;
  frequency: "daily" | "weekly";
  time: string;
  weekday: number;
  keep: number;
  has_passphrase: boolean;
  default_folder: string;
  locations: BackupLocation[];
  last: { at: number; ok: boolean; results: { name: string; ok: boolean; error?: string; size?: number }[] } | null;
}

export const useAutoBackup = () => useQuery({ queryKey: ["autobackup"], queryFn: () => api<AutoBackup>("/backup/auto") });

export function useSaveAutoBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Omit<AutoBackup, "has_passphrase" | "default_folder" | "last"> & { passphrase?: string }) =>
      api<AutoBackup>("/backup/auto", { method: "PUT", body }),
    onSuccess: (data) => { qc.setQueryData(["autobackup"], data); qc.invalidateQueries({ queryKey: ["overview"] }); },
  });
}

export function useRunAutoBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<AutoBackup>("/backup/auto/run", { method: "POST" }),
    onSuccess: (data) => { qc.setQueryData(["autobackup"], data); qc.invalidateQueries({ queryKey: ["overview"] }); },
  });
}

// --- update check ---
export interface UpdateInfo {
  enabled: boolean;
  current: string;
  latest: string | null;
  available: boolean;
  checked_at: number | null;
  error: string;
  url: string;
}

export const useUpdateInfo = (enabled = true) =>
  useQuery({ queryKey: ["update"], queryFn: () => api<UpdateInfo>("/update"), enabled, staleTime: 10 * 60_000 });

export function useCheckUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<UpdateInfo>("/update/check", { method: "POST" }),
    onSuccess: (data) => qc.setQueryData(["update"], data),
  });
}
