import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "./client";

export interface AppStatus {
  name: string;
  version: string;
  needs_setup: boolean;
}

export interface User {
  id: number;
  username: string;
  role: string;
  role_name: string;
  permissions: string[];
}

export interface Credentials {
  username: string;
  password: string;
}

export function useAppStatus() {
  return useQuery({ queryKey: ["status"], queryFn: () => api<AppStatus>("/status"), staleTime: 60_000 });
}

/** The logged-in user, or null when not logged in. */
export function useMe(enabled = true) {
  return useQuery({
    queryKey: ["me"],
    enabled,
    retry: false,
    queryFn: async () => {
      try {
        return await api<User>("/auth/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
  });
}

export type LoginResult = User | { totp_required: true; ticket: string };

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials) => api<LoginResult>("/auth/login", { method: "POST", body }),
    onSuccess: (result) => {
      if (!("totp_required" in result)) qc.setQueryData(["me"], result);
    },
  });
}

export function useLoginSecondFactor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { ticket: string; code: string }) => api<User>("/auth/login/2fa", { method: "POST", body }),
    onSuccess: (user) => qc.setQueryData(["me"], user),
  });
}

export function useSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials & { code: string }) => api<User>("/setup", { method: "POST", body }),
    onSuccess: (user) => {
      qc.setQueryData(["me"], user);
      qc.invalidateQueries({ queryKey: ["status"] });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/auth/logout", { method: "POST" }),
    onSettled: () => {
      qc.clear();
      qc.setQueryData(["me"], null);
    },
  });
}
