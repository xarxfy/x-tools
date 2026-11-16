import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  useCategories, useCategoryActions, useCustomers, useDeleteCustomer, usePortStatus, useSaveCustomer, useServices,
  type Customer, type CustomerInput,
} from "../api/data";
import { ReportDialog } from "../components/ReportDialog";
import { Icon } from "../components/Icon";
import { AssignEditor, AssignedCard, ContactsCard, ContactsEditor, ContractCard, ContractEditor, TasksCard, contractLevel, openTasks } from "./CustomerExtras";
import { ConfirmDelete, Dialog, Dot, Empty, Loading, PageHead, SearchField, matches } from "../components/ui";
import { CredentialsDialog } from "./CredentialsPage";
import { ServiceDialog, serviceState } from "./ServicesPage";
import type { Service } from "../api/data";
import { useRunSiteChecks, useSiteChecks, type SiteCheck } from "../api/monitor";
import { ago } from "../components/format";
import { useCan } from "../api/users";
import { SitesSection } from "./SitesSection";
import { NoteText } from "../components/NoteText";

function worst(checks: (SiteCheck | undefined)[]): "up" | "warn" | "down" | "off" {
  const levels = checks.map((c) => c?.level).filter(Boolean);
  if (!levels.length) return "off";
  return levels.includes("down") ? "down" : levels.includes("warn") ? "warn" : "up";
}

const EMPTY: CustomerInput = {
  name: "", owner: "", agreements: "", notes: "", category_id: null, service_ids: [], agent_ids: [], job_ids: [], contacts: [], contract: null,
};

export function CustomersPage() {
  const { t } = useTranslation();
  const customers = useCustomers();
  const services = useServices();
  const checks = useSiteChecks();
  const [query, setQuery] = useState("");
  const categories = useCategories().data ?? [];
  const [category, setCategory] = useState("");
  const [adding, setAdding] = useState(false);
  const [managing, setManaging] = useState(false);
  const navigate = useNavigate();
  const edit = useCan()("customers.edit");

  if (!customers.data) return <Loading error={customers.error} retry={() => customers.refetch()} />;
  const byId = new Map((services.data ?? []).map((s) => [s.id, s]));
  const rank = new Map(categories.map((c, i) => [c.id, i]));
  const catName = new Map(categories.map((c) => [c.id, c.name]));
  const list = customers.data
    .filter((c) => !category || (category === "none" ? !c.category_id : c.category_id === category))
    .filter((c) => matches(query, c.name, ...c.contacts.flatMap((p) => [p.name, p.email]), ...c.service_ids.flatMap((id) => byId.get(id)?.domains ?? [])))
    .sort((a, b) => (rank.get(a.category_id ?? "") ?? 999) - (rank.get(b.category_id ?? "") ?? 999) || a.name.localeCompare(b.name));

  return (
    <>
      <PageHead title={t("nav.customers")} sub={t("customers.sub", { count: customers.data.length })}>
        <SearchField value={query} onChange={setQuery} />
        {edit && (
          <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
            <Icon name="plus" size={16} />
            {t("customers.add")}
          </button>
        )}
      </PageHead>
      {(categories.length > 0 || edit) && (
        <div className="category-bar">
          {categories.length > 0 && (
            <>
              <button type="button" className={`category-pill${category === "" ? " active" : ""}`} onClick={() => setCategory("")}>{t("customers.allCategories")}</button>
              {categories.map((c) => (
                <button key={c.id} type="button" className={`category-pill${category === c.id ? " active" : ""}`} onClick={() => setCategory(c.id)}>{c.name}</button>
              ))}
              <button type="button" className={`category-pill${category === "none" ? " active" : ""}`} onClick={() => setCategory("none")}>{t("customers.noCategory")}</button>
            </>
          )}
          {edit && <button type="button" className="btn btn-ghost btn-small" onClick={() => setManaging(true)}>{t("customers.manageCategories")}</button>}
        </div>
      )}
      {list.length === 0 ? (
        <Empty>{customers.data.length ? t("common.noMatch") : t("customers.empty")}</Empty>
      ) : (
        <div className="card list">
          {list.map((c) => {
            const domains = c.service_ids.flatMap((id) => byId.get(id)?.domains ?? []);
            return (
              <Link key={c.id} to={`/customers/${c.id}`} className="list-row">
                <Dot state={worst(domains.map((d) => checks.data?.[d]))} />
                <span className="list-main">
                  <span className="list-title">{c.name}{c.category_id && catName.get(c.category_id) && <span className="badge category-badge">{catName.get(c.category_id)}</span>}</span>
                  <span className="list-sub">
                    {[c.contacts[0]?.name, domains.slice(0, 3).join(", ")].filter(Boolean).join(" · ") || t("customers.noDetails")}
                  </span>
                </span>
                <span className="list-side">
                  {contractLevel(c) === "warn" || contractLevel(c) === "down" ? <span className="badge badge-warn">{t("customers.deadlineBadge")}</span> : null}
                  {openTasks(c).length > 0 && <span className="badge">{t("customers.tasksOpen", { count: openTasks(c).length })}</span>}
                  <span className="badge">{t("customers.services", { count: c.service_ids.length })}</span>
                  <Icon name="chevron" size={16} />
                </span>
              </Link>
            );
          })}
        </div>
      )}
      {managing && <CategoryDialog onClose={() => setManaging(false)} />}
      {adding && (
        <CustomerDialog customer={null} onClose={() => setAdding(false)}
                        onSaved={(c) => navigate(`/customers/${c.id}`)} />
      )}
    </>
  );
}

export function CustomerPage() {
  const { id } = useParams();
  const { t } = useTranslation();
  const customers = useCustomers();
  const services = useServices();
  const ports = usePortStatus();
  const [editing, setEditing] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [service, setService] = useState<Service | null>(null);
  const [keys, setKeys] = useState<Service | null>(null);
  const checks = useSiteChecks();
  const runChecks = useRunSiteChecks();
  const can = useCan();
  const edit = can("customers.edit");
  const categories = useCategories().data ?? [];

  if (!customers.data) return <Loading error={customers.error} retry={() => customers.refetch()} />;
  const customer = customers.data.find((c) => c.id === id);
  if (!customer) {
    return (
      <div className="center-state">
        <div>
          <h1>{t("customers.notFound")}</h1>
          <Link to="/customers">{t("customers.back")}</Link>
        </div>
      </div>
    );
  }
  const own = (services.data ?? []).filter((s) => s.customer_id === customer.id);
  return (
    <>
      <p style={{ margin: "0 0 6px" }}>
        <Link to="/customers">‹ {t("nav.customers")}</Link>
      </p>
      <PageHead title={customer.name} sub={categories.find((c) => c.id === customer.category_id)?.name}>
        <button type="button" className="btn" onClick={() => setReporting(true)}>{t("report.button")}</button>
        {edit && (
          <button type="button" className="btn" onClick={() => setEditing(true)}>
            <Icon name="edit" size={16} />
            {t("common.edit")}
          </button>
        )}
      </PageHead>

      {reporting && <ReportDialog customerId={customer.id} onClose={() => setReporting(false)} />}
      <h2 className="section-title">{t("customers.contactTitle")}</h2>
      <ContactsCard customer={customer} />
      <ContractCard customer={customer} />
      <TasksCard customer={customer} edit={edit} />

      <h2 className="section-title">{t("customers.sitesTitle")}</h2>
      {own.length === 0 ? (
        <Empty>{t("customers.noServices")}</Empty>
      ) : (
        <div className="card list">
          {own.map((s) => (
            <div key={s.id} className={`list-row${edit ? "" : " static-row"}`} role={edit ? "button" : undefined}
                 tabIndex={edit ? 0 : undefined} onClick={() => edit && setService(s)}
                 onKeyDown={(e) => edit && e.key === "Enter" && setService(s)}>
              <Dot state={serviceState(s, ports.data)} />
              <div className="list-main">
                <div className="list-title">{s.name}</div>
                <div className="chips">
                  {s.domains.map((d) => (
                    <a key={d} className="chip" href={`https://${d}`} target="_blank" rel="noreferrer"
                       onClick={(e) => e.stopPropagation()}>
                      {d}
                      <Icon name="external" size={12} />
                    </a>
                  ))}
                </div>
              </div>
              {can("credentials.manage") && (
                <button type="button" className="btn btn-ghost" title={t("credentials.show")}
                        onClick={(e) => { e.stopPropagation(); setKeys(s); }}>
                  <Icon name="credentials" size={16} />
                  {s.credential_count > 0 ? s.credential_count : ""}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <AssignedCard customer={customer} />

      <SitesSection customerId={customer.id} />

      {own.some((s) => s.domains.length) && (
        <>
          <div className="section-row">
            <h2 className="section-title">{t("sites.title")}</h2>
            {edit && <button type="button" className="btn btn-ghost btn-small" disabled={runChecks.isPending}
                    onClick={() => runChecks.mutate(customer.id)}>
              <Icon name="refresh" size={14} />
              {runChecks.isPending ? t("sites.checking") : t("sites.checkNow")}
            </button>}
          </div>
          <div className="card list">
            {[...new Set(own.flatMap((s) => s.domains))].map((d) => {
              const ch = checks.data?.[d];
              return (
                <div key={d} className="list-row static-row">
                  <Dot state={ch?.level ?? "off"} />
                  <div className="list-main">
                    <div className="list-title">
                      <a href={`https://${d}`} target="_blank" rel="noreferrer">{d}</a>
                      {ch && <span className={`state-text state-${ch.level}`}>{ch.label}</span>}
                    </div>
                    <div className="list-sub">
                      {ch ? [
                        ch.ms !== undefined && `${ch.ms} ms`,
                        ch.cert_expires && t("sites.certUntil", { date: new Date(ch.cert_expires * 1000).toLocaleDateString() }),
                        ch.cloudflare ? t("sites.viaCloudflare") : ch.ips.slice(0, 2).join(", "),
                        t("sites.checked", { when: ago(ch.checked_at) }),
                      ].filter(Boolean).join(" · ") : t("sites.notChecked")}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {runChecks.error && <p className="error-text">{runChecks.error.message}</p>}
        </>
      )}

      {(customer.agreements || customer.notes) && (
        <>
          <h2 className="section-title">{t("customers.agreementsTitle")}</h2>
          <div className="card card-pad">
            <dl className="details">
              {customer.agreements && (<><dt>{t("customers.agreements")}</dt><dd>{customer.agreements}</dd></>)}
              {customer.notes && (<><dt>{t("customers.notes")}</dt><dd><NoteText text={customer.notes} /></dd></>)}
            </dl>
          </div>
        </>
      )}

      {editing && <CustomerDialog customer={customer} onClose={() => setEditing(false)} />}
      {service && <ServiceDialog service={service} onClose={() => setService(null)} />}
      {keys && <CredentialsDialog service={keys} onClose={() => setKeys(null)} />}
    </>
  );
}

function CustomerDialog({
  customer,
  onClose,
  onSaved,
}: {
  customer: Customer | null;
  onClose: () => void;
  onSaved?: (c: Customer) => void;
}) {
  const { t } = useTranslation();
  const services = useServices();
  const categories = useCategories().data ?? [];
  const save = useSaveCustomer();
  const remove = useDeleteCustomer();
  const navigate = useNavigate();
  const canContracts = useCan()("customers.contracts");
  const [form, setForm] = useState<CustomerInput>(() => (customer ? { ...customer } : canContracts ? { ...EMPTY, contract: { contract_end: null, notice_days: null, support_hours: "", response_time: "" } } : EMPTY));
  const set = (key: keyof CustomerInput) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));
  const toggle = (id: string) =>
    setForm((f) => ({
      ...f,
      service_ids: f.service_ids.includes(id) ? f.service_ids.filter((x) => x !== id) : [...f.service_ids, id],
    }));

  return (
    <Dialog
      wide
      title={customer ? t("customers.edit") : t("customers.add")}
      onClose={onClose}
      onSubmit={() =>
        save.mutate({ id: customer?.id, body: form }, { onSuccess: (c) => { onClose(); onSaved?.(c); } })
      }
      footer={
        <>
          {customer && (
            <ConfirmDelete busy={remove.isPending}
                           onConfirm={() => remove.mutate(customer.id, { onSuccess: () => navigate("/customers") })} />
          )}
          <span className="spacer" />
          <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button>
        </>
      }
    >
      <label className="field">
        {t("customers.name")}
        <input className="input" required maxLength={80} autoFocus value={form.name} onChange={set("name")} />
      </label>
      <ContactsEditor form={form} setForm={setForm} />
      <label className="field">
        {t("customers.owner")}
        <input className="input" maxLength={120} placeholder={t("customers.ownerHint")} value={form.owner}
               onChange={set("owner")} />
      </label>
      {categories.length > 0 && (
        <label className="field">
          {t("customers.category")}
          <select className="input" value={form.category_id ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, category_id: e.target.value || null }))}>
            <option value="">{t("customers.noCategory")}</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
      )}
      <div className="field">
        {t("customers.sitesTitle")}
        {services.data?.length ? (
          <div className="chips">
            {services.data.map((s) => (
              <label key={s.id} className="chip check-chip">
                <input type="checkbox" checked={form.service_ids.includes(s.id)} onChange={() => toggle(s.id)} />
                {s.name}
                {s.customer_id && s.customer_id !== customer?.id && <span className="muted">({s.customer_name})</span>}
              </label>
            ))}
          </div>
        ) : (
          <span className="hint">{t("customers.noServicesYet")}</span>
        )}
      </div>
      <AssignEditor form={form} setForm={setForm} />
      {canContracts && <ContractEditor form={form} setForm={setForm} />}
      <label className="field">
        {t("customers.agreements")}
        <span className="hint">{t("customers.agreementsHint")}</span>
        <textarea className="input" rows={3} maxLength={5000} value={form.agreements} onChange={set("agreements")} />
      </label>
      <label className="field">
        {t("customers.notes")}
        <textarea className="input" rows={4} maxLength={5000} value={form.notes} onChange={set("notes")} />
      </label>
      {save.error && <p className="error-text">{save.error.message}</p>}
      {remove.error && <p className="error-text">{remove.error.message}</p>}
    </Dialog>
  );
}

function CategoryDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const categories = useCategories().data ?? [];
  const { add, rename, remove, order } = useCategoryActions();
  const [name, setName] = useState("");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const error = add.error ?? rename.error ?? remove.error ?? order.error;
  const move = (index: number, by: number) => {
    const ids = categories.map((c) => c.id);
    [ids[index], ids[index + by]] = [ids[index + by], ids[index]];
    order.mutate(ids);
  };
  return (
    <Dialog title={t("customers.manageCategories")} onClose={onClose}
            onSubmit={() => name.trim() && add.mutate(name.trim(), { onSuccess: () => setName("") })}
            footer={<><span className="spacer" /><button type="button" className="btn" onClick={onClose}>{t("common.close")}</button></>}>
      <p className="hint">{t("customers.categoriesHint")}</p>
      {categories.map((c, i) => (
        <div key={c.id} className="category-row">
          <input className="input" maxLength={40} value={edits[c.id] ?? c.name}
                 onChange={(e) => setEdits((x) => ({ ...x, [c.id]: e.target.value }))}
                 onBlur={() => { const v = (edits[c.id] ?? c.name).trim(); if (v && v !== c.name) rename.mutate({ id: c.id, name: v }); setEdits((x) => { const { [c.id]: _, ...rest } = x; return rest; }); }} />
          <button type="button" className="btn btn-ghost btn-small" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t("customers.up")}>↑</button>
          <button type="button" className="btn btn-ghost btn-small" disabled={i === categories.length - 1} onClick={() => move(i, 1)} aria-label={t("customers.down")}>↓</button>
          <ConfirmDelete compact busy={remove.isPending} onConfirm={() => remove.mutate(c.id)} />
        </div>
      ))}
      <div className="category-row">
        <input className="input" maxLength={40} placeholder={t("customers.categoryPlaceholder")} value={name} onChange={(e) => setName(e.target.value)} />
        <button type="submit" className="btn btn-primary btn-small" disabled={!name.trim() || add.isPending}>{t("customers.addCategory")}</button>
      </div>
      {error && <p className="error-text">{error.message}</p>}
    </Dialog>
  );
}
