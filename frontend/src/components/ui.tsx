import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
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
          <button type="button" className="btn btn-ghost btn-icon" aria-label="Close" onClick={onClose}>
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className="dialog-body">{children}</div>
        {footer && <footer className="dialog-foot">{footer}</footer>}
      </form>
    </dialog>
  );
}

export function PageHead({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
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
export function ConfirmDelete({ onConfirm, busy }: { onConfirm: () => void; busy?: boolean }) {
  const { t } = useTranslation();
  const [ask, setAsk] = useState(false);
  if (!ask) {
    return (
      <button type="button" className="btn btn-danger-ghost" onClick={() => setAsk(true)}>
        <Icon name="trash" size={16} />
        {t("common.delete")}
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
