import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export interface Port {
  port: number;
  label: string;
}

export interface ChecklistItem {
  text: string;
  done: boolean;
}

export interface ServiceInput {
  checklist?: ChecklistItem[];
  name: string;
  host: string;
  domains: string[];
  ports: Port[];
  folder: string;
  type: string;
  notes: string;
  customer_id: string | null;
}

export interface Service extends ServiceInput {
  id: string;
  checklist: ChecklistItem[];
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

export interface Contact {
  name: string;
  role: string;
  email: string;
  phone: string;
}

export interface Contract {
  contract_end: string | null;
  notice_days: number | null;
  support_hours: string;
  response_time: string;
  /** Last day to give notice (end minus period of notice); computed by the server. */
  deadline?: string | null;
}

export interface CustomerTask {
  id: string;
  title: string;
  due: string | null;
  done: boolean;
}

export interface CustomerInput {
  name: string;
  owner: string;
  agreements: string;
  notes: string;
  category_id: string | null;
  service_ids: string[];
  agent_ids: string[];
  job_ids: string[];
  contacts: Contact[];
  /** null: the role may not see contract data (the server leaves it unchanged) */
  contract: Contract | null;
}

export interface Customer extends CustomerInput {
  id: string;
  tasks: CustomerTask[];
}

export function useCustomerTasks() {
  const qc = useQueryClient();
  const done = () => {
    qc.invalidateQueries({ queryKey: ["customers"] });
    qc.invalidateQueries({ queryKey: ["overview"] });
  };
  const add = useMutation({
    mutationFn: ({ customer, title, due }: { customer: string; title: string; due: string | null }) =>
      api<CustomerTask>(`/customers/${customer}/tasks`, { method: "POST", body: { title, due } }),
    onSuccess: done,
  });
  const update = useMutation({
    mutationFn: (t: CustomerTask) => api<CustomerTask>(`/customer-tasks/${t.id}`, { method: "PUT", body: t }),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/customer-tasks/${id}`, { method: "DELETE" }),
    onSuccess: done,
  });
  return { add, update, remove };
}

/** Key of a port in the port status: "8080" on the X-TOOLS host, "10.0.0.5:8080" elsewhere. */
export const portKey = (host: string, port: number) => (host ? `${host}:${port}` : String(port));

export const useServices = () => useQuery({ queryKey: ["services"], queryFn: () => api<Service[]>("/services") });

export const usePortStatus = () =>
  useQuery({
    queryKey: ["ports"],
    queryFn: () => api<Record<string, boolean>>("/services/ports"),
    refetchInterval: 60_000,
  });

export interface Category {
  id: string;
  name: string;
  position: number;
}

export const useCategories = () =>
  useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/customer-categories") });

export function useCategoryActions() {
  const qc = useQueryClient();
  const done = () => {
    qc.invalidateQueries({ queryKey: ["categories"] });
    qc.invalidateQueries({ queryKey: ["customers"] });
  };
  const add = useMutation({
    mutationFn: (name: string) => api<Category>("/customer-categories", { method: "POST", body: { name } }),
    onSuccess: done,
  });
  const rename = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api<Category>(`/customer-categories/${id}`, { method: "PUT", body: { name } }),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/customer-categories/${id}`, { method: "DELETE" }),
    onSuccess: done,
  });
  const order = useMutation({
    mutationFn: (ids: string[]) => api<Category[]>("/customer-categories/order", { method: "PUT", body: { ids } }),
    onSuccess: done,
  });
  return { add, rename, remove, order };
}

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
