import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export const STATUSES = ["open", "progress", "waiting", "done"] as const;
export const PRIORITIES = ["low", "normal", "high", "urgent"] as const;
export type TicketStatus = (typeof STATUSES)[number];
export type TicketPriority = (typeof PRIORITIES)[number];

export interface Ticket {
  id: string;
  number: number;
  customer_id: string;
  customer: string;
  title: string;
  description: string;
  status: TicketStatus;
  priority: TicketPriority;
  due: string | null;
  assignee_id: number | null;
  assignee: string | null;
  service_id: string | null;
  agent_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export type TicketInput = Pick<Ticket, "title" | "description" | "status" | "priority" | "due" | "assignee_id" | "service_id" | "agent_id">;

export interface JournalEntry {
  id: string;
  ticket_id: string | null;
  ticket: number | null;
  ticket_title: string | null;
  kind: "note" | "event";
  text: string;
  author: string;
  created_at: string;
}

export interface TicketDetail extends Ticket {
  entries: JournalEntry[];
}

export const useTickets = (status: "open" | "all" | "done" = "open", customer?: string) =>
  useQuery({
    queryKey: ["tickets", status, customer ?? ""],
    queryFn: () => api<Ticket[]>(`/tickets?status=${status}${customer ? `&customer=${customer}` : ""}`),
    refetchInterval: 60_000,
  });

export const useTicket = (id: string | null) =>
  useQuery({ queryKey: ["ticket", id], enabled: !!id, queryFn: () => api<TicketDetail>(`/tickets/${id}`) });

export const useAssignees = () =>
  useQuery({ queryKey: ["assignees"], queryFn: () => api<{ id: number; username: string }[]>("/tickets/assignees"), staleTime: 60_000 });

export const useJournal = (customer: string, q: string) =>
  useQuery({ queryKey: ["journal", customer, q], queryFn: () => api<JournalEntry[]>(`/customers/${customer}/journal?q=${encodeURIComponent(q)}`) });

/** Everything that shows tickets, the journal or the counts on customers and the overview. */
function useRefresh() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["tickets", "ticket", "journal", "customers", "overview"]) qc.invalidateQueries({ queryKey: [key] });
  };
}

export function useTicketActions() {
  const refresh = useRefresh();
  const create = useMutation({
    mutationFn: ({ customer, body }: { customer: string; body: TicketInput }) =>
      api<Ticket>(`/customers/${customer}/tickets`, { method: "POST", body }),
    onSuccess: refresh,
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: TicketInput }) => api<Ticket>(`/tickets/${id}`, { method: "PUT", body }),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (id: string) => api<void>(`/tickets/${id}`, { method: "DELETE" }), onSuccess: refresh });
  const comment = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) => api<JournalEntry>(`/tickets/${id}/comments`, { method: "POST", body: { text } }),
    onSuccess: refresh,
  });
  const note = useMutation({
    mutationFn: ({ customer, text }: { customer: string; text: string }) =>
      api<JournalEntry>(`/customers/${customer}/journal`, { method: "POST", body: { text } }),
    onSuccess: refresh,
  });
  const removeEntry = useMutation({ mutationFn: (id: string) => api<void>(`/journal/${id}`, { method: "DELETE" }), onSuccess: refresh });
  return { create, update, remove, comment, note, removeEntry };
}
