import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMe } from "../api/auth";
import {
  useAudit, useAuditFilters, useCreateUser, useDeleteUser, useReset2fa, useResetPassword, useUpdateUser, useUsers,
  type Role, type UserRow,
} from "../api/users";
import { Icon } from "../components/Icon";
import { ConfirmDelete, Dialog, Dot, Empty, Loading } from "../components/ui";
import { ago } from "../components/format";

const ROLES: Role[] = ["viewer", "operator", "admin"];

export function UsersSettings() {
  const { t } = useTranslation();
  const users = useUsers();
  const { data: me } = useMe();
  const update = useUpdateUser();
  const remove = useDeleteUser();
  const reset2fa = useReset2fa();
  const [adding, setAdding] = useState(false);
  const [resetting, setResetting] = useState<UserRow | null>(null);
  if (!users.data) return <Loading error={users.error} />;

  return (
    <>
      <div className="section-row">
        <p className="muted intro">{t("users.intro")}</p>
        <button type="button" className="btn btn-primary" onClick={() => setAdding(true)}>
          <Icon name="plus" size={16} />
          {t("users.add")}
        </button>
      </div>
      <div className="role-legend card card-pad">
        {ROLES.map((r) => (
          <div key={r}><strong>{t(`users.roles.${r}`)}</strong><span className="muted">{t(`users.rolesHint.${r}`)}</span></div>
        ))}
      </div>
      <div className="card list" style={{ marginTop: 16 }}>
        {users.data.map((u) => (
          <div key={u.id} className="list-row static-row">
            <Dot state={u.disabled ? "off" : "up"} />
            <div className="list-main">
              <div className="list-title">
                {u.username}
                {u.id === me?.id && <span className="badge">{t("users.you")}</span>}
                {u.disabled && <span className="badge">{t("users.disabled")}</span>}
                {u.totp_enabled && <span className="badge">2FA</span>}
              </div>
              <div className="list-sub">
                {u.last_login_at ? t("users.lastLogin", { when: ago(Date.parse(u.last_login_at) / 1000) }) : t("users.neverLoggedIn")}
              </div>
              {update.error && update.variables?.id === u.id && <p className="error-text">{update.error.message}</p>}
              {remove.error && remove.variables === u.id && <p className="error-text">{remove.error.message}</p>}
            </div>
            <div className="list-side">
              <select className="input role-select" value={u.role} aria-label={t("users.role")}
                      onChange={(e) => update.mutate({ id: u.id, role: e.target.value as Role })}>
                {ROLES.map((r) => <option key={r} value={r}>{t(`users.roles.${r}`)}</option>)}
              </select>
              <button type="button" className="btn btn-small" onClick={() => setResetting(u)}>{t("users.resetPassword")}</button>
              {u.totp_enabled && u.id !== me?.id && (
                <button type="button" className="btn btn-small" onClick={() => reset2fa.mutate(u.id)}>{t("users.reset2fa")}</button>
              )}
              {u.id !== me?.id && (
                <>
                  <button type="button" className="btn btn-small" onClick={() => update.mutate({ id: u.id, disabled: !u.disabled })}>
                    {u.disabled ? t("agents.enable") : t("agents.disable")}
                  </button>
                  <ConfirmDelete onConfirm={() => remove.mutate(u.id)} busy={remove.isPending} />
                </>
              )}
            </div>
          </div>
        ))}
      </div>
      {adding && <AddUserDialog onClose={() => setAdding(false)} />}
      {resetting && <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />}
    </>
  );
}

function AddUserDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const create = useCreateUser();
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const [password, setPassword] = useState("");
  return (
    <Dialog title={t("users.add")} onClose={onClose}
            onSubmit={() => create.mutate({ username, role, password }, { onSuccess: onClose })}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={create.isPending}>{t("users.create")}</button>
            </>}>
      <label className="field">
        {t("auth.username")} <span className="hint">{t("auth.usernameHint")}</span>
        <input className="input" required autoFocus minLength={3} maxLength={64} pattern="[A-Za-z0-9._\-]{3,64}"
               value={username} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <label className="field">
        {t("users.role")}
        <select className="input" value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLES.map((r) => <option key={r} value={r}>{t(`users.roles.${r}`)} – {t(`users.rolesHint.${r}`)}</option>)}
        </select>
      </label>
      <label className="field">
        {t("users.initialPassword")} <span className="hint">{t("users.initialPasswordHint")}</span>
        <input className="input" type="password" autoComplete="new-password" required minLength={10} value={password}
               onChange={(e) => setPassword(e.target.value)} />
      </label>
      {create.error && <p className="error-text">{create.error.message}</p>}
    </Dialog>
  );
}

function ResetPasswordDialog({ user, onClose }: { user: UserRow; onClose: () => void }) {
  const { t } = useTranslation();
  const reset = useResetPassword();
  const [password, setPassword] = useState("");
  return (
    <Dialog title={t("users.resetTitle", { name: user.username })} onClose={onClose}
            onSubmit={() => reset.mutate({ id: user.id, password }, { onSuccess: onClose })}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={reset.isPending}>{t("users.resetPassword")}</button>
            </>}>
      <label className="field">
        {t("account.new")} <span className="hint">{t("users.resetHint")}</span>
        <input className="input" type="password" autoComplete="new-password" required minLength={10} autoFocus
               value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>
      {reset.error && <p className="error-text">{reset.error.message}</p>}
    </Dialog>
  );
}

const DANGER = ["login.failed", "user.deleted", "agent.deleted", "service.deleted", "customer.deleted", "backup.restored",
  "container.stop", "account.2fa_disabled", "user.2fa_reset"];

export function AuditSettings() {
  const { t } = useTranslation();
  const [user, setUser] = useState("");
  const [action, setAction] = useState("");
  const filters = useAuditFilters();
  const log = useAudit(user, action);
  const rows = log.data?.pages.flat() ?? [];
  return (
    <>
      <div className="toolbar">
        <p className="muted" style={{ margin: 0 }}>{t("audit.intro")}</p>
        <div className="page-actions">
          <select className="input filter-select" value={user} onChange={(e) => setUser(e.target.value)} aria-label={t("audit.user")}>
            <option value="">{t("audit.allUsers")}</option>
            {filters.data?.users.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
          <select className="input filter-select" value={action} onChange={(e) => setAction(e.target.value)} aria-label={t("audit.area")}>
            <option value="">{t("audit.allAreas")}</option>
            {filters.data?.actions.map((a) => <option key={a} value={a}>{t(`audit.areas.${a}`, { defaultValue: a })}</option>)}
          </select>
        </div>
      </div>
      {!log.data ? <Loading error={log.error} /> : rows.length === 0 ? <Empty>{t("audit.none")}</Empty> : (
        <div className="card list">
          {rows.map((a) => (
            <div key={a.id} className="list-row static-row audit-row">
              <span className="audit-time muted" title={new Date(a.ts).toLocaleString()}>
                {new Date(a.ts).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
              </span>
              <div className="list-main">
                <div className="list-title">
                  <span className={DANGER.includes(a.action) ? "state-down" : ""}>{t(`audit.actions.${a.action}`, { defaultValue: a.action })}</span>
                  {a.target && <span className="audit-target">{a.target}</span>}
                </div>
                <div className="list-sub">{[a.username || "–", a.detail, a.ip].filter(Boolean).join(" · ")}</div>
              </div>
            </div>
          ))}
        </div>
      )}
      {log.hasNextPage && (
        <div style={{ textAlign: "center", marginTop: 14 }}>
          <button type="button" className="btn" disabled={log.isFetchingNextPage} onClick={() => log.fetchNextPage()}>
            {t("audit.more")}
          </button>
        </div>
      )}
    </>
  );
}
