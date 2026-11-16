import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Icon, type IconName } from "./Icon";
import { useAppStatus, useLogout, useMe } from "../api/auth";
import { useFeatures } from "../api/monitor";
import { useUpdateInfo } from "../api/ops";
import { useCan } from "../api/users";
import { SearchPalette } from "./SearchPalette";
import "./Layout.css";

type NavItem = { to: string; key: string; icon: IconName };

// The sidebar: Overview, then groups with a heading each, then Monitoring.
const TOP: NavItem[] = [{ to: "/", key: "overview", icon: "overview" }];
const GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "infrastructure",
    items: [
      { to: "/servers", key: "servers", icon: "servers" },
      { to: "/proxmox", key: "proxmox", icon: "proxmox" },
      { to: "/docker", key: "docker", icon: "docker" },
    ],
  },
  {
    title: "manage",
    items: [
      { to: "/services", key: "services", icon: "services" },
      { to: "/domains", key: "domains", icon: "domains" },
      { to: "/customers", key: "customers", icon: "customers" },
    ],
  },
];
const BOTTOM: NavItem[] = [{ to: "/monitoring", key: "monitoring", icon: "jobs" }];
const ADMIN_PERMISSIONS = ["admin.users", "admin.roles", "admin.audit", "admin.settings", "admin.backup"];

export function Layout() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { data: me } = useMe();
  const { data: status } = useAppStatus();
  const logout = useLogout();
  const features = useFeatures();
  // Optional entries: customers when switched on, Proxmox/Docker only when such a server reports.
  const can = useCan();
  const update = useUpdateInfo(can("admin.settings"));
  const adminArea = ADMIN_PERMISSIONS.some((p) => can(p));
  const visible = (item: NavItem) => item.key !== "customers" || features.data?.customers;

  // Ctrl/Cmd+K, or "/" outside of input fields, opens the search
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName ?? "";
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(tag) || (e.target as HTMLElement | null)?.isContentEditable;
      if (((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") || (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey)) {
        e.preventDefault();
        setSearching(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => setOpen(false), [location.pathname]); // close the mobile menu after navigating

  const link = (item: NavItem, size = 18) => (
    <NavLink key={item.to} to={item.to} end={item.to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
      <Icon name={item.icon} size={size} />
      <span>{t(`nav.${item.key}`)}</span>
    </NavLink>
  );

  return (
    <div className="app">
      <aside className={`sidebar${open ? " open" : ""}`}>
        <div className="brand">
          <NavLink to="/" className="brand-link">
            <span className="logo">
              <Icon name="logo" size={18} />
            </span>
            {t("app.name")}
          </NavLink>
          <button
            type="button"
            className="btn btn-ghost menu-toggle"
            aria-label={t("nav.menu")}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            <Icon name="menu" size={22} />
          </button>
        </div>
        <nav className="nav-main" aria-label={t("nav.menu")}>
          <button type="button" className="search-button" onClick={() => setSearching(true)}>
            <Icon name="search" size={16} /><span>{t("search.title")}</span><kbd>{navigator.platform.includes("Mac") ? "⌘K" : "Ctrl K"}</kbd>
          </button>
          {TOP.map((item) => link(item))}
          {GROUPS.map((group) => {
            const items = group.items.filter(visible);
            return items.length > 0 && (
              <div key={group.title} className="nav-group">
                <div className="nav-heading">{t(`nav.${group.title}`)}</div>
                {items.map((item) => link(item))}
              </div>
            );
          })}
          <div className="nav-group">{BOTTOM.map((item) => link(item))}</div>
        </nav>
        <div className="side-foot">
          <nav className="nav-foot" aria-label={t("nav.administration")}>
            {adminArea && link({ to: "/admin", key: "administration", icon: "shield" }, 16)}
            {link({ to: "/help", key: "help", icon: "help" }, 16)}
          </nav>
          <div className="user-row">
            <NavLink to="/account" className={({ isActive }) => `user-chip${isActive ? " active" : ""}`} title={t("nav.account")}>
              <span className="user-avatar">{(me?.username ?? "?").slice(0, 1).toUpperCase()}</span>
              <span className="user-name">
                <strong>{me?.username}</strong>
                <span>{me?.role_name}</span>
              </span>
            </NavLink>
            <button type="button" className="btn btn-ghost btn-icon" title={t("nav.logout")} aria-label={t("nav.logout")}
                    onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}>
              <Icon name="logout" size={16} />
            </button>
          </div>
          <div className="side-meta">
            {status && (
              <span>
                {update.data?.available ? (
                  <NavLink to="/admin?tab=system" className="update-dot" title={t("update.available", { version: update.data.latest })}>
                    v{status.version} ●
                  </NavLink>
                ) : <>v{status.version}</>}
              </span>
            )}
          </div>
        </div>
      </aside>
      <main>
        <Outlet />
      </main>
      {searching && <SearchPalette onClose={() => setSearching(false)} />}
    </div>
  );
}
