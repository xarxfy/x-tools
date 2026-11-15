import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCan } from "../api/users";
import { useDeleteSite, useSaveSite, useSiteAction, useSiteLog, useSites, type Site, type SiteInput } from "../api/sites";
import { ago } from "../components/format";
import { Icon } from "../components/Icon";
import { ConfirmDelete, Dialog, Dot } from "../components/ui";
import "./SitesSection.css";

const DOT = { none: "off", queued: "warn", running: "warn", ok: "up", failed: "down" } as const;

export function SitesSection({ customerId }: { customerId: string }) {
  const { t } = useTranslation();
  const sites = useSites(customerId);
  const action = useSiteAction();
  const edit = useCan()("operator");
  const [editing, setEditing] = useState<Site | "new" | null>(null);
  const [log, setLog] = useState<Site | null>(null);
  const list = sites.data?.sites ?? [];
  const deployer = sites.data?.deployer ?? false;

  return (
    <>
      <div className="section-row">
        <h2 className="section-title">{t("deploy.title")}</h2>
        {edit && (
          <button type="button" className="btn btn-ghost btn-small" onClick={() => setEditing("new")}>
            <Icon name="plus" size={14} />
            {t("deploy.add")}
          </button>
        )}
      </div>
      {sites.data && !deployer && (list.length > 0 || edit) && (
        <p className="hint deploy-hint">{t("deploy.noDeployer")}</p>
      )}
      {sites.data && list.length === 0 ? (
        <div className="card card-pad empty">{t("deploy.empty")}</div>
      ) : (
        <div className="card list">
          {list.map((s) => {
            const st = s.status;
            const running = st.state === "queued" || st.state === "running";
            return (
              <div key={s.id} className="list-row static-row">
                <Dot state={DOT[st.state]} />
                <div className="list-main">
                  <div className="list-title">
                    {s.name}
                    <span className={`state-text state-${DOT[st.state] === "up" ? "up" : DOT[st.state]}`}>
                      {t(`deploy.state.${st.state}`, { action: t(`deploy.action.${st.action ?? "deploy"}`) })}
                    </span>
                  </div>
                  <div className="list-sub">
                    {[
                      s.repo_url.replace(/^https?:\/\//, ""),
                      s.branch,
                      st.commit && `${st.commit}${st.subject ? ` – ${st.subject}` : ""}`,
                      st.finished && ago(st.finished),
                    ].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <div className="deploy-actions">
                  {st.state !== "none" && (
                    <button type="button" className="btn btn-ghost btn-small" onClick={() => setLog(s)}>
                      {t("deploy.log")}
                    </button>
                  )}
                  {edit && (
                    <>
                      <button type="button" className="btn btn-small" disabled={running || action.isPending}
                              onClick={() => action.mutate({ id: s.id, action: "deploy" })}>
                        {st.state === "none" ? t("deploy.deploy") : t("deploy.redeploy")}
                      </button>
                      {st.state === "ok" && st.action === "deploy" && (
                        <button type="button" className="btn btn-ghost btn-small" disabled={running}
                                onClick={() => action.mutate({ id: s.id, action: "stop" })}>
                          {t("deploy.stop")}
                        </button>
                      )}
                      <button type="button" className="btn btn-ghost btn-icon" aria-label={t("common.edit")}
                              title={t("common.edit")} onClick={() => setEditing(s)}>
                        <Icon name="edit" size={16} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {action.error && <p className="error-text">{action.error.message}</p>}
      {editing && (
        <SiteDialog site={editing === "new" ? null : editing} customerId={customerId} onClose={() => setEditing(null)} />
      )}
      {log && <LogDialog site={log} onClose={() => setLog(null)} />}
    </>
  );
}

function LogDialog({ site, onClose }: { site: Site; onClose: () => void }) {
  const { t } = useTranslation();
  const q = useSiteLog(site.id);
  const data = q.data ?? site;
  return (
    <Dialog wide title={`${site.name} – ${t("deploy.log")}`} onClose={onClose}
            footer={<><span className="spacer" /><button type="button" className="btn" onClick={onClose}>{t("common.close")}</button></>}>
      <div className="deploy-state">
        <Dot state={DOT[data.status.state]} />
        {t(`deploy.state.${data.status.state}`, { action: t(`deploy.action.${data.status.action ?? "deploy"}`) })}
      </div>
      <pre className="code deploy-log">{data.status.log || t("deploy.noLog")}</pre>
      {q.error && <p className="error-text">{q.error.message}</p>}
    </Dialog>
  );
}

interface EnvRow { key: string; value: string; existing: boolean }

function SiteDialog({ site, customerId, onClose }: { site: Site | null; customerId: string; onClose: () => void }) {
  const { t } = useTranslation();
  const save = useSaveSite();
  const remove = useDeleteSite();
  const [form, setForm] = useState({
    name: site?.name ?? "", repo_url: site?.repo_url ?? "https://", branch: site?.branch ?? "main",
    compose_file: site?.compose_file ?? "", port: site?.port ? String(site.port) : "",
  });
  const [token, setToken] = useState<string | undefined>(undefined);
  const [env, setEnv] = useState<EnvRow[]>((site?.env_keys ?? []).map((key) => ({ key, value: "", existing: true })));
  const [purge, setPurge] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setRow = (i: number, patch: Partial<EnvRow>) => setEnv((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const submit = () => {
    const body: SiteInput = {
      name: form.name, customer_id: customerId, repo_url: form.repo_url, branch: form.branch,
      compose_file: form.compose_file, port: form.port ? Number(form.port) : null, token,
      env: env.filter((r) => r.key.trim()).map((r) => ({
        key: r.key.trim(), ...(r.existing && r.value === "" ? {} : { value: r.value }),
      })),
    };
    save.mutate({ id: site?.id, body }, { onSuccess: onClose });
  };

  return (
    <Dialog wide title={site ? t("deploy.edit") : t("deploy.add")} onClose={onClose} onSubmit={submit}
            footer={
              <>
                {site && (
                  <ConfirmDelete busy={remove.isPending}
                                 onConfirm={() => remove.mutate({ id: site.id, purge }, { onSuccess: onClose })} />
                )}
                {site && (
                  <label className="check-inline">
                    <input type="checkbox" checked={purge} onChange={(e) => setPurge(e.target.checked)} />
                    {t("deploy.purge")}
                  </label>
                )}
                <span className="spacer" />
                <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
                <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button>
              </>
            }>
      <label className="field">
        {t("deploy.name")}
        <input className="input" required maxLength={80} autoFocus value={form.name} onChange={set("name")} />
      </label>
      <label className="field">
        {t("deploy.repo")}
        <span className="hint">{t("deploy.repoHint")}</span>
        <input className="input" required maxLength={300} value={form.repo_url} onChange={set("repo_url")}
               placeholder="https://git.example.com/customer/website" />
      </label>
      <div className="grid-2">
        <label className="field">
          {t("deploy.branch")}
          <input className="input" required maxLength={100} value={form.branch} onChange={set("branch")} />
        </label>
        <label className="field">
          {t("deploy.compose")}
          <input className="input" maxLength={100} value={form.compose_file} onChange={set("compose_file")}
                 placeholder={t("deploy.composePlaceholder")} />
        </label>
      </div>
      <label className="field">
        {t("deploy.port")}
        <span className="hint">{t("deploy.portHint")}</span>
        <input className="input" type="number" min={1} max={65535} value={form.port} onChange={set("port")} />
      </label>
      <div className="field">
        {t("deploy.token")}
        <span className="hint">{t("deploy.tokenHint")}</span>
        <div className="deploy-token">
          <input className="input" type="password" autoComplete="new-password" maxLength={500}
                 value={token ?? ""} placeholder={site?.has_token && token === undefined ? t("deploy.tokenSaved") : ""}
                 onChange={(e) => setToken(e.target.value)} />
          {site?.has_token && token !== "" && (
            <button type="button" className="btn btn-ghost btn-small" onClick={() => setToken("")}>
              {t("deploy.tokenRemove")}
            </button>
          )}
        </div>
      </div>
      <div className="field">
        {t("deploy.env")}
        <span className="hint">{t("deploy.envHint")}</span>
        {env.map((r, i) => (
          <div key={i} className="deploy-env">
            <input className="input" placeholder="NAME" value={r.key} maxLength={64} readOnly={r.existing}
                   onChange={(e) => setRow(i, { key: e.target.value })} />
            <input className="input" type="password" autoComplete="new-password" maxLength={2000} value={r.value}
                   placeholder={r.existing ? t("deploy.tokenSaved") : t("deploy.value")}
                   onChange={(e) => setRow(i, { value: e.target.value })} />
            <button type="button" className="btn btn-ghost btn-icon" aria-label={t("common.delete")}
                    onClick={() => setEnv((rows) => rows.filter((_, j) => j !== i))}>
              <Icon name="close" size={16} />
            </button>
          </div>
        ))}
        <button type="button" className="btn btn-ghost btn-small deploy-envadd"
                onClick={() => setEnv((rows) => [...rows, { key: "", value: "", existing: false }])}>
          <Icon name="plus" size={14} />
          {t("deploy.envAdd")}
        </button>
      </div>
      {save.error && <p className="error-text">{save.error.message}</p>}
      {remove.error && <p className="error-text">{remove.error.message}</p>}
    </Dialog>
  );
}
