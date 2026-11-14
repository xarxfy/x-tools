import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface Account {
  username: string;
  role: string;
  totp_enabled: boolean;
  recovery_codes_left: number;
}

export const useAccount = () => useQuery({ queryKey: ["account"], queryFn: () => api<Account>("/account") });

export const useChangePassword = () =>
  useMutation({
    mutationFn: (body: { current: string; new: string }) => api<void>("/account/password", { method: "POST", body }),
  });

export const useSetup2fa = () =>
  useMutation({ mutationFn: () => api<{ secret: string; uri: string }>("/account/2fa/setup", { method: "POST" }) });

function useAccountMutation<T, B>(path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: B) => api<T>(path, { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["account"] }),
  });
}

export const useEnable2fa = () => useAccountMutation<{ recovery_codes: string[] }, { code: string }>("/account/2fa/enable");
export const useDisable2fa = () => useAccountMutation<void, { password: string; code: string }>("/account/2fa/disable");
export const useNewRecoveryCodes = () =>
  useAccountMutation<{ recovery_codes: string[] }, { code: string }>("/account/2fa/recovery-codes");

/** Download an encrypted backup (the browser saves the file). */
export async function downloadBackup(passphrase: string): Promise<void> {
  const csrf = document.cookie.match(/(?:^|;\s*)xt_csrf=([^;]+)/)?.[1] ?? "";
  const res = await fetch("/api/backup", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": decodeURIComponent(csrf) },
    body: JSON.stringify({ passphrase }),
  });
  if (!res.ok) {
    let message = `Backup failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail[0]?.msg ?? message;
    } catch {
      /* not JSON */
    }
    throw new Error(message);
  }
  const name = res.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] ?? "x-tools-backup.xtb";
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function restoreBackup(file: File, passphrase: string): Promise<void> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  await api<void>("/backup/restore", { method: "POST", body: { passphrase, data: btoa(binary) } });
}

export interface HistoryEvent {
  id: number;
  key: string;
  kind: string;
  level: "down" | "warn";
  text: string;
  link: string;
  started_at: string;
  ended_at: string | null;
}

export interface MetricPoint {
  ts: string;
  load: number | null;
  mem: number | null;
  disk: number | null;
}

export const useEvents = (days = 7, limit = 20) =>
  useQuery({
    queryKey: ["history", "events", days, limit],
    queryFn: () => api<HistoryEvent[]>(`/history/events?days=${days}&limit=${limit}`),
    refetchInterval: 60_000,
  });

export const useUptime = () =>
  useQuery({ queryKey: ["history", "uptime"], queryFn: () => api<Record<string, number>>("/history/uptime"), refetchInterval: 300_000 });

export const useMetrics = (source: string, hours: number) =>
  useQuery({
    queryKey: ["history", "metrics", source, hours],
    queryFn: () => api<MetricPoint[]>(`/history/metrics?source=${encodeURIComponent(source)}&hours=${hours}`),
    refetchInterval: 300_000,
  });
