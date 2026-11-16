import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import { Icon, type IconName } from "./Icon";
import "./SearchPalette.css";

interface Hit {
  type: string;
  title: string;
  subtitle: string;
  link: string;
}

const ICONS: Record<string, IconName | null> = {
  server: "servers", container: "docker", guest: "proxmox", service: "services", domain: "domains",
  customer: "customers", site: "customers", job: "jobs", tag: null,
};

/** Global search (Ctrl/Cmd+K or "/"): servers, containers, guests, services, domains, customers, jobs, tags. */
export function SearchPalette({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const ref = useRef<HTMLDialogElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);

  useEffect(() => { ref.current?.showModal(); }, []);
  useEffect(() => {
    const timer = setTimeout(() => { setQuery(text.trim()); setIndex(0); }, 150);
    return () => clearTimeout(timer);
  }, [text]);

  const results = useQuery({
    queryKey: ["search", query],
    enabled: query.length > 0,
    queryFn: () => api<{ results: Hit[] }>(`/search?q=${encodeURIComponent(query)}`),
    staleTime: 10_000,
  });
  const hits = query ? results.data?.results ?? [] : [];

  const go = (hit: Hit) => { onClose(); navigate(hit.link); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIndex((i) => Math.min(hits.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIndex((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter" && hits[index]) { e.preventDefault(); go(hits[index]); }
  };
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(".sp-hit.active")?.scrollIntoView({ block: "nearest" });
  }, [index, hits.length]);

  let last = "";
  return (
    <dialog ref={ref} className="search-palette" onCancel={(e) => { e.preventDefault(); onClose(); }}
            onMouseDown={(e) => e.target === ref.current && onClose()}>
      <div className="sp-box" onKeyDown={onKey}>
        <div className="sp-input">
          <Icon name="search" size={18} />
          <input autoFocus value={text} placeholder={t("search.placeholder")} aria-label={t("search.title")}
                 onChange={(e) => setText(e.target.value)} />
          <kbd>Esc</kbd>
        </div>
        <div className="sp-list" ref={listRef} role="listbox">
          {!query && <p className="sp-hint">{t("search.hint")}</p>}
          {query && results.isLoading && <p className="sp-hint">{t("app.loading")}</p>}
          {query && !results.isLoading && hits.length === 0 && <p className="sp-hint">{t("search.none", { query })}</p>}
          {hits.map((h, i) => {
            const heading = h.type !== last ? t(`search.types.${h.type}`) : null;
            last = h.type;
            const icon = ICONS[h.type];
            return (
              <div key={`${h.type}-${h.link}-${h.title}-${i}`}>
                {heading && <div className="sp-heading">{heading}</div>}
                <button type="button" role="option" aria-selected={i === index} className={`sp-hit${i === index ? " active" : ""}`}
                        onMouseMove={() => setIndex(i)} onClick={() => go(h)}>
                  <span className="sp-icon">{icon ? <Icon name={icon} size={16} /> : "#"}</span>
                  <span className="sp-title">{h.title}</span>
                  {h.subtitle && <span className="sp-sub">{h.subtitle}</span>}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </dialog>
  );
}
