import "./colors.css";
import i18n from "../i18n";
import { createContext, useContext, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Icon } from "./Icon";
import "./ui.css";

/** Modal dialog based on the native <dialog> element (focus trap, Esc to close). */
export function Dialog({
  title,
  onClose,
  onSubmit,
  children,
  footer,
  wide,
}: {
  title: string;
  onClose: () => void;
  onSubmit?: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el && !el.open) el.showModal();
  }, []);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit?.();
  };
  return (
    <dialog
      ref={ref}
      className={`dialog${wide ? " dialog-wide" : ""}`}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onMouseDown={(e) => e.target === ref.current && onClose()}
    >
      <form onSubmit={submit}>
        <header className="dialog-head">
          <h2>{title}</h2>
          <button type="button" className="btn btn-ghost btn-icon" aria-label={i18n.t("common.close")} onClick={onClose}>
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className="dialog-body">{children}</div>
        {footer && <footer className="dialog-foot">{footer}</footer>}
      </form>
    </dialog>
  );
}

/** True inside a Hub: the title and the tabs are shown by the hub, the page only adds its tools. */
const EmbeddedContext = createContext(false);

export function PageHead({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  const embedded = useContext(EmbeddedContext);
  if (embedded) {
    return (sub || children) ? (
      <header className="page-head page-head-embedded">
        <div>{sub && <p>{sub}</p>}</div>
        {children && <div className="page-actions">{children}</div>}
      </header>
    ) : null;
  }
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}

export function Dot({ state }: { state: "up" | "down" | "warn" | "off" }) {
  return <span className={`dot dot-${state}`} aria-hidden="true" />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="card card-pad empty">{children}</div>;
}

export function Loading({ error, retry }: { error?: unknown; retry?: () => void }) {
  const { t } = useTranslation();
  if (error) {
    return (
      <div className="center-state">
        <div>
          <p>{error instanceof Error ? error.message : t("app.error")}</p>
          {retry && (
            <button type="button" className="btn" onClick={retry}>
              {t("app.retry")}
            </button>
          )}
        </div>
      </div>
    );
  }
  return <div className="center-state">{t("app.loading")}</div>;
}

export function SearchField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useTranslation();
  return (
    <label className="search">
      <Icon name="search" size={16} />
      <input
        className="input"
        type="search"
        placeholder={t("common.search")}
        aria-label={t("common.search")}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

/** Copies text to the clipboard and briefly shows a confirmation. */
export function CopyButton({ value, label }: { value: string; label: string }) {
  const { t } = useTranslation();
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="btn btn-ghost btn-icon"
      title={done ? t("common.copied") : label}
      aria-label={label}
      disabled={!value}
      onClick={async () => {
        await navigator.clipboard.writeText(value);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
    >
      <Icon name={done ? "check" : "copy"} size={16} />
    </button>
  );
}

/** Delete button that asks once more before doing anything. */
export function ConfirmDelete({ onConfirm, busy, compact }: { onConfirm: () => void; busy?: boolean; compact?: boolean }) {
  const { t } = useTranslation();
  const [ask, setAsk] = useState(false);
  if (!ask) {
    return (
      <button type="button" className={`btn btn-danger-ghost${compact ? " btn-icon" : ""}`} onClick={() => setAsk(true)}
              title={t("common.delete")} aria-label={t("common.delete")}>
        <Icon name="trash" size={16} />
        {!compact && t("common.delete")}
      </button>
    );
  }
  return (
    <span className="confirm">
      <span className="muted">{t("common.reallyDelete")}</span>
      <button type="button" className="btn btn-danger" disabled={busy} onClick={onConfirm}>
        {t("common.delete")}
      </button>
      <button type="button" className="btn btn-ghost" onClick={() => setAsk(false)}>
        {t("common.cancel")}
      </button>
    </span>
  );
}

export function rootDomain(domain: string): string {
  const host = domain.split(":")[0];
  const parts = host.split(".");
  return parts.length <= 2 ? host : parts.slice(-2).join(".");
}

export function matches(query: string, ...values: (string | null | undefined)[]): boolean {
  const q = query.trim().toLowerCase();
  return !q || values.some((v) => v && v.toLowerCase().includes(q));
}

/** A section that can be folded: title and a short summary stay visible, the content only when opened. */
export function Collapsible({ title, summary, tools, open: initial = false, flat = false, children }: {
  title: string; summary?: ReactNode; tools?: ReactNode; open?: boolean; flat?: boolean; children: ReactNode;
}) {
  const [open, setOpen] = useState(initial);
  if (flat) {
    // no folding (e.g. on a tab of its own): heading with summary and tools, content always visible
    return (
      <section className="collapsible is-flat">
        <div className="collapsible-head">
          <span className="collapsible-title">{title}</span>
          <span className="collapsible-summary">{summary}</span>
          <span className="spacer" />
          {tools && <span className="collapsible-flat-tools">{tools}</span>}
        </div>
        <div className="collapsible-body">{children}</div>
      </section>
    );
  }
  return (
    <section className={`collapsible${open ? " is-open" : ""}`}>
      <button type="button" className="collapsible-head" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="collapsible-chevron"><Icon name="chevron" size={16} /></span>
        <span className="collapsible-title">{title}</span>
        <span className="collapsible-summary">{summary}</span>
      </button>
      {open && (
        <div className="collapsible-body">
          {tools && <div className="collapsible-tools">{tools}</div>}
          {children}
        </div>
      )}
    </section>
  );
}

/** One page with several tabs (e.g. Services | Logins): the hub shows title and tabs, each tab is a normal page. */
export function Hub({ title, tabs, tab, onTab, children }: {
  title: string; tabs: { key: string; label: string }[]; tab: string; onTab: (key: string) => void; children: ReactNode;
}) {
  return (
    <>
      <header className="page-head"><div><h1>{title}</h1></div></header>
      {tabs.length > 1 && (
        <div className="tabs hub-tabs" role="tablist">
          {tabs.map((x) => (
            <button key={x.key} type="button" role="tab" aria-selected={tab === x.key} className={tab === x.key ? "active" : ""}
                    onClick={() => onTab(x.key)}>{x.label}</button>
          ))}
        </div>
      )}
      <EmbeddedContext.Provider value>{children}</EmbeddedContext.Provider>
    </>
  );
}
