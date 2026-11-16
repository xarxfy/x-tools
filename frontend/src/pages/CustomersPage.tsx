import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  useCategories, useCustomers, useDeleteCustomer, usePortStatus, useSaveCustomer, useServices,
  type Customer, type CustomerInput,
} from "../api/data";
import { ReportDialog } from "../components/ReportDialog";
import { Icon } from "../components/Icon";
import { AssignEditor, AssignedCard, ContactsCard, ContactsEditor, ContractCard, ContractEditor, CustomerJournal, CustomerTickets, LinksCard, LinksEditor, OpenTickets, TagsEditor, contractLevel, daysFrom, useRelDays } from "./CustomerExtras";
import { DataTable, type Column } from "../components/DataTable";
import { colorClass, useTagClass } from "../api/organize";
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
  name: "", owner: "", agreements: "", notes: "", category_id: null, service_ids: [], agent_ids: [], job_ids: [], contacts: [], links: [], tags: [], contract: null,
};

export function CustomersPage() {
  const { t } = useTranslation();
  const customers = useCustomers();
  const services = useServices();
  const checks = useSiteChecks();
  const [query, setQuery] = useState("");
  const categories = useCategories().data ?? [];
  const [category, setCategory] = useState("");
  const [tag, setTag] = useState("");
  const [adding, setAdding] = useState(false);
  const navigate = useNavigate();
  const edit = useCan()("customers.edit");
  const canContracts = useCan()("customers.contracts");
  const canOrganize = useCan()("admin.organize");
  const tagClass = useTagClass();
  const rel = useRelDays();

  if (!customers.data) return <Loading error={customers.error} retry={() => customers.refetch()} />;
  const byId = new Map((services.data ?? []).map((s) => [s.id, s]));
  const rank = new Map(categories.map((c, i) => [c.id, i]));
  const catName = new Map(categories.map((c) => [c.id, c.name]));
  const catColor = new Map(categories.map((c) => [c.id, c.color]));
  const allTags = [...new Set(customers.data.flatMap((c) => c.tags))].sort((x, y) => x.localeCompare(y));
  const list = customers.data
    .filter((c) => !category || (category === "none" ? !c.category_id : c.category_id === category))
    .filter((c) => !tag || c.tags.includes(tag))
    .filter((c) => matches(query, c.name, ...c.tags, ...c.contacts.flatMap((p) => [p.name, p.email]), ...c.service_ids.flatMap((id) => byId.get(id)?.domains ?? [])));
  const domainsOf = (c: Customer) => c.service_ids.flatMap((id) => byId.get(id)?.domains ?? []);
  const columns: Column<Customer>[] = [
    { key: "name", label: t("customers.name"), value: (c) => c.name,
      render: (c) => <><Link to={`/customers/${c.id}`}><b>{c.name}</b></Link>{c.tags.length > 0 && <div className="chips">{c.tags.map((x) => <span key={x} className={`chip ${tagClass(x)}`}>#{x}</span>)}</div>}</> },
    { key: "category", label: t("customers.category"), nowrap: true,
      value: (c) => `${String(rank.get(c.category_id ?? "") ?? 999).padStart(3, "0")}${c.name}`, csv: (c) => catName.get(c.category_id ?? "") ?? "",
      render: (c) => c.category_id && catName.get(c.category_id) ? <span className={`badge category-badge ${colorClass(catColor.get(c.category_id))}`}>{catName.get(c.category_id)}</span> : <span className="muted">–</span> },
    { key: "contact", label: t("customers.contactTitle"), value: (c) => c.contacts[0]?.name ?? "",
      render: (c) => c.contacts[0] ? <>{c.contacts[0].name}{c.contacts[0].email && <div className="small-note"><a href={`mailto:${c.contacts[0].email}`}>{c.contacts[0].email}</a></div>}</> : <span className="muted">–</span> },
    { key: "services", label: t("customers.sitesTitle"), value: (c) => c.service_ids.length,
      render: (c) => <>{c.service_ids.length}{domainsOf(c).length > 0 && <div className="small-note">{domainsOf(c).slice(0, 2).join(", ")}{domainsOf(c).length > 2 && ` +${domainsOf(c).length - 2}`}</div>}</> },
    { key: "servers", label: t("customers.serversTitle"), value: (c) => c.agent_ids.length, render: (c) => c.agent_ids.length || <span className="muted">–</span> },
    { key: "status", label: t("customers.status"), value: (c) => ["up", "off", "warn", "down"].indexOf(worst(domainsOf(c).map((d) => checks.data?.[d]))),
      csv: (c) => worst(domainsOf(c).map((d) => checks.data?.[d])), render: (c) => <Dot state={worst(domainsOf(c).map((d) => checks.data?.[d]))} /> },
    ...(canContracts ? [{ key: "contract", label: t("customers.contractEnd"), nowrap: true, value: (c: Customer) => c.contract?.contract_end ?? "9999",
      csv: (c: Customer) => c.contract?.contract_end ?? "",
      render: (c: Customer) => c.contract?.contract_end ? <>{new Date(`${c.contract.contract_end}T00:00:00`).toLocaleDateString()}{contractLevel(c) === "warn" || contractLevel(c) === "down" ? <div className="small-note due-late">{t("customers.noticeBy")}: {rel(daysFrom(c.contract.deadline ?? ""))}</div> : null}</> : <span className="muted">–</span> }] : []),
    { key: "tickets", label: t("customers.ticketsCol"), nowrap: true, value: (c) => c.tickets_open,
      render: (c) => c.tickets_open ? <Link to={`/customers/${c.id}?tab=tickets`}>{c.tickets_open}{c.tickets_overdue > 0 && <span className="due-late"> ({c.tickets_overdue} {t("tickets.overdue")})</span>}</Link> : <span className="muted">0</span> },
  ];

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
      {(categories.length > 0 || canOrganize) && (
        <div className="category-bar">
          {categories.length > 0 && (
            <>
              <button type="button" className={`category-pill${category === "" ? " active" : ""}`} onClick={() => setCategory("")}>{t("customers.allCategories")}</button>
              {categories.map((c) => (
                <button key={c.id} type="button" className={`category-pill ${colorClass(c.color)}${category === c.id ? " active" : ""}`} onClick={() => setCategory(c.id)}>{c.name}</button>
              ))}
              <button type="button" className={`category-pill${category === "none" ? " active" : ""}`} onClick={() => setCategory("none")}>{t("customers.noCategory")}</button>
            </>
          )}
          {canOrganize && <Link className="btn btn-ghost btn-small" to="/admin?tab=organize">{t("organize.manage")}</Link>}
        </div>
      )}
      {allTags.length > 0 && (
        <div className="category-bar">
          {allTags.map((x) => (
            <button key={x} type="button" className={`category-pill ${tagClass(x)}${tag === x ? " active" : ""}`} onClick={() => setTag(tag === x ? "" : x)}>#{x}</button>
          ))}
        </div>
      )}
      {list.length === 0 ? (
        <Empty>{customers.data.length ? t("common.noMatch") : t("customers.empty")}</Empty>
      ) : (
        <DataTable rows={list} rowKey={(c) => c.id} initialSort="category" columns={columns} />
      )}
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
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [service, setService] = useState<Service | null>(null);
  const [keys, setKeys] = useState<Service | null>(null);
  const checks = useSiteChecks();
  const runChecks = useRunSiteChecks();
  const can = useCan();
  const edit = can("customers.edit");
  const categories = useCategories().data ?? [];
  const tagClass = useTagClass();

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
  const level = contractLevel(customer);
  const siteLevel = worst(own.flatMap((s) => s.domains).map((d) => checks.data?.[d]));
  const tabs = ["overview", "services", "servers", "tickets", "history"] as const;
  const tab = (tabs as readonly string[]).includes(params.get("tab") ?? "") ? params.get("tab")! : "overview";
  const rel = (days: number) => days === 0 ? t("customers.today") : days > 0 ? t("customers.inDays", { count: days }) : t("customers.daysAgo", { count: -days });

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

      <div className="customer-head">
        {siteLevel !== "off" && <span><Dot state={siteLevel} /> {t(`customers.siteState.${siteLevel}`)}</span>}
        {customer.contacts[0] && <span>{customer.contacts[0].name}{customer.contacts[0].email && <> · <a href={`mailto:${customer.contacts[0].email}`}>{customer.contacts[0].email}</a></>}{customer.contacts[0].phone && <> · <a href={`tel:${customer.contacts[0].phone.replace(/\s/g, "")}`}>{customer.contacts[0].phone}</a></>}</span>}
        {customer.contract?.deadline && (level === "warn" || level === "down") && <span className="due-late">{t("customers.noticeBy")} {new Date(`${customer.contract.deadline}T00:00:00`).toLocaleDateString()} ({rel(daysFrom(customer.contract.deadline))})</span>}
        {customer.tags.map((x) => <span key={x} className={`chip ${tagClass(x)}`}>#{x}</span>)}
      </div>

      {reporting && <ReportDialog customerId={customer.id} onClose={() => setReporting(false)} />}

      <div className="tabs server-tabs" role="tablist">
        {tabs.map((x) => (
          <button key={x} type="button" role="tab" aria-selected={tab === x} className={tab === x ? "active" : ""}
                  onClick={() => setParams(x === "overview" ? {} : { tab: x }, { replace: true })}>
            {t(`customers.tabs.${x}`)}
            {x === "tickets" && customer.tickets_open > 0 && <span className={`badge${customer.tickets_overdue ? " badge-down" : ""}`}>{customer.tickets_open}</span>}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <h2 className="section-title">{t("customers.contactTitle")}</h2>
          <ContactsCard customer={customer} />
          <ContractCard customer={customer} />
          <LinksCard customer={customer} />
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
          <OpenTickets customer={customer} onAll={() => setParams({ tab: "tickets" }, { replace: true })} />
        </>
      )}

      {tab === "services" && (
        <>
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
        </>
      )}

      {tab === "servers" && (customer.agent_ids.length || customer.job_ids.length ? <AssignedCard customer={customer} /> : <Empty>{t("customers.noServers")}</Empty>)}
      {tab === "tickets" && <CustomerTickets customer={customer} />}
      {tab === "history" && <CustomerJournal customer={customer} />}

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
      <TagsEditor form={form} setForm={setForm} />
      <LinksEditor form={form} setForm={setForm} />
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
