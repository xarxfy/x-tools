import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface Port {
  port: number;
  label: string;
}

export interface ServiceInput {
  name: string;
  domains: string[];
  ports: Port[];
  folder: string;
  type: string;
  notes: string;
  customer_id: string | null;
}

export interface Service extends ServiceInput {
  id: string;
  customer_name: string | null;
  credential_count: number;
}

export interface Credential {
  label: string;
  username: string;
  password: string;
  url: string;
  note: string;
}

export interface CustomerInput {
  name: string;
  contact: string;
  email: string;
  phone: string;
  owner: string;
  agreements: string;
  notes: string;
  service_ids: string[];
}

export interface Customer extends CustomerInput {
  id: string;
}

export const useServices = () => useQuery({ queryKey: ["services"], queryFn: () => api<Service[]>("/services") });

export const usePortStatus = () =>
  useQuery({
    queryKey: ["ports"],
    queryFn: () => api<Record<string, boolean>>("/services/ports"),
    refetchInterval: 60_000,
  });

export const useCustomers = () => useQuery({ queryKey: ["customers"], queryFn: () => api<Customer[]>("/customers") });

export const useCredentials = (serviceId: string | null) =>
  useQuery({
    queryKey: ["credentials", serviceId],
    enabled: !!serviceId,
    staleTime: 0,
    gcTime: 0, // do not keep decrypted passwords around in the cache
    queryFn: () => api<Credential[]>(`/services/${serviceId}/credentials`),
  });

/** Invalidates everything that shows services or customers after a change. */
function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["services"] });
    qc.invalidateQueries({ queryKey: ["customers"] });
    qc.invalidateQueries({ queryKey: ["ports"] });
  };
}

export function useSaveService() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: ServiceInput }) =>
      id ? api<Service>(`/services/${id}`, { method: "PUT", body }) : api<Service>("/services", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export function useDeleteService() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/services/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}

export function useSaveCredentials() {
  const invalidate = useInvalidate();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Credential[] }) =>
      api<Credential[]>(`/services/${id}/credentials`, { method: "PUT", body }),
    onSuccess: (data, { id }) => {
      qc.setQueryData(["credentials", id], data);
      invalidate();
    },
  });
}

export function useSaveCustomer() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: CustomerInput }) =>
      id
        ? api<Customer>(`/customers/${id}`, { method: "PUT", body })
        : api<Customer>("/customers", { method: "POST", body }),
    onSuccess: invalidate,
  });
}

export function useDeleteCustomer() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/customers/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
}
