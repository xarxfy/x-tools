import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  useCustomers, useDeleteCustomer, usePortStatus, useSaveCustomer, useServices,
  type Customer, type CustomerInput,
} from "../api/data";
import { Icon } from "../components/Icon";
import { ConfirmDelete, Dialog, Dot, Empty, Loading, PageHead, SearchField, matches } from "../components/ui";
import { CredentialsDialog } from "./CredentialsPage";
import { ServiceDialog, serviceState } from "./ServicesPage";
import type { Service } from "../api/data";
import { useRunSiteChecks, useSiteChecks, type SiteCheck } from "../api/monitor";
import { ago } from "../components/format";

function worst(checks: (SiteCheck | undefined)[]): "up" | "warn" | "down" | "off" {
  const levels = checks.map((c) => c?.level).filter(Boolean);
  if (!levels.length) return "off";
  return levels.includes("down") ? "down" : levels.includes("warn") ? "warn" : "up";
}

const EMPTY: CustomerInput = {
  name: "", contact: "", email: "", phone: "", owner: "", agreements: "", notes: "", service_ids: [],
};

export function CustomersPage() {
  const { t } = useTranslation();
  const customers = useCustomers();
  const services = useServices();
  const checks = useSiteChecks();
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const navigate = useNavigate();

  if (!customers.data) return <Loading error={customers.error} retry={() => customers.refetch()} />;
  const byId = new Map((services.data ?? []).map((s) => [s.id, s]));
  const list = customers.data.filter((c) =>
    matches(query, c.name, c.contact, c.email, ...c.service_ids.flatMap((id) => byId.get(id)?.domains ?? [])),
  );

  return (
    <>
      <PageHead title={t("nav.customers")} sub={t("customers.sub", { count: customers.data.length })}>
        <SearchField value={query} onChange={setQuery} />
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
          <Icon name="plus" size={16} />
          {t("customers.add")}
        </button>
      </PageHead>
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
                  <span className="list-title">{c.name}</span>
                  <span className="list-sub">
                    {[c.contact, domains.slice(0, 3).join(", ")].filter(Boolean).join(" · ") || t("customers.noDetails")}
                  </span>
                </span>
                <span className="list-side">
                  <span className="badge">{t("customers.services", { count: c.service_ids.length })}</span>
                  <Icon name="chevron" size={16} />
                </span>
              </Link>
            );
          })}
        </div>
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
  const [editing, setEditing] = useState(false);
  const [service, setService] = useState<Service | null>(null);
  const [keys, setKeys] = useState<Service | null>(null);
  const checks = useSiteChecks();
  const runChecks = useRunSiteChecks();

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
  const contact: [string, string][] = (
    [
      [t("customers.contact"), customer.contact],
      [t("customers.email"), customer.email],
      [t("customers.phone"), customer.phone],
      [t("customers.owner"), customer.owner],
    ] as [string, string][]
  ).filter(([, v]) => v);

  return (
    <>
      <p style={{ margin: "0 0 6px" }}>
        <Link to="/customers">‹ {t("nav.customers")}</Link>
      </p>
      <PageHead title={customer.name}>
        <button type="button" className="btn" onClick={() => setEditing(true)}>
          <Icon name="edit" size={16} />
          {t("common.edit")}
        </button>
      </PageHead>

      <h2 className="section-title">{t("customers.contactTitle")}</h2>
      <div className="card card-pad">
        {contact.length ? (
          <dl className="details">
            {contact.map(([k, v]) => (
              <div key={k} style={{ display: "contents" }}>
                <dt>{k}</dt>
                <dd>
                  {k === t("customers.email") ? <a href={`mailto:${v}`}>{v}</a>
                    : k === t("customers.phone") ? <a href={`tel:${v.replace(/\s/g, "")}`}>{v}</a> : v}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <span className="muted">{t("customers.noContact")}</span>
        )}
      </div>

      <h2 className="section-title">{t("customers.sitesTitle")}</h2>
      {own.length === 0 ? (
        <Empty>{t("customers.noServices")}</Empty>
      ) : (
        <div className="card list">
          {own.map((s) => (
            <div key={s.id} className="list-row" role="button" tabIndex={0} onClick={() => setService(s)}
                 onKeyDown={(e) => e.key === "Enter" && setService(s)}>
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
              <button type="button" className="btn btn-ghost" title={t("credentials.show")}
                      onClick={(e) => { e.stopPropagation(); setKeys(s); }}>
                <Icon name="credentials" size={16} />
                {s.credential_count > 0 ? s.credential_count : ""}
              </button>
            </div>
          ))}
        </div>
      )}

      {own.some((s) => s.domains.length) && (
        <>
          <div className="section-row">
            <h2 className="section-title">{t("sites.title")}</h2>
            <button type="button" className="btn btn-ghost btn-small" disabled={runChecks.isPending}
                    onClick={() => runChecks.mutate(customer.id)}>
              <Icon name="refresh" size={14} />
              {runChecks.isPending ? t("sites.checking") : t("sites.checkNow")}
            </button>
          </div>
          <div className="card list">
            {[...new Set(own.flatMap((s) => s.domains))].map((d) => {
              const ch = checks.data?.[d];
              return (
                <div key={d} className="list-row container-row">
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
              {customer.notes && (<><dt>{t("customers.notes")}</dt><dd>{customer.notes}</dd></>)}
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
  const save = useSaveCustomer();
  const remove = useDeleteCustomer();
  const navigate = useNavigate();
  const [form, setForm] = useState<CustomerInput>(() => (customer ? { ...customer } : EMPTY));
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
      <div className="grid-2">
        <label className="field">
          {t("customers.contact")}
          <input className="input" maxLength={80} value={form.contact} onChange={set("contact")} />
        </label>
        <label className="field">
          {t("customers.email")}
          <input className="input" type="email" maxLength={120} value={form.email} onChange={set("email")} />
        </label>
        <label className="field">
          {t("customers.phone")}
          <input className="input" type="tel" maxLength={40} value={form.phone} onChange={set("phone")} />
        </label>
        <label className="field">
          {t("customers.owner")}
          <input className="input" maxLength={120} placeholder={t("customers.ownerHint")} value={form.owner}
                 onChange={set("owner")} />
        </label>
      </div>
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
      <label className="field">
        {t("customers.agreements")}
        <span className="hint">{t("customers.agreementsHint")}</span>
        <textarea className="input" rows={3} maxLength={5000} value={form.agreements} onChange={set("agreements")} />
      </label>
      <label className="field">
        {t("customers.notes")}
        <textarea className="input" rows={2} maxLength={5000} value={form.notes} onChange={set("notes")} />
      </label>
      {save.error && <p className="error-text">{save.error.message}</p>}
      {remove.error && <p className="error-text">{remove.error.message}</p>}
    </Dialog>
  );
}
