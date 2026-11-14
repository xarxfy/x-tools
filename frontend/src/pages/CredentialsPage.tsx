import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCredentials, useSaveCredentials, useServices, type Credential, type Service } from "../api/data";
import { Icon } from "../components/Icon";
import { CopyButton, Dialog, Empty, Loading, PageHead, SearchField, matches } from "../components/ui";

const BLANK: Credential = { label: "", username: "", password: "", url: "", note: "" };

export function CredentialsPage() {
  const { t } = useTranslation();
  const services = useServices();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Service | null>(null);

  if (!services.data) return <Loading error={services.error} retry={() => services.refetch()} />;
  const list = services.data.filter((s) => matches(query, s.name, s.customer_name, ...s.domains));
  const withCreds = list.filter((s) => s.credential_count > 0);
  const without = list.filter((s) => s.credential_count === 0);

  const row = (s: Service) => (
    <button key={s.id} type="button" className="list-row" onClick={() => setOpen(s)}>
      <span className="list-main">
        <span className="list-title">{s.name}</span>
        <span className="list-sub">{[s.domains[0]].filter(Boolean).join(" · ")}</span>
      </span>
      <span className="list-side">
        {s.credential_count > 0 && <span className="badge">{t("credentials.count", { count: s.credential_count })}</span>}
        <Icon name="chevron" size={16} />
      </span>
    </button>
  );

  return (
    <>
      <PageHead title={t("nav.credentials")} sub={t("credentials.sub")}>
        <SearchField value={query} onChange={setQuery} />
      </PageHead>
      {services.data.length === 0 ? (
        <Empty>{t("credentials.noServices")}</Empty>
      ) : (
        <>
          {withCreds.length > 0 && <div className="card list">{withCreds.map(row)}</div>}
          {without.length > 0 && (
            <>
              <h2 className="section-title">{t("credentials.withoutTitle")}</h2>
              <div className="card list">{without.map(row)}</div>
            </>
          )}
        </>
      )}
      {open && <CredentialsDialog service={open} onClose={() => setOpen(null)} />}
    </>
  );
}

/** Shows the (decrypted) logins of a service; passwords stay hidden until revealed. */
export function CredentialsDialog({ service, onClose }: { service: Service; onClose: () => void }) {
  const { t } = useTranslation();
  const creds = useCredentials(service.id);
  const save = useSaveCredentials();
  const [edit, setEdit] = useState<Credential[] | null>(null);
  const [shown, setShown] = useState<Set<number>>(new Set());

  const startEdit = () => setEdit(creds.data?.length ? creds.data.map((c) => ({ ...c })) : [{ ...BLANK }]);
  const update = (i: number, key: keyof Credential, value: string) =>
    setEdit((list) => list && list.map((c, j) => (j === i ? { ...c, [key]: value } : c)));

  const footer = edit ? (
    <>
      <span className="spacer" />
      <button type="button" className="btn" onClick={() => setEdit(null)}>{t("common.cancel")}</button>
      <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button>
    </>
  ) : (
    <>
      <span className="spacer" />
      <button type="button" className="btn" onClick={startEdit} disabled={!creds.data}>
        <Icon name="edit" size={16} />
        {t("common.edit")}
      </button>
      <button type="button" className="btn btn-primary" onClick={onClose}>{t("common.done")}</button>
    </>
  );

  return (
    <Dialog
      title={t("credentials.title", { name: service.name })}
      onClose={onClose}
      onSubmit={() => edit && save.mutate({ id: service.id, body: edit }, { onSuccess: () => setEdit(null) })}
      footer={footer}
    >
      {!creds.data ? (
        <Loading error={creds.error} />
      ) : edit ? (
        <>
          {edit.map((c, i) => (
            <div key={i} className="cred stack">
              <div className="grid-2">
                <input className="input" maxLength={60} placeholder={t("credentials.label")}
                       aria-label={t("credentials.label")} value={c.label}
                       onChange={(e) => update(i, "label", e.target.value)} />
                <input className="input" maxLength={300} placeholder={t("credentials.url")}
                       aria-label={t("credentials.url")} value={c.url} onChange={(e) => update(i, "url", e.target.value)} />
                <input className="input" maxLength={200} placeholder={t("credentials.username")} autoComplete="off"
                       aria-label={t("credentials.username")} value={c.username}
                       onChange={(e) => update(i, "username", e.target.value)} />
                <input className="input secret" maxLength={500} placeholder={t("credentials.password")}
                       autoComplete="new-password" aria-label={t("credentials.password")} value={c.password}
                       onChange={(e) => update(i, "password", e.target.value)} />
              </div>
              <div className="row-inputs" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
                <input className="input" maxLength={300} placeholder={t("credentials.note")}
                       aria-label={t("credentials.note")} value={c.note} onChange={(e) => update(i, "note", e.target.value)} />
                <button type="button" className="btn btn-ghost btn-icon" aria-label={t("common.remove")}
                        onClick={() => setEdit((l) => l && l.filter((_, j) => j !== i))}>
                  <Icon name="trash" size={16} />
                </button>
              </div>
            </div>
          ))}
          {edit.length < 20 && (
            <button type="button" className="btn btn-ghost add-link" onClick={() => setEdit((l) => [...(l ?? []), { ...BLANK }])}>
              <Icon name="plus" size={14} />
              {t("credentials.add")}
            </button>
          )}
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>{t("credentials.encrypted")}</p>
          {save.error && <p className="error-text">{save.error.message}</p>}
        </>
      ) : creds.data.length === 0 ? (
        <p className="muted">{t("credentials.none")}</p>
      ) : (
        creds.data.map((c, i) => (
          <div key={i} className="cred">
            {c.label && <div className="cred-head">{c.label}</div>}
            {c.url && (
              <div className="cred-line">
                <span>{t("credentials.url")}</span>
                <span>
                  {/^https?:\/\//.test(c.url) ? <a href={c.url} target="_blank" rel="noreferrer">{c.url}</a> : c.url}
                </span>
                <CopyButton value={c.url} label={t("common.copy")} />
              </div>
            )}
            <div className="cred-line">
              <span>{t("credentials.username")}</span>
              <span className="secret">{c.username || "–"}</span>
              <CopyButton value={c.username} label={t("common.copy")} />
            </div>
            <div className="cred-line">
              <span>{t("credentials.password")}</span>
              <span className="secret">{c.password ? (shown.has(i) ? c.password : "••••••••••") : "–"}</span>
              <span>
                <button type="button" className="btn btn-ghost btn-icon" disabled={!c.password}
                        aria-label={shown.has(i) ? t("credentials.hide") : t("credentials.reveal")}
                        onClick={() => setShown((s) => { const n = new Set(s); if (n.has(i)) n.delete(i); else n.add(i); return n; })}>
                  <Icon name="eye" size={16} />
                </button>
                <CopyButton value={c.password} label={t("common.copy")} />
              </span>
            </div>
            {c.note && <div className="list-sub" style={{ marginTop: 6 }}>{c.note}</div>}
          </div>
        ))
      )}
    </Dialog>
  );
}
