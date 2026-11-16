import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMe } from "../api/auth";
import { useRoleActions, useRoles, type RoleRow } from "../api/users";
import { Icon } from "../components/Icon";
import { ConfirmDelete, Dialog, Empty, Loading } from "../components/ui";
import { roleLabel } from "./SettingsUsers";
import "./AdminRoles.css";

function RoleDialog({ role, roles, onClose }: { role: RoleRow | null; roles: RoleRow[]; onClose: () => void }) {
  const { t } = useTranslation();
  const data = useRoles().data!;
  const { data: me } = useMe();
  const { save } = useRoleActions();
  const mine = new Set(me?.permissions ?? []);
  const [name, setName] = useState(role?.name ?? "");
  const [perms, setPerms] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const readonly = !!role?.locked;
  const fixedName = !!role?.builtin;
  const toggle = (key: string) =>
    setPerms((p) => { const n = new Set(p); if (n.has(key)) n.delete(key); else n.add(key); return n; });
  const copyFrom = (id: string) => {
    const r = roles.find((x) => x.id === id);
    if (r) setPerms(new Set(r.permissions.filter((p) => mine.has(p))));
  };
  return (
    <Dialog wide title={role ? t("roles.editTitle", { name: roleLabel(role, t) }) : t("roles.add")} onClose={onClose}
            onSubmit={() => !readonly && save.mutate({ id: role?.id, name, permissions: [...perms] }, { onSuccess: onClose })}
            footer={<><span className="spacer" /><button type="button" className="btn" onClick={onClose}>{readonly ? t("common.close") : t("common.cancel")}</button>
              {!readonly && <button type="submit" className="btn btn-primary" disabled={save.isPending || !name.trim()}>{t("common.save")}</button>}</>}>
      {readonly && <p className="hint">{t("roles.lockedHint")}</p>}
      {fixedName && !readonly && <p className="hint">{t("roles.builtinHint")}</p>}
      <div className="grid-2">
        <label className="field">
          {t("roles.name")}
          <input className="input" required maxLength={40} disabled={fixedName} value={fixedName && role ? roleLabel(role, t) : name}
                 onChange={(e) => setName(e.target.value)} autoFocus={!role} />
        </label>
        {!role && (
          <label className="field">
            {t("roles.copyFrom")}
            <select className="input" defaultValue="" onChange={(e) => copyFrom(e.target.value)}>
              <option value="">–</option>
              {roles.map((r) => <option key={r.id} value={r.id}>{roleLabel(r, t)}</option>)}
            </select>
          </label>
        )}
      </div>
      {data.areas.map((area) => (
        <fieldset key={area} className="perm-area">
          <legend>{t(`perm.area.${area}`)}</legend>
          {data.permissions.filter((p) => p.area === area).map((p) => {
            const missing = !readonly && !mine.has(p.key);
            return (
              <label key={p.key} className={`perm-row${missing ? " is-missing" : ""}`} title={missing ? t("roles.notYours") : undefined}>
                <input type="checkbox" checked={readonly || perms.has(p.key)} disabled={readonly || missing} onChange={() => toggle(p.key)} />
                <span><strong>{t(`perm.${p.key}.name`)}</strong><span className="muted"> – {t(`perm.${p.key}.hint`)}</span></span>
              </label>
            );
          })}
        </fieldset>
      ))}
      {save.error && <p className="error-text">{save.error.message}</p>}
    </Dialog>
  );
}

export function RolesSettings() {
  const { t } = useTranslation();
  const roles = useRoles();
  const { remove } = useRoleActions();
  const [editing, setEditing] = useState<RoleRow | "new" | null>(null);
  if (!roles.data) return <Loading error={roles.error} />;
  const total = roles.data.permissions.length;
  return (
    <>
      <div className="section-row">
        <p className="muted intro">{t("roles.intro")}</p>
        <button type="button" className="btn btn-primary" onClick={() => setEditing("new")}>
          <Icon name="plus" size={16} />{t("roles.add")}
        </button>
      </div>
      {roles.data.roles.length === 0 ? <Empty>{t("roles.none")}</Empty> : (
        <div className="card list" style={{ marginTop: 16 }}>
          {roles.data.roles.map((r) => (
            <div key={r.id} className="list-row static-row">
              <div className="list-main">
                <div className="list-title">
                  {roleLabel(r, t)}
                  {r.builtin && <span className="badge role-badge">{t("roles.builtin")}</span>}
                </div>
                <div className="list-sub">{t("roles.summary", { perms: r.permissions.length, total, users: r.users })}</div>
                {remove.error && remove.variables === r.id && <p className="error-text">{remove.error.message}</p>}
              </div>
              <div className="list-side">
                <button type="button" className="btn btn-small" onClick={() => setEditing(r)}>{r.locked ? t("roles.view") : t("common.edit")}</button>
                {!r.builtin && <ConfirmDelete onConfirm={() => remove.mutate(r.id)} busy={remove.isPending} />}
              </div>
            </div>
          ))}
        </div>
      )}
      {editing && <RoleDialog role={editing === "new" ? null : editing} roles={roles.data.roles} onClose={() => setEditing(null)} />}
    </>
  );
}
