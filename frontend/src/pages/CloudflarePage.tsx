import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  useCloudflare, useDeleteRecord, useDeleteRoute, useRefreshCloudflare, useSaveRecord, useSaveRoute,
  type CfHost, type CfRecord, type CfSnapshot, type RecordBody, type RouteBody,
} from "../api/cloudflare";
import { ConfirmDelete, Dialog } from "../components/ui";
import { useCan } from "../api/users";
import { Icon } from "../components/Icon";
import { Dot, Empty, Loading, PageHead, SearchField, matches } from "../components/ui";
import { ago } from "../components/format";
import "./CloudflarePage.css";

const TABS = ["hosts", "dns", "tunnels", "access"] as const;

function tunnelState(status: string): "up" | "warn" | "down" | "off" {
  return status === "healthy" ? "up" : status === "degraded" ? "warn" : status === "down" ? "down" : "off";
}

export function CloudflarePage() {
  const { t } = useTranslation();
  const cf = useCloudflare();
  const refresh = useRefreshCloudflare();
  const can = useCan();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [record, setRecord] = useState<(RecordBody & { id?: string }) | null>(null);
  const [route, setRoute] = useState<(RouteBody & { edit?: boolean }) | null>(null);
  const tab = TABS.find((k) => k === params.get("tab")) ?? "hosts";

  if (!cf.data) return <Loading error={cf.error} retry={() => cf.refetch()} />;
  if (!cf.data.configured || !cf.data.snapshot) {
    return (
      <>
        <PageHead title="Cloudflare" />
        <Empty>{t("cloudflare.notSetUp")} {can("admin.settings") && <Link to="/admin?tab=cloudflare">{t("cloudflare.setUp")}</Link>}</Empty>
      </>
    );
  }
  const snap = cf.data.snapshot;
  const edit = can("cloudflare.edit") && cf.data.allow_write;
  const remoteTunnels = snap.tunnels.filter((tn) => tn.remote_config);
  const problems = cf.data.hosts.filter((h) => h.problems.length);
  const errors = Object.entries(snap.errors ?? {});

  return (
    <>
      <PageHead title="Cloudflare" sub={t("cloudflare.sub", { zones: snap.zones.length, tunnels: snap.tunnels.length, when: ago(snap.fetched_at) })}>
        <SearchField value={query} onChange={setQuery} />
        {can("cloudflare.edit") && (
          <button type="button" className="btn" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            <Icon name="refresh" size={16} />
            {refresh.isPending ? t("cloudflare.refreshing") : t("cloudflare.refresh")}
          </button>
        )}
      </PageHead>
      {errors.length > 0 && (
        <div className="notice cf-errors">
          <strong>{t("cloudflare.partial")}</strong>
          <ul>{errors.map(([k, v]) => <li key={k}><code>{k}</code>: {v}</li>)}</ul>
          <span>{t("cloudflare.permissionsHint")}</span>
        </div>
      )}
      <div className="tabs" role="tablist">
        {TABS.map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""}
                  onClick={() => setParams(k === "hosts" ? {} : { tab: k })}>
            {t(`cloudflare.tabs.${k}`)}
            {k === "hosts" && problems.length > 0 && <span className="tab-count warn-text">{problems.length}</span>}
          </button>
        ))}
      </div>

      {tab === "hosts" && (
        <Hosts hosts={cf.data.hosts.filter((h) => matches(query, h.hostname, h.service?.name, h.route?.service))}
               onFix={edit && remoteTunnels.length ? (h) => setRoute({
                 tunnel_id: h.tunnel?.id && remoteTunnels.some((tn) => tn.id === h.tunnel!.id) ? h.tunnel.id : remoteTunnels[0].id,
                 hostname: h.hostname, service: `http://localhost:${h.service?.ports[0] ?? 8080}`, dns: true,
               }) : undefined} />
      )}

      {tab === "dns" && snap.zones.map((z) => {
        const records = z.records.filter((r) => matches(query, r.name, r.content, r.type));
        return (
          <section key={z.id}>
            <div className="section-row">
              <h2 className="section-title">{z.name} <span className="badge">{z.status}</span></h2>
              {edit && (
                <button type="button" className="btn btn-ghost btn-small"
                        onClick={() => setRecord({ zone_id: z.id, type: "CNAME", name: `.${z.name}`, content: "", proxied: true })}>
                  <Icon name="plus" size={14} />{t("cloudflare.addRecord")}
                </button>
              )}
            </div>
            {records.length === 0 ? <Empty>{t("common.noMatch")}</Empty> : (
              <div className="card list">
                {records.map((r, i) => (
                  <div key={i} className="list-row static-row">
                    <span className="badge cf-type">{r.type}</span>
                    <div className="list-main">
                      <div className="list-title cf-name">{r.name}</div>
                      <div className="list-sub mono">{r.content}</div>
                    </div>
                    {["A", "AAAA", "CNAME"].includes(r.type) && (
                      <span className={`badge ${r.proxied ? "badge-proxied" : ""}`}>{r.proxied ? t("cloudflare.proxied") : t("cloudflare.dnsOnly")}</span>
                    )}
                    {edit && ["A", "AAAA", "CNAME", "TXT"].includes(r.type) && (
                      <RecordActions zoneId={z.id} record={r}
                                     onEdit={() => setRecord({ id: r.id, zone_id: z.id, type: r.type, name: r.name, content: r.content, proxied: r.proxied })} />
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        );
      })}

      {tab === "tunnels" && (snap.tunnels.length === 0 ? <Empty>{t("cloudflare.noTunnels")}</Empty> : snap.tunnels.map((tn) => (
        <section key={tn.id}>
          <h2 className="section-title cf-tunnel-title">
            <Dot state={tunnelState(tn.status)} /> {tn.name}
            <span className="badge">{t(`cloudflare.status.${tn.status}`, { defaultValue: tn.status })}</span>
            <span className="muted cf-small">{t("cloudflare.connections", { count: tn.connections })}</span>
            {edit && tn.remote_config && (
              <button type="button" className="btn btn-ghost btn-small cf-add-route"
                      onClick={() => setRoute({ tunnel_id: tn.id, hostname: "", service: "http://localhost:", dns: true })}>
                <Icon name="plus" size={14} />{t("cloudflare.addRoute")}
              </button>
            )}
          </h2>
          {tn.ingress === null ? (
            <Empty>{t("cloudflare.localConfig")}</Empty>
          ) : (
            <div className="card list">
              {tn.ingress.filter((i) => matches(query, i.hostname, i.service)).map((i) => (
                <div key={i.hostname + i.path} className="list-row static-row">
                  <div className="list-main">
                    <div className="list-title">{i.hostname}{i.path && <span className="muted">{i.path}</span>}</div>
                    <div className="list-sub mono">→ {i.service}</div>
                  </div>
                  {edit && (
                    <div className="list-side">
                      <button type="button" className="btn btn-ghost btn-icon" aria-label={t("common.edit")}
                              onClick={() => setRoute({ tunnel_id: tn.id, hostname: i.hostname, service: i.service, dns: false, edit: true })}>
                        <Icon name="edit" size={15} />
                      </button>
                      <RouteDelete tunnelId={tn.id} hostname={i.hostname} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )))}

      {tab === "access" && (snap.access_apps.length === 0 ? <Empty>{t("cloudflare.noAccess")}</Empty> : (
        <div className="card list" style={{ marginTop: 16 }}>
          {snap.access_apps.filter((a) => matches(query, a.name, ...a.domains)).map((a) => (
            <div key={a.name + a.domains.join()} className="list-row static-row">
              <Icon name="credentials" size={16} />
              <div className="list-main">
                <div className="list-title">{a.name}<span className="badge">{a.type}</span></div>
                <div className="list-sub mono">{a.domains.join(" · ")}</div>
              </div>
            </div>
          ))}
        </div>
      ))}
      {record && <RecordDialog value={record} snap={snap} onClose={() => setRecord(null)} />}
      {route && <RouteDialog value={route} snap={snap} onClose={() => setRoute(null)} />}
    </>
  );
}

function RecordActions({ zoneId, record, onEdit }: { zoneId: string; record: CfRecord; onEdit: () => void }) {
  const { t } = useTranslation();
  const remove = useDeleteRecord();
  return (
    <div className="list-side">
      <button type="button" className="btn btn-ghost btn-icon" aria-label={t("common.edit")} onClick={onEdit}>
        <Icon name="edit" size={15} />
      </button>
      <ConfirmDelete compact onConfirm={() => remove.mutate({ zone_id: zoneId, id: record.id })} busy={remove.isPending} />
      {remove.error && <span className="error-text small-note">{remove.error.message}</span>}
    </div>
  );
}

function RouteDelete({ tunnelId, hostname }: { tunnelId: string; hostname: string }) {
  const remove = useDeleteRoute();
  return (
    <>
      <ConfirmDelete compact onConfirm={() => remove.mutate({ tunnel_id: tunnelId, hostname, service: "", dns: true })}
                     busy={remove.isPending} />
      {remove.error && <span className="error-text small-note">{remove.error.message}</span>}
    </>
  );
}

function RecordDialog({ value, snap, onClose }: { value: RecordBody & { id?: string }; snap: CfSnapshot; onClose: () => void }) {
  const { t } = useTranslation();
  const save = useSaveRecord();
  const [form, setForm] = useState(value);
  const zone = snap.zones.find((z) => z.id === form.zone_id);
  return (
    <Dialog title={value.id ? t("cloudflare.editRecord") : t("cloudflare.addRecord")} onClose={onClose}
            onSubmit={() => save.mutate(form, { onSuccess: onClose })}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button>
            </>}>
      <p className="muted" style={{ margin: 0 }}>{t("cloudflare.zone", { name: zone?.name })}</p>
      <div className="grid-2">
        <label className="field">
          {t("cloudflare.type")}
          <select className="input" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            {["A", "AAAA", "CNAME", "TXT"].map((x) => <option key={x}>{x}</option>)}
          </select>
        </label>
        <label className="field">
          {t("cloudflare.name")}
          <input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value.trim().toLowerCase() })} />
        </label>
      </div>
      <label className="field">
        {t("cloudflare.content")}
        <span className="hint">{t(`cloudflare.contentHint.${form.type}`)}</span>
        <input className="input mono" required value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} />
      </label>
      {["A", "AAAA", "CNAME"].includes(form.type) && (
        <label className="inline-check">
          <input type="checkbox" checked={form.proxied} onChange={(e) => setForm({ ...form, proxied: e.target.checked })} />
          {t("cloudflare.proxiedHint")}
        </label>
      )}
      {save.error && <p className="error-text">{save.error.message}</p>}
    </Dialog>
  );
}

function RouteDialog({ value, snap, onClose }: { value: RouteBody & { edit?: boolean }; snap: CfSnapshot; onClose: () => void }) {
  const { t } = useTranslation();
  const save = useSaveRoute();
  const [form, setForm] = useState(value);
  const tunnels = snap.tunnels.filter((tn) => tn.remote_config);
  return (
    <Dialog title={value.edit ? t("cloudflare.editRoute") : t("cloudflare.addRoute")} onClose={onClose}
            onSubmit={() => save.mutate(form, { onSuccess: onClose })}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button>
            </>}>
      <div className="grid-2">
        <label className="field">
          {t("cloudflare.tunnel")}
          <select className="input" value={form.tunnel_id} disabled={value.edit}
                  onChange={(e) => setForm({ ...form, tunnel_id: e.target.value })}>
            {tunnels.map((tn) => <option key={tn.id} value={tn.id}>{tn.name}</option>)}
          </select>
        </label>
        <label className="field">
          {t("cloudflare.hostname")}
          <input className="input" required readOnly={value.edit} placeholder="app.example.com" value={form.hostname}
                 onChange={(e) => setForm({ ...form, hostname: e.target.value.trim().toLowerCase() })} />
        </label>
      </div>
      <label className="field">
        {t("cloudflare.service")}
        <span className="hint">{t("cloudflare.serviceHint")}</span>
        <input className="input mono" required value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value.trim() })} />
      </label>
      <label className="inline-check">
        <input type="checkbox" checked={form.dns} onChange={(e) => setForm({ ...form, dns: e.target.checked })} />
        {t("cloudflare.routeDns")}
      </label>
      {save.error && <p className="error-text">{save.error.message}</p>}
    </Dialog>
  );
}

function Hosts({ hosts, onFix }: { hosts: CfHost[]; onFix?: (h: CfHost) => void }) {
  const { t } = useTranslation();
  if (!hosts.length) return <Empty>{t("common.noMatch")}</Empty>;
  const zones = [...new Set(hosts.map((h) => h.zone ?? t("cloudflare.otherZone")))];
  return (
    <>
      {zones.map((zone) => (
        <section key={zone}>
          <h2 className="section-title">{zone}</h2>
          <div className="card list">
            {hosts.filter((h) => (h.zone ?? t("cloudflare.otherZone")) === zone).map((h) => (
              <div key={h.hostname} className="list-row static-row cf-host">
                <Dot state={h.problems.length ? "warn" : h.dns ? "up" : "off"} />
                <div className="list-main">
                  <div className="list-title">
                    {h.hostname}
                    {h.service && <Link className="badge" to="/services">{h.service.name}</Link>}
                  </div>
                  <div className="cf-chain">
                    <span className="chip" title={t("cloudflare.dns")}>
                      {h.dns ? `${h.dns.type} ${h.tunnel ? t("cloudflare.toTunnel", { name: h.tunnel.name || "?" }) : h.dns.content}` : t("cloudflare.noDns")}
                      {h.dns?.proxied && <span className="cf-cloud" title={t("cloudflare.proxied")}>☁</span>}
                    </span>
                    {h.route && <span className="chip mono">→ {h.route.service}</span>}
                    {h.access.map((a) => (
                      <span key={a.name + a.path} className="chip">
                        <Icon name="credentials" size={12} /> {a.name}{a.path !== "/" && <span className="muted"> {a.path}</span>}
                      </span>
                    ))}
                  </div>
                  {h.problems.map((p) => <p key={p} className="cf-problem">{p}</p>)}
                </div>
                {onFix && h.service && h.problems.length > 0 && (
                  <button type="button" className="btn btn-small" onClick={() => onFix(h)}>{t("cloudflare.fixRoute")}</button>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
