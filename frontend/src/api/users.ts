import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { useMe } from "./auth";

/** can("services.edit") → true when the role of the logged-in user has this permission. */
export function useCan() {
  const { data: me } = useMe();
  return (permission: string) => !!me && (me.permissions ?? []).includes(permission);
}

export interface RoleRow {
  id: string;
  name: string;
  builtin: boolean;
  locked: boolean;
  permissions: string[];
  users: number;
}

export interface RolesData {
  roles: RoleRow[];
  permissions: { key: string; area: string }[];
  areas: string[];
}

export const useRoles = (enabled = true) =>
  useQuery({ queryKey: ["roles"], queryFn: () => api<RolesData>("/roles"), enabled });

export function useRoleActions() {
  const qc = useQueryClient();
  const done = () => {
    qc.invalidateQueries({ queryKey: ["roles"] });
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["me"] });
  };
  const save = useMutation({
    mutationFn: ({ id, name, permissions }: { id?: string; name: string; permissions: string[] }) =>
      id ? api<RoleRow>(`/roles/${id}`, { method: "PUT", body: { name, permissions } })
        : api<RoleRow>("/roles", { method: "POST", body: { name, permissions } }),
    onSuccess: done,
  });
  const remove = useMutation({ mutationFn: (id: string) => api<void>(`/roles/${id}`, { method: "DELETE" }), onSuccess: done });
  return { save, remove };
}

export interface UserRow {
  id: number;
  username: string;
  role: string;
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
  useUserMutation((body: { username: string; role: string; password: string }) => api<UserRow>("/users", { method: "POST", body }));
export const useUpdateUser = () =>
  useUserMutation(({ id, ...body }: { id: number; role?: string; disabled?: boolean }) =>
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
