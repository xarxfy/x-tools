import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Icon, type IconName } from "./Icon";
import { useAppStatus, useLogout, useMe } from "../api/auth";
import "./Layout.css";

const MAIN: { to: string; key: string; icon: IconName }[] = [
  { to: "/", key: "overview", icon: "overview" },
  { to: "/customers", key: "customers", icon: "customers" },
  { to: "/services", key: "services", icon: "services" },
  { to: "/servers", key: "servers", icon: "servers" },
  { to: "/domains", key: "domains", icon: "domains" },
  { to: "/credentials", key: "credentials", icon: "credentials" },
];
const FOOTER: { to: string; key: string; icon: IconName }[] = [
  { to: "/settings", key: "settings", icon: "settings" },
  { to: "/help", key: "help", icon: "help" },
];

export function Layout() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { data: me } = useMe();
  const { data: status } = useAppStatus();
  const logout = useLogout();

  useEffect(() => setOpen(false), [location.pathname]); // close the mobile menu after navigating

  const link = (item: (typeof MAIN)[number], size = 18) => (
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
        <nav className="nav-main" aria-label="Main">
          {MAIN.map((item) => link(item))}
        </nav>
        <div className="side-foot">
          <nav className="nav-foot" aria-label="Settings and help">
            {FOOTER.map((item) => link(item, 16))}
            <button
              type="button"
              className="nav-button"
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate("/login") })}
            >
              <Icon name="logout" size={16} />
              <span>{t("nav.logout")}</span>
            </button>
          </nav>
          <div className="side-meta">
            {me && <span>{t("nav.signedInAs", { name: me.username })}</span>}
            {status && <span>v{status.version}</span>}
          </div>
        </div>
      </aside>
      <main>
        <Outlet />
      </main>
    </div>
  );
}
