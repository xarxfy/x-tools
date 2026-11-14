import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useServices } from "../api/data";
import { Icon } from "../components/Icon";
import { Empty, Loading, PageHead, SearchField, matches, rootDomain } from "../components/ui";

/** All domains of all services, grouped by their root domain. */
export function DomainsPage() {
  const { t } = useTranslation();
  const services = useServices();
  const [query, setQuery] = useState("");

  if (!services.data) return <Loading error={services.error} retry={() => services.refetch()} />;
  const rows = services.data
    .flatMap((s) => s.domains.map((domain) => ({ domain, service: s })))
    .filter((r) => matches(query, r.domain, r.service.name, r.service.customer_name))
    .sort((a, b) => a.domain.localeCompare(b.domain));
  const groups = new Map<string, typeof rows>();
  for (const r of rows) {
    const root = rootDomain(r.domain);
    groups.set(root, [...(groups.get(root) ?? []), r]);
  }
  const total = new Set(services.data.flatMap((s) => s.domains)).size;

  return (
    <>
      <PageHead title={t("nav.domains")} sub={t("domains.sub", { count: total })}>
        <SearchField value={query} onChange={setQuery} />
      </PageHead>
      {groups.size === 0 ? (
        <Empty>{total ? t("common.noMatch") : t("domains.empty")}</Empty>
      ) : (
        [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([root, list]) => (
          <section key={root}>
            <h2 className="section-title">{root}</h2>
            <div className="card list">
              {list.map(({ domain, service }) => (
                <div key={`${domain}-${service.id}`} className="list-row" style={{ cursor: "default" }}>
                  <span className="list-main">
                    <a className="list-title" href={`https://${domain}`} target="_blank" rel="noreferrer">
                      {domain}
                      <Icon name="external" size={12} />
                    </a>
                    <span className="list-sub">
                      {service.name}
                      {service.customer_id && (
                        <> · <Link to={`/customers/${service.customer_id}`}>{service.customer_name}</Link></>
                      )}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </section>
        ))
      )}
    </>
  );
}
