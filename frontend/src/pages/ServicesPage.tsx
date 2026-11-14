import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  portKey, useCustomers, useDeleteService, usePortStatus, useSaveService, useServices,
  type Port, type Service, type ServiceInput,
} from "../api/data";
import { Icon } from "../components/Icon";
import { ConfirmDelete, Dialog, Dot, Empty, Loading, PageHead, SearchField, matches } from "../components/ui";
import { CredentialsDialog } from "./CredentialsPage";
import { ConfigDialog } from "./AssistantPage";
import { useFeatures } from "../api/monitor";
import { useUptime } from "../api/account";
import { useCan } from "../api/users";

const EMPTY: ServiceInput = { name: "", host: "", domains: [], ports: [], folder: "", type: "", notes: "", customer_id: null };

export function serviceState(s: Service, ports?: Record<string, boolean>): "up" | "down" | "warn" | "off" {
  if (!s.ports.length || !ports) return "off";
  const states = s.ports.map((p) => ports[portKey(s.host, p.port)]);
  if (states.every(Boolean)) return "up";
  return states.some(Boolean) ? "warn" : "down";
}

export function ServicesPage() {
  const { t } = useTranslation();
  const services = useServices();
  const ports = usePortStatus();
  const uptime = useUptime();
  const can = useCan();
  const edit = can("operator");
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Service | "new" | null>(null);
  const [keys, setKeys] = useState<Service | null>(null);
  const customersOn = useFeatures().data?.customers ?? false;

  if (!services.data) return <Loading error={services.error} retry={() => services.refetch()} />;
  const list = services.data.filter((s) =>
    matches(query, s.name, s.type, s.folder, s.host, s.customer_name, ...s.domains, ...s.ports.map((p) => String(p.port))),
  );

  return (
    <>
      <PageHead title={t("nav.services")} sub={t("services.sub", { count: services.data.length })}>
        <SearchField value={query} onChange={setQuery} />
        {edit && (
          <>
            <button type="button" className="btn" onClick={() => navigate("/services/new")}>
              <Icon name="wand" size={16} />
              {t("services.assistant")}
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setEditing("new")}>
              <Icon name="plus" size={16} />
              {t("services.add")}
            </button>
          </>
        )}
      </PageHead>

      {list.length === 0 ? (
        <Empty>{services.data.length ? t("common.noMatch") : t("services.empty")}</Empty>
      ) : (
        <div className="card list">
          {list.map((s) => (
            <div key={s.id} className={`list-row${edit ? "" : " static-row"}`} role={edit ? "button" : undefined}
                 tabIndex={edit ? 0 : undefined} onClick={() => edit && setEditing(s)}
                 onKeyDown={(e) => edit && e.key === "Enter" && setEditing(s)}>
              <Dot state={serviceState(s, ports.data)} />
              <div className="list-main">
                <div className="list-title">
                  {s.name}
                  {s.type && <span className="badge">{s.type}</span>}
                  {s.checklist.some((c) => !c.done) && (
                    <span className="badge badge-warn">
                      {t("services.setupProgress", { done: s.checklist.filter((c) => c.done).length, total: s.checklist.length })}
                    </span>
                  )}
                </div>
                <div className="list-sub">
                  {[s.host, s.folder, customersOn && s.customer_name && t("services.forCustomer", { name: s.customer_name })]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
                {(s.ports.length > 0 || s.domains.length > 0) && (
                  <div className="chips">
                    {s.ports.map((p) => (
                      <span key={p.port} className="chip">
                        <Dot state={ports.data ? (ports.data[portKey(s.host, p.port)] ? "up" : "down") : "off"} />
                        {p.port}
                        {p.label && <span className="muted">{p.label}</span>}
                      </span>
                    ))}
                    {s.domains.map((d) => (
                      <a key={d} className="chip" href={`https://${d}`} target="_blank" rel="noreferrer"
                         onClick={(e) => e.stopPropagation()}>
                        {d}
                        <Icon name="external" size={12} />
                      </a>
                    ))}
                  </div>
                )}
              </div>
              <div className="list-side">
                {uptime.data?.[s.id] !== undefined && (
                  <span className={`badge uptime ${uptime.data[s.id] < 99 ? "uptime-low" : ""}`}
                        title={t("history.uptime", { pct: uptime.data[s.id] })}>
                    {uptime.data[s.id] >= 99.995 ? "100" : uptime.data[s.id].toFixed(2)} %
                  </span>
                )}
                {edit && (
                  <button type="button" className="btn btn-ghost" title={t("credentials.show")}
                          onClick={(e) => { e.stopPropagation(); setKeys(s); }}>
                    <Icon name="credentials" size={16} />
                    {s.credential_count > 0 ? s.credential_count : ""}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && <ServiceDialog service={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {keys && <CredentialsDialog service={keys} onClose={() => setKeys(null)} />}
    </>
  );
}

export function ServiceDialog({
  service,
  initial,
  onClose,
}: {
  service: Service | null;
  initial?: Partial<ServiceInput>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const customers = useCustomers();
  const customersOn = useFeatures().data?.customers ?? false;
  const save = useSaveService();
  const remove = useDeleteService();
  const [configs, setConfigs] = useState(false);
  const start: ServiceInput = { ...EMPTY, ...initial, ...service };
  const [form, setForm] = useState<ServiceInput>(start);
  const [domains, setDomains] = useState(() => start.domains.join("\n"));
  const [ports, setPorts] = useState<{ port: string; label: string }[]>(() =>
    start.ports.map((p) => ({ port: String(p.port), label: p.label })),
  );
  const set = (key: keyof ServiceInput) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = () => {
    const body: ServiceInput = {
      ...form,
      domains: domains.split(/[\s,]+/).filter(Boolean),
      ports: ports.filter((p) => p.port.trim()).map((p): Port => ({ port: Number(p.port), label: p.label })),
    };
    save.mutate({ id: service?.id, body }, { onSuccess: onClose });
  };

  return (
    <Dialog
      title={service ? t("services.edit") : t("services.add")}
      onClose={onClose}
      onSubmit={submit}
      footer={
        <>
          {service && (
            <ConfirmDelete busy={remove.isPending}
                           onConfirm={() => remove.mutate(service.id, { onSuccess: onClose })} />
          )}
          {service && (
            <button type="button" className="btn btn-ghost" onClick={() => setConfigs(true)}>
              <Icon name="wand" size={16} />
              {t("assistant.configs")}
            </button>
          )}
          <span className="spacer" />
          <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button>
        </>
      }
    >
      <label className="field">
        {t("services.name")}
        <input className="input" required maxLength={80} autoFocus value={form.name} onChange={set("name")} />
      </label>
      <div className="grid-2">
        <label className="field">
          {t("services.type")}
          <input className="input" maxLength={60} list="service-types" placeholder="Docker Compose"
                 value={form.type} onChange={set("type")} />
          <datalist id="service-types">
            {["Docker Compose", "Docker", "Systemd", "LXC", "VM", "Static site"].map((v) => <option key={v} value={v} />)}
          </datalist>
        </label>
        {customersOn && <label className="field">
          {t("services.customer")}
          <select className="input" value={form.customer_id ?? ""}
                  onChange={(e) => setForm((f) => ({ ...f, customer_id: e.target.value || null }))}>
            <option value="">{t("services.noCustomer")}</option>
            {customers.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>}
      </div>
      <div className="grid-2">
        <label className="field">
          {t("services.host")}
          <span className="hint">{t("services.hostHint")}</span>
          <input className="input" maxLength={255} placeholder="192.168.1.20" value={form.host} onChange={set("host")} />
        </label>
        <label className="field">
          {t("services.folder")}
          <span className="hint">{t("services.folderHint")}</span>
          <input className="input" maxLength={200} placeholder="~/my-app" value={form.folder} onChange={set("folder")} />
        </label>
      </div>
      <label className="field">
        {t("services.domains")}
        <span className="hint">{t("services.domainsHint")}</span>
        <textarea className="input" rows={2} placeholder="app.example.com" value={domains}
                  onChange={(e) => setDomains(e.target.value)} />
      </label>
      <div className="field">
        {t("services.ports")}
        <div className="stack">
          {ports.map((p, i) => (
            <div key={i} className="row-inputs">
              <input className="input" inputMode="numeric" placeholder="8080" aria-label={t("services.port")}
                     value={p.port}
                     onChange={(e) => setPorts((ps) => ps.map((x, j) => (j === i ? { ...x, port: e.target.value } : x)))} />
              <input className="input" maxLength={40} placeholder={t("services.portLabel")} aria-label={t("services.portLabel")}
                     value={p.label}
                     onChange={(e) => setPorts((ps) => ps.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
              <button type="button" className="btn btn-ghost btn-icon" aria-label={t("common.remove")}
                      onClick={() => setPorts((ps) => ps.filter((_, j) => j !== i))}>
                <Icon name="close" size={16} />
              </button>
            </div>
          ))}
          {ports.length < 10 && (
            <button type="button" className="btn btn-ghost add-link"
                    onClick={() => setPorts((ps) => [...ps, { port: "", label: "" }])}>
              <Icon name="plus" size={14} />
              {t("services.addPort")}
            </button>
          )}
        </div>
      </div>
      {(form.checklist?.length ?? 0) > 0 && (
        <div className="field">
          {t("services.checklist")}
          <div className="checklist">
            {form.checklist!.map((item, i) => (
              <label key={i} className={`inline-check${item.done ? " done" : ""}`}>
                <input type="checkbox" checked={item.done}
                       onChange={(e) => setForm((f) => ({ ...f, checklist: f.checklist!.map((c, j) => (j === i ? { ...c, done: e.target.checked } : c)) }))} />
                {item.text}
              </label>
            ))}
          </div>
        </div>
      )}
      <label className="field">
        {t("services.notes")}
        <textarea className="input" maxLength={300} value={form.notes} onChange={set("notes")} />
      </label>
      {customersOn && service?.customer_id && (
        <Link to={`/customers/${service.customer_id}`} onClick={onClose}>{t("services.openCustomer")}</Link>
      )}
      {save.error && <p className="error-text">{save.error.message}</p>}
      {remove.error && <p className="error-text">{remove.error.message}</p>}
      {configs && service && <ConfigDialog service={service} onClose={() => setConfigs(false)} />}
    </Dialog>
  );
}
