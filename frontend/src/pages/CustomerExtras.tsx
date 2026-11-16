import "./Customers.css";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Icon } from "../components/Icon";
import { Dot } from "../components/ui";
import { useCustomerTasks, type Contact, type Contract, type Customer, type CustomerInput } from "../api/data";
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

export function openTasks(c: Customer) {
  return c.tasks.filter((t) => !t.done);
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

export function TasksCard({ customer, edit }: { customer: Customer; edit: boolean }) {
  const { t } = useTranslation();
  const rel = useRelDays();
  const { add, update, remove } = useCustomerTasks();
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  if (!edit && !customer.tasks.length) return null;
  const error = add.error ?? update.error ?? remove.error;
  return (
    <>
      <h2 className="section-title">{t("customers.tasksTitle")}</h2>
      <div className="card">
        {customer.tasks.length > 0 && (
          <ul className="task-list">
            {customer.tasks.map((k) => {
              const late = !k.done && k.due && daysFrom(k.due) < 0;
              return (
                <li key={k.id} className={k.done ? "is-done" : undefined}>
                  <input type="checkbox" checked={k.done} disabled={!edit} aria-label={k.title}
                         onChange={(e) => update.mutate({ ...k, done: e.target.checked })} />
                  <span className="task-title">{k.title}</span>
                  {k.due && <span className={`badge${late ? " badge-warn" : ""}`}>{fmtDate(k.due)}{!k.done && ` · ${rel(daysFrom(k.due))}`}</span>}
                  {edit && (
                    <button type="button" className="btn btn-ghost btn-small" aria-label={t("common.delete")} onClick={() => remove.mutate(k.id)}>
                      <Icon name="close" size={14} />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {edit && (
          <form className="task-add card-pad" onSubmit={(e) => {
            e.preventDefault();
            if (title.trim()) add.mutate({ customer: customer.id, title: title.trim(), due: due || null }, { onSuccess: () => { setTitle(""); setDue(""); } });
          }}>
            <input className="input" maxLength={200} placeholder={t("customers.taskPlaceholder")} value={title} onChange={(e) => setTitle(e.target.value)} />
            <input className="input task-due" type="date" aria-label={t("customers.taskDue")} value={due} onChange={(e) => setDue(e.target.value)} />
            <button type="submit" className="btn btn-small" disabled={!title.trim() || add.isPending}>{t("customers.addTask")}</button>
          </form>
        )}
        {error && <p className="error-text card-pad">{error.message}</p>}
      </div>
    </>
  );
}
