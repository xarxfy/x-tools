import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmDelete } from "../components/ui";
import { useCategories, useCategoryActions, useCustomers } from "../api/data";
import { useAgents, useGroupActions, useServerGroups } from "../api/monitor";
import { COLORS, useTagActions, useTags, type Color } from "../api/organize";
import "./AdminOrganize.css";

export function ColorPicker({ value, onChange }: { value: string; onChange: (c: Color) => void }) {
  const { t } = useTranslation();
  return (
    <span className="swatches" role="radiogroup">
      {COLORS.map((c) => (
        <button key={c} type="button" role="radio" aria-checked={value === c} className={`c-${c}`} title={t(`organize.colors.${c}`)}
                aria-label={t(`organize.colors.${c}`)} onClick={() => onChange(c)} />
      ))}
    </span>
  );
}

interface Item { id: string; name: string; color: string }

/** One list of names with colours; optionally in a fixed order (categories, groups). */
function ItemList({ items, usage, onAdd, onUpdate, onRemove, onOrder, placeholder, error, busy }: {
  items: Item[]; usage: (id: string) => string; placeholder: string; error?: Error | null; busy: boolean;
  onAdd: (name: string, color: Color) => void; onUpdate: (id: string, name: string, color: string) => void;
  onRemove: (id: string) => void; onOrder?: (ids: string[]) => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [color, setColor] = useState<Color>("gray");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const move = (i: number, by: number) => {
    const ids = items.map((x) => x.id);
    [ids[i], ids[i + by]] = [ids[i + by], ids[i]];
    onOrder?.(ids);
  };
  const commit = (x: Item) => {
    const v = (edits[x.id] ?? x.name).trim();
    if (v && v !== x.name) onUpdate(x.id, v, x.color);
    setEdits((e) => { const { [x.id]: _, ...rest } = e; return rest; });
  };
  return (
    <div className="card card-pad org-list">
      {items.length === 0 && <p className="muted">{t("organize.empty")}</p>}
      {items.map((x, i) => (
        <div key={x.id} className="org-row">
          <ColorPicker value={x.color} onChange={(c) => onUpdate(x.id, x.name, c)} />
          <input className="input" maxLength={40} value={edits[x.id] ?? x.name} onChange={(e) => setEdits((v) => ({ ...v, [x.id]: e.target.value }))}
                 onBlur={() => commit(x)} onKeyDown={(e) => e.key === "Enter" && (e.currentTarget.blur())} />
          <span className="muted org-usage">{usage(x.id)}</span>
          {onOrder && <>
            <button type="button" className="btn btn-ghost btn-small" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t("customers.up")}>↑</button>
            <button type="button" className="btn btn-ghost btn-small" disabled={i === items.length - 1} onClick={() => move(i, 1)} aria-label={t("customers.down")}>↓</button>
          </>}
          <ConfirmDelete compact busy={busy} onConfirm={() => onRemove(x.id)} />
        </div>
      ))}
      <form className="org-row org-add" onSubmit={(e) => { e.preventDefault(); if (name.trim()) { onAdd(name.trim(), color); setName(""); } }}>
        <ColorPicker value={color} onChange={setColor} />
        <input className="input" maxLength={40} placeholder={placeholder} value={name} onChange={(e) => setName(e.target.value)} />
        <button type="submit" className="btn btn-primary btn-small" disabled={!name.trim() || busy}>{t("organize.add")}</button>
      </form>
      {error && <p className="error-text">{error.message}</p>}
    </div>
  );
}

function Tags() {
  const { t } = useTranslation();
  const tags = useTags().data ?? [];
  const { add, update, merge, remove } = useTagActions();
  const [name, setName] = useState("");
  const [color, setColor] = useState<Color>("gray");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [mergeOf, setMergeOf] = useState<string | null>(null);
  const error = add.error ?? update.error ?? merge.error ?? remove.error;
  const commit = (x: (typeof tags)[number]) => {
    const v = (edits[x.id] ?? x.name).trim();
    if (v && v !== x.name) update.mutate({ id: x.id, name: v, color: x.color });
    setEdits((e) => { const { [x.id]: _, ...rest } = e; return rest; });
  };
  return (
    <div className="card card-pad org-list">
      {tags.length === 0 && <p className="muted">{t("organize.tagsEmpty")}</p>}
      {tags.map((x) => (
        <div key={x.id} className="org-row">
          <ColorPicker value={x.color} onChange={(c) => update.mutate({ id: x.id, name: x.name, color: c })} />
          <input className="input" maxLength={30} value={edits[x.id] ?? x.name} onChange={(e) => setEdits((v) => ({ ...v, [x.id]: e.target.value }))}
                 onBlur={() => commit(x)} onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()} />
          <span className="muted org-usage">{t("organize.tagUsage", { servers: x.servers, customers: x.customers })}</span>
          {mergeOf === x.id ? (
            <select className="input org-merge" autoFocus defaultValue="" onBlur={() => setMergeOf(null)}
                    onChange={(e) => e.target.value && merge.mutate({ id: x.id, into: e.target.value }, { onSuccess: () => setMergeOf(null) })}>
              <option value="">{t("organize.mergeInto")}</option>
              {tags.filter((y) => y.id !== x.id).map((y) => <option key={y.id} value={y.id}>{y.name}</option>)}
            </select>
          ) : tags.length > 1 && <button type="button" className="btn btn-ghost btn-small" onClick={() => setMergeOf(x.id)}>{t("organize.merge")}</button>}
          <ConfirmDelete compact busy={remove.isPending} onConfirm={() => remove.mutate(x.id)} />
        </div>
      ))}
      <form className="org-row org-add" onSubmit={(e) => { e.preventDefault(); if (name.trim()) add.mutate({ name: name.trim(), color }, { onSuccess: () => setName("") }); }}>
        <ColorPicker value={color} onChange={setColor} />
        <input className="input" maxLength={30} placeholder={t("organize.tagPlaceholder")} value={name} onChange={(e) => setName(e.target.value)} />
        <button type="submit" className="btn btn-primary btn-small" disabled={!name.trim() || add.isPending}>{t("organize.add")}</button>
      </form>
      {error && <p className="error-text">{error.message}</p>}
    </div>
  );
}

/** Administration → Order: tags, customer categories and server groups in one place. Everywhere else they are only picked. */
export function AdminOrganize() {
  const { t } = useTranslation();
  const categories = useCategories().data ?? [];
  const customers = useCustomers().data ?? [];
  const cat = useCategoryActions();
  const groups = useServerGroups().data ?? [];
  const agents = useAgents().data ?? [];
  const grp = useGroupActions();
  return (
    <>
      <p className="muted">{t("organize.intro")}</p>
      <h2 className="section-title">{t("organize.tags")}</h2>
      <p className="hint">{t("organize.tagsHint")}</p>
      <Tags />
      <h2 className="section-title">{t("organize.categories")}</h2>
      <p className="hint">{t("organize.categoriesHint")}</p>
      <ItemList items={categories} placeholder={t("customers.categoryPlaceholder")} busy={cat.add.isPending || cat.remove.isPending}
                error={cat.add.error ?? cat.rename.error ?? cat.remove.error ?? cat.order.error}
                usage={(id) => t("organize.customersCount", { count: customers.filter((c) => c.category_id === id).length })}
                onAdd={(name, color) => cat.add.mutate({ name, color })} onUpdate={(id, name, color) => cat.rename.mutate({ id, name, color })}
                onRemove={(id) => cat.remove.mutate(id)} onOrder={(ids) => cat.order.mutate(ids)} />
      <h2 className="section-title">{t("organize.groups")}</h2>
      <p className="hint">{t("organize.groupsHint")}</p>
      <ItemList items={groups} placeholder={t("servers.list.groupPlaceholder")} busy={grp.add.isPending || grp.remove.isPending}
                error={grp.add.error ?? grp.rename.error ?? grp.remove.error ?? grp.order.error}
                usage={(id) => t("organize.serversCount", { count: agents.filter((a) => a.group_id === id).length })}
                onAdd={(name, color) => grp.add.mutate({ name, color })} onUpdate={(id, name, color) => grp.rename.mutate({ id, name, color })}
                onRemove={(id) => grp.remove.mutate(id)} onOrder={(ids) => grp.order.mutate(ids)} />
    </>
  );
}
