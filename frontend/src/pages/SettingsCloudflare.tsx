import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useCloudflareSettings, useRemoveCloudflare, useSaveCloudflareToken } from "../api/cloudflare";
import { ConfirmDelete, Loading } from "../components/ui";
import { ago } from "../components/format";

const PERMISSIONS = ["Zone → Zone → Read", "Zone → DNS → Read", "Account → Cloudflare Tunnel → Read",
  "Account → Access: Apps and Policies → Read"];

export function CloudflareSettings() {
  const { t } = useTranslation();
  const settings = useCloudflareSettings();
  const save = useSaveCloudflareToken();
  const remove = useRemoveCloudflare();
  const [token, setToken] = useState("");
  if (!settings.data) return <Loading error={settings.error} />;
  const s = settings.data;
  const errors = Object.entries(s.errors ?? {});

  return (
    <>
      <p className="muted intro">{t("cloudflare.settingsIntro")}</p>
      {s.configured && (
        <section className="card card-pad stack-md" style={{ marginBottom: 16 }}>
          <p style={{ margin: 0 }}>
            <span className="state-up">●</span>{" "}
            {t("cloudflare.connected", { zones: s.zones, tunnels: s.tunnels, apps: s.access_apps })}
            {s.fetched_at && <span className="muted"> · {t("cloudflare.updated", { when: ago(s.fetched_at) })}</span>}
          </p>
          {errors.length > 0 && (
            <ul className="cf-settings-errors">
              {errors.map(([k, v]) => <li key={k}><code>{k}</code>: {v}</li>)}
            </ul>
          )}
          <div className="channel-actions">
            <Link className="btn" to="/cloudflare">{t("cloudflare.open")}</Link>
            <ConfirmDelete onConfirm={() => remove.mutate()} busy={remove.isPending} />
          </div>
        </section>
      )}
      <form className="card card-pad stack-lg" onSubmit={(e) => {
        e.preventDefault();
        save.mutate(token.trim(), { onSuccess: () => setToken("") });
      }}>
        <div className="field">
          {t("cloudflare.howTo")}
          <ol className="steps">
            <li>{t("cloudflare.step1")}</li>
            <li>{t("cloudflare.step2")}
              <ul className="perm-list">{PERMISSIONS.map((p) => <li key={p}><code>{p}</code></li>)}</ul>
            </li>
            <li>{t("cloudflare.step3")}</li>
          </ol>
        </div>
        <label className="field">
          {t("cloudflare.token")}
          <span className="hint">{s.configured ? t("cloudflare.tokenReplace") : t("cloudflare.tokenHint")}</span>
          <input className="input secret" type="password" autoComplete="off" required minLength={20} value={token}
                 onChange={(e) => setToken(e.target.value)} />
        </label>
        <div className="channel-actions">
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? t("cloudflare.checking") : t("cloudflare.saveToken")}
          </button>
          {save.isSuccess && <span className="state-up">{t("cloudflare.saved")}</span>}
          {save.error && <span className="error-text">{save.error.message}</span>}
        </div>
      </form>
    </>
  );
}
