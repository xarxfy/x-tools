import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { useMe } from "./auth";

export type Role = "viewer" | "operator" | "admin";
const RANK: Record<string, number> = { viewer: 0, operator: 1, admin: 2 };

/** can("operator") → true for operators and admins. */
export function useCan() {
  const { data: me } = useMe();
  return (role: Role) => !!me && (RANK[me.role] ?? -1) >= RANK[role];
}

export interface UserRow {
  id: number;
  username: string;
  role: Role;
  disabled: boolean;
  totp_enabled: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AuditEntry {
  id: number;
  ts: string;
  username: string;
  action: string;
  target: string;
  detail: string;
  ip: string;
}

export const useUsers = () => useQuery({ queryKey: ["users"], queryFn: () => api<UserRow[]>("/users") });

function useUserMutation<B>(fn: (body: B) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

export const useCreateUser = () =>
  useUserMutation((body: { username: string; role: Role; password: string }) => api<UserRow>("/users", { method: "POST", body }));
export const useUpdateUser = () =>
  useUserMutation(({ id, ...body }: { id: number; role?: Role; disabled?: boolean }) =>
    api<UserRow>(`/users/${id}`, { method: "PUT", body }));
export const useResetPassword = () =>
  useUserMutation(({ id, password }: { id: number; password: string }) =>
    api<void>(`/users/${id}/password`, { method: "POST", body: { password } }));
export const useReset2fa = () => useUserMutation((id: number) => api<void>(`/users/${id}/reset-2fa`, { method: "POST" }));
export const useDeleteUser = () => useUserMutation((id: number) => api<void>(`/users/${id}`, { method: "DELETE" }));

const PAGE = 50;

export function useAudit(user: string, action: string) {
  return useInfiniteQuery({
    queryKey: ["audit", user, action],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => {
      const q = new URLSearchParams({ limit: String(PAGE) });
      if (pageParam) q.set("before", String(pageParam));
      if (user) q.set("user", user);
      if (action) q.set("action", action);
      return api<AuditEntry[]>(`/audit?${q}`);
    },
    getNextPageParam: (last) => (last.length === PAGE ? last[last.length - 1].id : undefined),
  });
}

export const useAuditFilters = () =>
  useQuery({
    queryKey: ["audit", "filters"],
    queryFn: async () => ({
      actions: await api<string[]>("/audit/actions"),
      users: await api<string[]>("/users/names"),
    }),
  });
