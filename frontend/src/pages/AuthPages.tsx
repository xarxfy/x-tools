import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAppStatus, useLogin, useLoginSecondFactor, useMe, useSetup } from "../api/auth";
import { Icon } from "../components/Icon";
import "./AuthPages.css";

function AuthCard({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="auth-page">
      <div className="auth-card card">
        <span className="logo auth-logo">
          <Icon name="logo" size={24} />
        </span>
        <h1>{title}</h1>
        <p className="muted">{subtitle}</p>
        {children}
      </div>
    </div>
  );
}

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const status = useAppStatus();
  const me = useMe(status.data ? !status.data.needs_setup : false);
  const login = useLogin();
  const second = useLoginSecondFactor();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [ticket, setTicket] = useState<string | null>(null);
  const [code, setCode] = useState("");

  if (status.data?.needs_setup) return <Navigate to="/setup" replace />;
  if (me.data) return <Navigate to="/" replace />;

  const done = () => navigate((location.state as { from?: string } | null)?.from ?? "/", { replace: true });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate(
      { username, password },
      { onSuccess: (r) => ("totp_required" in r ? setTicket(r.ticket) : done()) },
    );
  };

  if (ticket) {
    return (
      <AuthCard title={t("auth.codeTitle")} subtitle={t("auth.codeSubtitle")}>
        <form className="auth-form" onSubmit={(e) => {
          e.preventDefault();
          second.mutate({ ticket, code }, {
            onSuccess: done,
            onError: (err) => { if (err.message.includes("expired")) setTicket(null); },
          });
        }}>
          <label className="field">
            {t("auth.code")} <span className="hint">{t("auth.codeHint")}</span>
            <input className="input setup-code" autoComplete="one-time-code" inputMode="text" autoFocus required
                   maxLength={32} value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
          {second.error && <p className="error-text" role="alert">{second.error.message}</p>}
          <button className="btn btn-primary btn-block" disabled={second.isPending}>{t("auth.verify")}</button>
          <button type="button" className="btn btn-ghost btn-block" onClick={() => { setTicket(null); setCode(""); }}>
            {t("common.cancel")}
          </button>
        </form>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={t("auth.loginTitle")} subtitle={t("auth.loginSubtitle")}>
      <form className="auth-form" onSubmit={submit}>
        <label className="field">
          {t("auth.username")}
          <input className="input" autoComplete="username" autoFocus required value={username}
                 onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="field">
          {t("auth.password")}
          <input className="input" type="password" autoComplete="current-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </label>
        {login.error && <p className="error-text" role="alert">{login.error.message}</p>}
        <button className="btn btn-primary btn-block" disabled={login.isPending}>
          {login.isPending ? t("auth.loggingIn") : t("auth.login")}
        </button>
      </form>
    </AuthCard>
  );
}

export function SetupPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const status = useAppStatus();
  const setup = useSetup();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [code, setCode] = useState("");
  const [localError, setLocalError] = useState("");
  const [done, setDone] = useState(false);

  if (status.data && !status.data.needs_setup && !done) return <Navigate to="/login" replace />;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setLocalError("");
    if (password !== confirm) {
      setLocalError(t("auth.passwordsDiffer"));
      return;
    }
    setup.mutate({ username, password, code }, { onSuccess: () => setDone(true) });
  };

  if (done) {
    return (
      <AuthCard title={t("auth.setupTitle")} subtitle="">
        <div className="notice auth-notice">
          <strong>{t("auth.keyHintTitle")}</strong>
          <p>{t("auth.keyHint")}</p>
        </div>
        <button className="btn btn-primary btn-block" onClick={() => navigate("/", { replace: true })}>
          {t("nav.overview")}
        </button>
      </AuthCard>
    );
  }

  return (
    <AuthCard title={t("auth.setupTitle")} subtitle={t("auth.setupSubtitle")}>
      <form className="auth-form" onSubmit={submit}>
        <label className="field">
          {t("auth.setupCode")} <span className="hint">{t("auth.setupCodeHint")}</span>
          <input className="input setup-code" required autoFocus autoComplete="off" spellCheck={false}
                 placeholder="ABCD-EFGH" maxLength={32} value={code} onChange={(e) => setCode(e.target.value)} />
        </label>
        <label className="field">
          {t("auth.username")} <span className="hint">{t("auth.usernameHint")}</span>
          <input className="input" autoComplete="username" required minLength={3} maxLength={64}
                 pattern="[A-Za-z0-9._\-]{3,64}" value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="field">
          {t("auth.password")} <span className="hint">{t("auth.passwordHint")}</span>
          <input className="input" type="password" autoComplete="new-password" required minLength={10}
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label className="field">
          {t("auth.confirmPassword")}
          <input className="input" type="password" autoComplete="new-password" required value={confirm}
                 onChange={(e) => setConfirm(e.target.value)} />
        </label>
        {(localError || setup.error) && (
          <p className="error-text" role="alert">{localError || setup.error?.message}</p>
        )}
        <button className="btn btn-primary btn-block" disabled={setup.isPending}>
          {setup.isPending ? t("auth.creating") : t("auth.createAccount")}
        </button>
      </form>
    </AuthCard>
  );
}
