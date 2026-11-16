import "./Customers.css";
import { useState } from "react";
import { useCan } from "../api/users";
import { useJournal, useTicketActions, useTickets, type Ticket } from "../api/tickets";
import { ago } from "../components/format";
import { EntryText, PriorityBadge, StatusBadge, TicketDialog } from "./TicketParts";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Icon } from "../components/Icon";
import { Dot } from "../components/ui";
import type { Contact, Contract, Customer, CustomerInput } from "../api/data";
import { useAgents } from "../api/monitor";
import { useJobs } from "../api/ops";

export const WARN_DAYS = 60;

const day = (iso: string) => new Date(`${iso}T00:00:00`);
export const daysFrom = (iso: string) => Math.round((day(iso).getTime() - new Date().setHours(0, 0, 0, 0)) / 86_400_000);
export const fmtDate = (iso: string) => day(iso).toLocaleDateString();

/** "in 12 days" / "3 days ago" / "today" */
export function useRelDays() {
  const { t } = useTranslation();
  return (days: number) => days === 0 ? t("customers.today") : days > 0 ? t("customers.inDays", { count: days }) : t("customers.daysAgo", { count: -days });
}

/** State of the contract of a customer: warn when the notice deadline is near, down when it has passed. */
export function contractLevel(c: { contract: Contract | null }): "up" | "warn" | "down" | null {
  const k = c.contract;
  if (!k?.contract_end || !k.deadline) return null;
  if (daysFrom(k.contract_end) < 0) return null; // already ended: nothing to decide any more
  const d = daysFrom(k.deadline);
  return d < 0 ? "down" : d <= WARN_DAYS ? "warn" : "up";
}


// --- in the edit dialog ------------------------------------------------------------------------

export function ContactsEditor({ form, setForm }: { form: CustomerInput; setForm: (f: (x: CustomerInput) => CustomerInput) => void }) {
  const { t } = useTranslation();
  const set = (i: number, key: keyof Contact, v: string) =>
    setForm((f) => ({ ...f, contacts: f.contacts.map((c, j) => (j === i ? { ...c, [key]: v } : c)) }));
  return (
    <div className="field">
      {t("customers.contacts")}
      {form.contacts.length === 0 && <span className="hint">{t("customers.noContact")}</span>}
      {form.contacts.map((c, i) => (
        <div key={i} className="contact-edit">
          <input className="input" required maxLength={80} placeholder={t("customers.contactName")} value={c.name} onChange={(e) => set(i, "name", e.target.value)} />
          <input className="input" maxLength={60} placeholder={t("customers.contactRole")} value={c.role} onChange={(e) => set(i, "role", e.target.value)} />
          <input className="input" type="email" maxLength={120} placeholder={t("customers.email")} value={c.email} onChange={(e) => set(i, "email", e.target.value)} />
          <input className="input" type="tel" maxLength={40} placeholder={t("customers.phone")} value={c.phone} onChange={(e) => set(i, "phone", e.target.value)} />
          <button type="button" className="btn btn-ghost btn-small" aria-label={t("common.delete")}
                  onClick={() => setForm((f) => ({ ...f, contacts: f.contacts.filter((_, j) => j !== i) }))}>
            <Icon name="close" size={14} />
          </button>
        </div>
      ))}
      <div>
        <button type="button" className="btn btn-small" disabled={form.contacts.length >= 30}
                onClick={() => setForm((f) => ({ ...f, contacts: [...f.contacts, { name: "", role: "", email: "", phone: "" }] }))}>
          <Icon name="plus" size={14} /> {t("customers.addContact")}
        </button>
      </div>
    </div>
  );
}

export function ContractEditor({ form, setForm }: { form: CustomerInput; setForm: (f: (x: CustomerInput) => CustomerInput) => void }) {
  const { t } = useTranslation();
  const k: Contract = form.contract ?? { contract_end: null, notice_days: null, support_hours: "", response_time: "" };
  const set = (patch: Partial<Contract>) => setForm((f) => ({ ...f, contract: { ...k, ...patch } }));
  return (
    <fieldset className="field contract-edit">
      <legend>{t("customers.contractTitle")}</legend>
      <div className="grid-2">
        <label className="field">
          {t("customers.contractEnd")}
          <input className="input" type="date" value={k.contract_end ?? ""} onChange={(e) => set({ contract_end: e.target.value || null })} />
        </label>
        <label className="field">
          {t("customers.noticeDays")}
          <input className="input" type="number" min={0} max={3650} value={k.notice_days ?? ""}
                 onChange={(e) => set({ notice_days: e.target.value === "" ? null : Number(e.target.value) })} />
        </label>
        <label className="field">
          {t("customers.supportHours")}
          <input className="input" maxLength={120} placeholder={t("customers.supportHoursHint")} value={k.support_hours} onChange={(e) => set({ support_hours: e.target.value })} />
        </label>
        <label className="field">
          {t("customers.responseTime")}
          <input className="input" maxLength={60} placeholder={t("customers.responseTimeHint")} value={k.response_time} onChange={(e) => set({ response_time: e.target.value })} />
        </label>
      </div>
    </fieldset>
  );
}

/** Pick the servers and jobs that belong to the customer. */
export function AssignEditor({ form, setForm }: { form: CustomerInput; setForm: (f: (x: CustomerInput) => CustomerInput) => void }) {
  const { t } = useTranslation();
  const agents = useAgents().data?.filter((a) => !a.disabled) ?? [];
  const jobs = useJobs().data ?? [];
  const toggle = (key: "agent_ids" | "job_ids", id: string) =>
    setForm((f) => ({ ...f, [key]: f[key].includes(id) ? f[key].filter((x) => x !== id) : [...f[key], id] }));
  return (
    <>
      {agents.length > 0 && (
        <div className="field">
          {t("customers.serversTitle")}
          <div className="chips">
            {agents.map((a) => (
              <label key={a.id} className="chip check-chip">
                <input type="checkbox" checked={form.agent_ids.includes(a.id)} onChange={() => toggle("agent_ids", a.id)} />
                {a.name}
              </label>
            ))}
          </div>
          <span className="hint">{t("customers.assignHint")}</span>
        </div>
      )}
      {jobs.length > 0 && (
        <div className="field">
          {t("customers.jobsTitle")}
          <div className="chips">
            {jobs.map((j) => (
              <label key={j.id} className="chip check-chip">
                <input type="checkbox" checked={form.job_ids.includes(j.id)} onChange={() => toggle("job_ids", j.id)} />
                {j.name}
              </label>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

// --- on the customer page ----------------------------------------------------------------------

export function ContactsCard({ customer }: { customer: Customer }) {
  const { t } = useTranslation();
  const rows = customer.contacts;
  if (!rows.length && !customer.owner) return <div className="card card-pad"><span className="muted">{t("customers.noContact")}</span></div>;
  return (
    <div className="card list">
      {rows.map((p, i) => (
        <div key={i} className="list-row static-row">
          <div className="list-main">
            <div className="list-title">{p.name}{p.role && <span className="badge">{p.role}</span>}</div>
            <div className="list-sub">
              {p.email && <a href={`mailto:${p.email}`}>{p.email}</a>}
              {p.email && p.phone && " · "}
              {p.phone && <a href={`tel:${p.phone.replace(/\s/g, "")}`}>{p.phone}</a>}
            </div>
          </div>
        </div>
      ))}
      {customer.owner && (
        <div className="list-row static-row">
          <div className="list-main">
            <div className="list-sub">{t("customers.owner")}: {customer.owner}</div>
          </div>
        </div>
      )}
    </div>
  );
}

export function ContractCard({ customer }: { customer: Customer }) {
  const { t } = useTranslation();
  const rel = useRelDays();
  const k = customer.contract;
  if (!k || (!k.contract_end && !k.support_hours && !k.response_time && k.notice_days === null)) return null;
  const level = contractLevel(customer);
  const rows: [string, React.ReactNode][] = [];
  if (k.contract_end) {
    const ended = daysFrom(k.contract_end) < 0;
    rows.push([t("customers.contractEnd"), <>{fmtDate(k.contract_end)} <span className="muted">({ended ? t("customers.ended") : rel(daysFrom(k.contract_end))})</span></>]);
  }
  if (k.notice_days !== null) rows.push([t("customers.noticeDays"), t("customers.noticeValue", { count: k.notice_days })]);
  if (k.deadline && level) {
    rows.push([t("customers.noticeBy"), <><Dot state={level} /> {fmtDate(k.deadline)} <span className="muted">({rel(daysFrom(k.deadline))})</span></>]);
  }
  if (k.support_hours) rows.push([t("customers.supportHours"), k.support_hours]);
  if (k.response_time) rows.push([t("customers.responseTime"), k.response_time]);
  return (
    <>
      <h2 className="section-title">{t("customers.contractTitle")}</h2>
      <div className="card card-pad">
        <dl className="details">
          {rows.map(([a, b]) => <div key={a} style={{ display: "contents" }}><dt>{a}</dt><dd>{b}</dd></div>)}
        </dl>
      </div>
    </>
  );
}

export function AssignedCard({ customer }: { customer: Customer }) {
  const { t } = useTranslation();
  const agents = useAgents().data ?? [];
  const jobs = useJobs().data ?? [];
  const mineAgents = agents.filter((a) => customer.agent_ids.includes(a.id));
  const mineJobs = jobs.filter((j) => customer.job_ids.includes(j.id));
  if (!mineAgents.length && !mineJobs.length) return null;
  const page = (a: (typeof agents)[number]) => a.kind === "linux" ? `/servers/${a.id}` : a.kind === "proxmox" ? "/proxmox" : "/docker";
  return (
    <>
      <h2 className="section-title">{t("customers.serversTitle")} · {t("customers.jobsTitle")}</h2>
      <div className="card list">
        {mineAgents.map((a) => (
          <Link key={a.id} to={page(a)} className="list-row">
            <Dot state={a.last_report_at ? "up" : "off"} />
            <span className="list-main"><span className="list-title">{a.name}</span><span className="list-sub">{a.hostname}</span></span>
            <Icon name="chevron" size={16} />
          </Link>
        ))}
        {mineJobs.map((j) => (
          <Link key={j.id} to="/monitoring" className="list-row">
            <Dot state={j.state === "ok" || j.state === "waiting" ? "up" : j.state === "paused" ? "off" : "down"} />
            <span className="list-main"><span className="list-title">{j.name}</span><span className="list-sub">{t("customers.job")}</span></span>
            <Icon name="chevron" size={16} />
          </Link>
        ))}
      </div>
    </>
  );
}

export function TagsEditor({ form, setForm }: { form: CustomerInput; setForm: (f: (x: CustomerInput) => CustomerInput) => void }) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const add = () => {
    const tag = text.split(/\s+/).filter(Boolean).join(" ").slice(0, 30);
    if (tag && !form.tags.some((x) => x.toLowerCase() === tag.toLowerCase())) setForm((f) => ({ ...f, tags: [...f.tags, tag] }));
    setText("");
  };
  return (
    <div className="field">
      {t("customers.tags")}
      <div className="chips">
        {form.tags.map((x) => (
          <span key={x} className="chip">#{x}
            <button type="button" className="btn btn-ghost btn-small" aria-label={t("common.delete")} onClick={() => setForm((f) => ({ ...f, tags: f.tags.filter((y) => y !== x) }))}>×</button>
          </span>
        ))}
      </div>
      <input className="input" maxLength={30} placeholder={t("customers.tagPlaceholder")} value={text} onChange={(e) => setText(e.target.value)}
             onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }} onBlur={add} />
    </div>
  );
}

export function LinksEditor({ form, setForm }: { form: CustomerInput; setForm: (f: (x: CustomerInput) => CustomerInput) => void }) {
  const { t } = useTranslation();
  const set = (i: number, key: "title" | "url", v: string) =>
    setForm((f) => ({ ...f, links: f.links.map((l, j) => (j === i ? { ...l, [key]: v } : l)) }));
  return (
    <div className="field">
      {t("customers.links")}
      <span className="hint">{t("customers.linksHint")}</span>
      {form.links.map((l, i) => (
        <div key={i} className="link-edit">
          <input className="input" required maxLength={80} placeholder={t("customers.linkTitle")} value={l.title} onChange={(e) => set(i, "title", e.target.value)} />
          <input className="input" required type="url" maxLength={500} placeholder="https://…" value={l.url} onChange={(e) => set(i, "url", e.target.value)} />
          <button type="button" className="btn btn-ghost btn-small" aria-label={t("common.delete")}
                  onClick={() => setForm((f) => ({ ...f, links: f.links.filter((_, j) => j !== i) }))}><Icon name="close" size={14} /></button>
        </div>
      ))}
      <div>
        <button type="button" className="btn btn-small" disabled={form.links.length >= 30}
                onClick={() => setForm((f) => ({ ...f, links: [...f.links, { title: "", url: "" }] }))}>
          <Icon name="plus" size={14} /> {t("customers.addLink")}
        </button>
      </div>
    </div>
  );
}

export function LinksCard({ customer }: { customer: Customer }) {
  const { t } = useTranslation();
  if (!customer.links.length) return null;
  return (
    <>
      <h2 className="section-title">{t("customers.links")}</h2>
      <div className="card list">
        {customer.links.map((l, i) => (
          <a key={i} className="list-row" href={l.url} target="_blank" rel="noreferrer noopener">
            <span className="list-main"><span className="list-title">{l.title}</span><span className="list-sub">{l.url}</span></span>
            <Icon name="external" size={14} />
          </a>
        ))}
      </div>
    </>
  );
}

function TicketRow({ t: tk, onOpen }: { t: Ticket; onOpen: () => void }) {
  return (
    <button type="button" className="list-row ticket-row" onClick={onOpen}>
      <span className="list-main">
        <span className="list-title">#{tk.number} {tk.title}</span>
        <span className="list-sub">{[tk.assignee, tk.due && new Date(`${tk.due}T00:00:00`).toLocaleDateString()].filter(Boolean).join(" · ")}</span>
      </span>
      <span className="list-side"><PriorityBadge priority={tk.priority} /><StatusBadge status={tk.status} /></span>
    </button>
  );
}

/** The open tickets on the first tab (the most urgent few). */
export function OpenTickets({ customer, onAll }: { customer: Customer; onAll: () => void }) {
  const { t } = useTranslation();
  const tickets = useTickets("open", customer.id);
  const [open, setOpen] = useState<Ticket | null>(null);
  if (!tickets.data?.length) return null;
  return (
    <>
      <div className="section-row">
        <h2 className="section-title">{t("customers.tabs.tickets")}</h2>
        <button type="button" className="btn btn-ghost btn-small" onClick={onAll}>{t("customers.allTickets")}</button>
      </div>
      <div className="card list">{tickets.data.slice(0, 5).map((tk) => <TicketRow key={tk.id} t={tk} onOpen={() => setOpen(tk)} />)}</div>
      {open && <TicketDialog ticket={open} onClose={() => setOpen(null)} />}
    </>
  );
}

export function CustomerTickets({ customer }: { customer: Customer }) {
  const { t } = useTranslation();
  const can = useCan()("tickets.edit");
  const [filter, setFilter] = useState<"open" | "all">("open");
  const tickets = useTickets(filter, customer.id);
  const [open, setOpen] = useState<Ticket | null>(null);
  const [adding, setAdding] = useState(false);
  return (
    <>
      <div className="filters">
        <select className="input" value={filter} onChange={(e) => setFilter(e.target.value as "open" | "all")} aria-label={t("tickets.filter")}>
          <option value="open">{t("tickets.filterOpen")}</option>
          <option value="all">{t("tickets.filterAll")}</option>
        </select>
        <span className="spacer" />
        {can && <button type="button" className="btn btn-primary btn-small" onClick={() => setAdding(true)}><Icon name="plus" size={14} /> {t("tickets.add")}</button>}
      </div>
      {!tickets.data?.length ? <div className="card card-pad muted">{t("tickets.none")}</div>
        : <div className="card list">{tickets.data.map((tk) => <TicketRow key={tk.id} t={tk} onOpen={() => setOpen(tk)} />)}</div>}
      {open && <TicketDialog ticket={open} onClose={() => setOpen(null)} />}
      {adding && <TicketDialog ticket={null} customerId={customer.id} customerName={customer.name} onClose={() => setAdding(false)} />}
    </>
  );
}

/** Timeline of a customer: ticket comments, changes and free notes. */
export function CustomerJournal({ customer }: { customer: Customer }) {
  const { t } = useTranslation();
  const edit = useCan()("customers.edit");
  const [q, setQ] = useState("");
  const [text, setText] = useState("");
  const journal = useJournal(customer.id, q);
  const { note, removeEntry } = useTicketActions();
  return (
    <>
      {edit && (
        <form className="timeline-add" onSubmit={(e) => { e.preventDefault(); if (text.trim()) note.mutate({ customer: customer.id, text: text.trim() }, { onSuccess: () => setText("") }); }}>
          <textarea className="input" rows={2} maxLength={10000} placeholder={t("customers.notePlaceholder")} value={text} onChange={(e) => setText(e.target.value)} />
          <button type="submit" className="btn btn-primary btn-small" disabled={!text.trim() || note.isPending}>{t("customers.addNote")}</button>
        </form>
      )}
      <div className="filters">
        <input className="input" type="search" placeholder={t("customers.searchHistory")} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {!journal.data?.length ? <div className="card card-pad muted">{t("customers.noHistory")}</div> : (
        <div className="card">
          <ul className="entry-list timeline">
            {journal.data.map((e) => (
              <li key={e.id} className={`entry entry-${e.kind}`}>
                <div className="entry-meta">
                  <b>{e.author}</b> · {ago(Date.parse(e.created_at) / 1000)}
                  {e.ticket !== null && <> · <Link to={`/tickets?open=${e.ticket_id}`}>#{e.ticket} {e.ticket_title}</Link></>}
                  {edit && e.kind === "note" && <button type="button" className="btn btn-ghost btn-small" aria-label={t("common.delete")} onClick={() => removeEntry.mutate(e.id)}><Icon name="close" size={12} /></button>}
                </div>
                <div className="entry-text"><EntryText e={e} /></div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
