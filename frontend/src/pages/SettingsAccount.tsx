import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import {
  downloadBackup, restoreBackup, useAccount, useChangePassword, useDisable2fa, useEnable2fa,
  useNewRecoveryCodes, useSetup2fa,
} from "../api/account";
import { CopyButton, Dialog, Loading } from "../components/ui";

export function AccountSettings() {
  const { t } = useTranslation();
  const account = useAccount();
  if (!account.data) return <Loading error={account.error} />;
  return (
    <>
      <h2 className="section-title">{t("account.password")}</h2>
      <PasswordForm />
      <h2 className="section-title">{t("account.twoFactor")}</h2>
      <TwoFactor enabled={account.data.totp_enabled} left={account.data.recovery_codes_left} />
    </>
  );
}

function PasswordForm() {
  const { t } = useTranslation();
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  return (
    <form className="card card-pad stack-lg" onSubmit={(e) => {
      e.preventDefault();
      setError(""); setDone(false);
      if (next !== repeat) { setError(t("auth.passwordsDiffer")); return; }
      change.mutate({ current, new: next }, { onSuccess: () => { setDone(true); setCurrent(""); setNext(""); setRepeat(""); } });
    }}>
      <label className="field">
        {t("account.current")}
        <input className="input" type="password" autoComplete="current-password" required value={current}
               onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <div className="grid-2">
        <label className="field">
          {t("account.new")} <span className="hint">{t("auth.passwordHint")}</span>
          <input className="input" type="password" autoComplete="new-password" required minLength={10} value={next}
                 onChange={(e) => setNext(e.target.value)} />
        </label>
        <label className="field">
          {t("auth.confirmPassword")}
          <input className="input" type="password" autoComplete="new-password" required value={repeat}
                 onChange={(e) => setRepeat(e.target.value)} />
        </label>
      </div>
      <div className="channel-actions">
        <button type="submit" className="btn btn-primary" disabled={change.isPending}>{t("account.change")}</button>
        {done && <span className="state-up">{t("account.changed")}</span>}
        {(error || change.error) && <span className="error-text">{error || change.error?.message}</span>}
      </div>
    </form>
  );
}

function RecoveryCodes({ codes, onClose }: { codes: string[]; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <Dialog title={t("account.recoveryTitle")} onClose={onClose}
            footer={<><span className="spacer" /><button type="button" className="btn btn-primary" onClick={onClose}>{t("account.saved")}</button></>}>
      <p className="notice" style={{ margin: 0 }}>{t("account.recoveryText")}</p>
      <div className="key-row">
        <pre className="code recovery">{codes.join("\n")}</pre>
        <CopyButton value={codes.join("\n")} label={t("common.copy")} />
      </div>
    </Dialog>
  );
}

function TwoFactor({ enabled, left }: { enabled: boolean; left: number }) {
  const { t } = useTranslation();
  const setup = useSetup2fa();
  const enable = useEnable2fa();
  const disable = useDisable2fa();
  const renew = useNewRecoveryCodes();
  const [qr, setQr] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const [mode, setMode] = useState<"" | "disable" | "renew">("");

  useEffect(() => {
    if (setup.data) QRCode.toDataURL(setup.data.uri, { margin: 1, width: 200 }).then(setQr);
  }, [setup.data]);

  if (enabled) {
    return (
      <section className="card card-pad stack-lg">
        <p style={{ margin: 0 }}><span className="state-up">●</span> {t("account.on", { count: left })}</p>
        {mode === "" ? (
          <div className="channel-actions">
            <button type="button" className="btn" onClick={() => setMode("renew")}>{t("account.newCodes")}</button>
            <button type="button" className="btn btn-danger-ghost" onClick={() => setMode("disable")}>{t("account.turnOff")}</button>
          </div>
        ) : (
          <form className="stack-md" onSubmit={(e) => {
            e.preventDefault();
            if (mode === "disable") disable.mutate({ password, code }, { onSuccess: () => { setMode(""); setCode(""); setPassword(""); } });
            else renew.mutate({ code }, { onSuccess: (r) => { setCodes(r.recovery_codes); setMode(""); setCode(""); } });
          }}>
            <div className="grid-2">
              {mode === "disable" && (
                <label className="field">
                  {t("auth.password")}
                  <input className="input" type="password" autoComplete="current-password" required value={password}
                         onChange={(e) => setPassword(e.target.value)} />
                </label>
              )}
              <label className="field">
                {t("auth.code")}
                <input className="input setup-code" autoComplete="one-time-code" required value={code}
                       onChange={(e) => setCode(e.target.value)} />
              </label>
            </div>
            <div className="channel-actions">
              <button type="submit" className={mode === "disable" ? "btn btn-danger" : "btn btn-primary"}
                      disabled={disable.isPending || renew.isPending}>
                {mode === "disable" ? t("account.turnOff") : t("account.newCodes")}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setMode("")}>{t("common.cancel")}</button>
              {(disable.error || renew.error) && <span className="error-text">{(disable.error || renew.error)?.message}</span>}
            </div>
          </form>
        )}
        {codes && <RecoveryCodes codes={codes} onClose={() => setCodes(null)} />}
      </section>
    );
  }

  return (
    <section className="card card-pad stack-lg">
      <p className="muted" style={{ margin: 0 }}>{t("account.twoFactorText")}</p>
      {!setup.data ? (
        <div>
          <button type="button" className="btn btn-primary" disabled={setup.isPending} onClick={() => setup.mutate()}>
            {t("account.turnOn")}
          </button>
        </div>
      ) : (
        <form className="totp-setup" onSubmit={(e) => {
          e.preventDefault();
          enable.mutate({ code }, { onSuccess: (r) => { setCodes(r.recovery_codes); setup.reset(); setCode(""); } });
        }}>
          {qr && <img src={qr} alt={t("account.qrAlt")} className="qr" width={180} height={180} />}
          <div className="stack-md">
            <ol className="steps">
              <li>{t("account.step1")}</li>
              <li>{t("account.step2")}</li>
            </ol>
            <div className="field">
              {t("account.manualKey")}
              <div className="key-row">
                <code className="secret">{setup.data.secret.match(/.{1,4}/g)?.join(" ")}</code>
                <CopyButton value={setup.data.secret} label={t("common.copy")} />
              </div>
            </div>
            <label className="field">
              {t("auth.code")}
              <input className="input setup-code" autoComplete="one-time-code" inputMode="numeric" required maxLength={8}
                     placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} />
            </label>
            <div className="channel-actions">
              <button type="submit" className="btn btn-primary" disabled={enable.isPending}>{t("account.confirm")}</button>
              <button type="button" className="btn btn-ghost" onClick={() => setup.reset()}>{t("common.cancel")}</button>
              {enable.error && <span className="error-text">{enable.error.message}</span>}
            </div>
          </div>
        </form>
      )}
      {codes && <RecoveryCodes codes={codes} onClose={() => setCodes(null)} />}
    </section>
  );
}

export function BackupSettings() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [pass, setPass] = useState("");
  const [pass2, setPass2] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [rpass, setRpass] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [rerror, setRerror] = useState("");

  return (
    <>
      <h2 className="section-title">{t("backup.create")}</h2>
      <form className="card card-pad stack-lg" onSubmit={async (e) => {
        e.preventDefault();
        setMsg(null);
        if (pass !== pass2) { setMsg({ ok: false, text: t("auth.passwordsDiffer") }); return; }
        setBusy(true);
        try {
          await downloadBackup(pass);
          setMsg({ ok: true, text: t("backup.created") });
          setPass(""); setPass2("");
        } catch (err) {
          setMsg({ ok: false, text: err instanceof Error ? err.message : String(err) });
        } finally {
          setBusy(false);
        }
      }}>
        <p className="muted" style={{ margin: 0 }}>{t("backup.createText")}</p>
        <div className="grid-2">
          <label className="field">
            {t("backup.passphrase")} <span className="hint">{t("backup.passphraseHint")}</span>
            <input className="input" type="password" autoComplete="new-password" required minLength={10} value={pass}
                   onChange={(e) => setPass(e.target.value)} />
          </label>
          <label className="field">
            {t("auth.confirmPassword")}
            <input className="input" type="password" autoComplete="new-password" required value={pass2}
                   onChange={(e) => setPass2(e.target.value)} />
          </label>
        </div>
        <div className="channel-actions">
          <button type="submit" className="btn btn-primary" disabled={busy}>{t("backup.download")}</button>
          {msg && <span className={msg.ok ? "state-up" : "error-text"}>{msg.text}</span>}
        </div>
      </form>

      <h2 className="section-title">{t("backup.restore")}</h2>
      <form className="card card-pad stack-lg" onSubmit={(e) => { e.preventDefault(); setRerror(""); setConfirm(true); }}>
        <p className="muted" style={{ margin: 0 }}>{t("backup.restoreText")}</p>
        <div className="grid-2">
          <label className="field">
            {t("backup.file")}
            <input className="input" type="file" accept=".xtb" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <label className="field">
            {t("backup.passphrase")}
            <input className="input" type="password" autoComplete="off" required value={rpass}
                   onChange={(e) => setRpass(e.target.value)} />
          </label>
        </div>
        <div className="channel-actions">
          <button type="submit" className="btn btn-danger-ghost" disabled={!file}>{t("backup.restoreButton")}</button>
          {rerror && <span className="error-text">{rerror}</span>}
        </div>
      </form>

      {confirm && file && (
        <Dialog title={t("backup.confirmTitle")} onClose={() => setConfirm(false)}
                onSubmit={async () => {
                  setBusy(true);
                  try {
                    await restoreBackup(file, rpass);
                    qc.clear();
                    navigate("/login", { replace: true });
                  } catch (err) {
                    setRerror(err instanceof Error ? err.message : String(err));
                    setConfirm(false);
                  } finally {
                    setBusy(false);
                  }
                }}
                footer={<>
                  <span className="spacer" />
                  <button type="button" className="btn" onClick={() => setConfirm(false)}>{t("common.cancel")}</button>
                  <button type="submit" className="btn btn-danger" disabled={busy}>
                    {busy ? t("backup.restoring") : t("backup.restoreButton")}
                  </button>
                </>}>
          <p style={{ margin: 0 }}>{t("backup.confirmText", { name: file.name })}</p>
        </Dialog>
      )}
    </>
  );
}
