import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog, ConfirmDelete } from "../components/ui";
import { useCan } from "../api/users";
import { useServices } from "../api/data";
import { useAgents } from "../api/monitor";
import {
  PRIORITIES, STATUSES, useAssignees, useTicket, useTicketActions,
  type JournalEntry, type Ticket, type TicketInput,
} from "../api/tickets";
import { ago } from "../components/format";
import { NoteText } from "../components/NoteText";
import "./Tickets.css";

const dayStart = () => new Date().setHours(0, 0, 0, 0);
export const daysUntil = (iso: string) => Math.round((new Date(`${iso}T00:00:00`).getTime() - dayStart()) / 86_400_000);

export function StatusBadge({ status }: { status: Ticket["status"] }) {
  const { t } = useTranslation();
  return <span className={`badge ticket-status st-${status}`}>{t(`tickets.status.${status}`)}</span>;
}

export function PriorityBadge({ priority }: { priority: Ticket["priority"] }) {
  const { t } = useTranslation();
  return <span className={`badge ticket-prio pr-${priority}`}>{t(`tickets.priority.${priority}`)}</span>;
}

export function DueBadge({ ticket }: { ticket: Pick<Ticket, "due" | "status"> }) {
  const { t } = useTranslation();
  if (!ticket.due) return <span className="muted">–</span>;
  const late = ticket.status !== "done" && daysUntil(ticket.due) < 0;
  return <span className={late ? "due-late" : undefined}>{new Date(`${ticket.due}T00:00:00`).toLocaleDateString()}{late && ` · ${t("tickets.overdue")}`}</span>;
}

/** What a change in the history says ("status: open > done"). */
export function EntryText({ e }: { e: JournalEntry }) {
  const { t } = useTranslation();
  if (e.kind === "note") return <NoteText text={e.text} />;
  const [what, value] = e.text.split(/:(.*)/s);
  if (e.text === "created") return <>{t("tickets.ev.created")}</>;
  if (what === "status") { const [a, b] = value.split(">"); return <>{t("tickets.ev.status", { from: t(`tickets.status.${a}`), to: t(`tickets.status.${b}`) })}</>; }
  if (what === "priority") { const [a, b] = value.split(">"); return <>{t("tickets.ev.priority", { from: t(`tickets.priority.${a}`), to: t(`tickets.priority.${b}`) })}</>; }
  if (what === "assignee") return <>{value === "-" ? t("tickets.ev.unassigned") : t("tickets.ev.assignee", { name: value })}</>;
  return <>{e.text}</>;
}

/** Create or edit a ticket; for an existing one the comments are shown and can be added. */
export function TicketDialog({ ticket, customerId, customerName, onClose }: {
  ticket: Ticket | null; customerId?: string; customerName?: string; onClose: () => void;
}) {
  const { t } = useTranslation();
  const can = useCan()("tickets.edit");
  const { create, update, remove, comment } = useTicketActions();
  const detail = useTicket(ticket?.id ?? null);
  const assignees = useAssignees().data ?? [];
  const services = (useServices().data ?? []).filter((s) => s.customer_id === (ticket?.customer_id ?? customerId));
  const agents = (useAgents().data ?? []).filter((a) => !a.disabled);
  const [form, setForm] = useState<TicketInput>(() => ticket
    ? { title: ticket.title, description: ticket.description, status: ticket.status, priority: ticket.priority, due: ticket.due,
        assignee_id: ticket.assignee_id, service_id: ticket.service_id, agent_id: ticket.agent_id }
    : { title: "", description: "", status: "open", priority: "normal", due: null, assignee_id: null, service_id: null, agent_id: null });
  const [text, setText] = useState("");
  const set = <K extends keyof TicketInput>(k: K, v: TicketInput[K]) => setForm((f) => ({ ...f, [k]: v }));
  const busy = create.isPending || update.isPending;
  const error = create.error ?? update.error ?? remove.error ?? comment.error;
  const save = () => {
    const done = { onSuccess: () => onClose() };
    if (ticket) update.mutate({ id: ticket.id, body: form }, done);
    else if (customerId) create.mutate({ customer: customerId, body: form }, done);
  };
  return (
    <Dialog wide onClose={onClose} onSubmit={can ? save : undefined}
            title={ticket ? `#${ticket.number} · ${ticket.customer}` : t("tickets.new", { customer: customerName ?? "" })}
            footer={<>
              {ticket && can && <ConfirmDelete busy={remove.isPending} onConfirm={() => remove.mutate(ticket.id, { onSuccess: () => onClose() })} />}
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{can ? t("common.cancel") : t("common.close")}</button>
              {can && <button type="submit" className="btn btn-primary" disabled={busy || !form.title.trim()}>{t("common.save")}</button>}
            </>}>
      <label className="field">
        {t("tickets.title")}
        <input className="input" required maxLength={200} autoFocus={!ticket} disabled={!can} value={form.title} onChange={(e) => set("title", e.target.value)} />
      </label>
      <div className="grid-2">
        <label className="field">
          {t("tickets.statusLabel")}
          <select className="input" disabled={!can} value={form.status} onChange={(e) => set("status", e.target.value as TicketInput["status"])}>
            {STATUSES.map((s) => <option key={s} value={s}>{t(`tickets.status.${s}`)}</option>)}
          </select>
        </label>
        <label className="field">
          {t("tickets.priorityLabel")}
          <select className="input" disabled={!can} value={form.priority} onChange={(e) => set("priority", e.target.value as TicketInput["priority"])}>
            {PRIORITIES.map((s) => <option key={s} value={s}>{t(`tickets.priority.${s}`)}</option>)}
          </select>
        </label>
        <label className="field">
          {t("tickets.assignee")}
          <select className="input" disabled={!can} value={form.assignee_id ?? ""} onChange={(e) => set("assignee_id", e.target.value ? Number(e.target.value) : null)}>
            <option value="">{t("tickets.unassigned")}</option>
            {assignees.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
          </select>
        </label>
        <label className="field">
          {t("tickets.due")}
          <input className="input" type="date" disabled={!can} value={form.due ?? ""} onChange={(e) => set("due", e.target.value || null)} />
        </label>
        <label className="field">
          {t("tickets.service")}
          <select className="input" disabled={!can} value={form.service_id ?? ""} onChange={(e) => set("service_id", e.target.value || null)}>
            <option value="">–</option>
            {services.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </label>
        <label className="field">
          {t("tickets.server")}
          <select className="input" disabled={!can} value={form.agent_id ?? ""} onChange={(e) => set("agent_id", e.target.value || null)}>
            <option value="">–</option>
            {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
      </div>
      <label className="field">
        {t("tickets.description")}
        <textarea className="input" rows={4} maxLength={10000} disabled={!can} value={form.description} onChange={(e) => set("description", e.target.value)} />
      </label>
      {ticket && (
        <div className="field">
          {t("tickets.history")}
          <ul className="entry-list">
            {(detail.data?.entries ?? []).map((e) => (
              <li key={e.id} className={`entry entry-${e.kind}`}>
                <div className="entry-meta"><b>{e.author}</b> · {ago(Date.parse(e.created_at) / 1000)}</div>
                <div className="entry-text"><EntryText e={e} /></div>
              </li>
            ))}
          </ul>
          {can && (
            <div className="entry-add">
              <textarea className="input" rows={2} maxLength={10000} placeholder={t("tickets.commentPlaceholder")} value={text} onChange={(e) => setText(e.target.value)} />
              <button type="button" className="btn btn-small" disabled={!text.trim() || comment.isPending}
                      onClick={() => comment.mutate({ id: ticket.id, text: text.trim() }, { onSuccess: () => setText("") })}>{t("tickets.addComment")}</button>
            </div>
          )}
        </div>
      )}
      {error && <p className="error-text">{error.message}</p>}
    </Dialog>
  );
}
