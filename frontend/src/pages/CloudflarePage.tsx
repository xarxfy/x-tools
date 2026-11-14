import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useCloudflare, useRefreshCloudflare, type CfHost } from "../api/cloudflare";
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
  const tab = TABS.find((k) => k === params.get("tab")) ?? "hosts";

  if (!cf.data) return <Loading error={cf.error} retry={() => cf.refetch()} />;
  if (!cf.data.configured || !cf.data.snapshot) {
    return (
      <>
        <PageHead title="Cloudflare" />
        <Empty>{t("cloudflare.notSetUp")} {can("admin") && <Link to="/settings?tab=cloudflare">{t("cloudflare.setUp")}</Link>}</Empty>
      </>
    );
  }
  const snap = cf.data.snapshot;
  const problems = cf.data.hosts.filter((h) => h.problems.length);
  const errors = Object.entries(snap.errors ?? {});

  return (
    <>
      <PageHead title="Cloudflare" sub={t("cloudflare.sub", { zones: snap.zones.length, tunnels: snap.tunnels.length, when: ago(snap.fetched_at) })}>
        <SearchField value={query} onChange={setQuery} />
        {can("operator") && (
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

      {tab === "hosts" && <Hosts hosts={cf.data.hosts.filter((h) => matches(query, h.hostname, h.service?.name, h.route?.service))} />}

      {tab === "dns" && snap.zones.map((z) => {
        const records = z.records.filter((r) => matches(query, r.name, r.content, r.type));
        return (
          <section key={z.id}>
            <h2 className="section-title">{z.name} <span className="badge">{z.status}</span></h2>
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
    </>
  );
}

function Hosts({ hosts }: { hosts: CfHost[] }) {
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
              </div>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
