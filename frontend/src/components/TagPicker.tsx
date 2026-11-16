import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useCan } from "../api/users";
import { useTagClass, useTags } from "../api/organize";

/** Pick tags from the central list (they are created in Administration → Order). */
export function TagPicker({ value, onChange }: { value: string[]; onChange: (tags: string[]) => void }) {
  const { t } = useTranslation();
  const tags = useTags().data ?? [];
  const tagClass = useTagClass();
  const can = useCan()("admin.organize");
  const has = (name: string) => value.some((x) => x.toLowerCase() === name.toLowerCase());
  const toggle = (name: string) => onChange(has(name) ? value.filter((x) => x.toLowerCase() !== name.toLowerCase()) : [...value, name]);
  if (!tags.length) {
    return (
      <span className="hint">
        {t("organize.noTagsYet")} {can && <Link to="/admin?tab=organize">{t("organize.manage")}</Link>}
      </span>
    );
  }
  return (
    <>
      <div className="chips">
        {tags.map((x) => (
          <button key={x.id} type="button" aria-pressed={has(x.name)} onClick={() => toggle(x.name)}
                  className={`chip pick-chip ${has(x.name) ? tagClass(x.name) : ""}${has(x.name) ? " is-on" : ""}`}>
            {has(x.name) ? "✓ " : ""}#{x.name}
          </button>
        ))}
      </div>
      {can && <Link className="small-note" to="/admin?tab=organize">{t("organize.manage")}</Link>}
    </>
  );
}
