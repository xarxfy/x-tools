import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  useCustomers, useSaveCredentials, useSaveService, useServices, type Service,
} from "../api/data";
import { useDocker, allContainers } from "../api/docker";
import { useAbout, useFeatures } from "../api/monitor";
import {
  TEMPLATES, checklist, envFile, proxyFiles, randomSecret, setupCommands, slugify,
  type Ctx, type Expose, type GeneratedFile, type Template,
} from "../assistant/templates";
import { Icon } from "../components/Icon";
import { CopyButton, Dialog, PageHead } from "../components/ui";
import "./AssistantPage.css";

const EXPOSE: Expose[] = ["tunnel", "caddy", "nginx", "traefik", "lan"];
const STEPS = ["template", "basics", "publish", "files"] as const;

/** Ports already used on a host: by services and (on this server) by containers. */
function usedPorts(services: Service[], host: string, containerPorts: number[]): Map<number, string> {
  const used = new Map<number, string>();
  for (const s of services) {
    if ((s.host || "") !== host) continue;
    for (const p of s.ports) used.set(p.port, s.name);
  }
  if (!host) for (const p of containerPorts) if (!used.has(p)) used.set(p, "Docker");
  return used;
}

function suggestPort(base: number, used: Map<number, string>): number {
  let p = base < 1024 ? 8080 : base;
  while (used.has(p)) p++;
  return p;
}

function download(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain" }));
  const a = document.createElement("a");
  a.href = url;
  // "nginx (/etc/nginx/sites-available/app)" → "app", "cloudflared (config.yml)" → "config.yml"
  const inner = name.match(/\(([^)]+)\)/)?.[1];
  a.download = (inner ?? name).split("/").pop()!.trim() || "config.txt";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function FileBlock({ file }: { file: GeneratedFile }) {
  const { t } = useTranslation();
  return (
    <div className="file-block">
      <div className="file-head">
        <code>{file.name}</code>
        <span className="spacer" />
        <CopyButton value={file.content} label={t("common.copy")} />
        <button type="button" className="btn btn-ghost btn-icon" title={t("assistant.download")} aria-label={t("assistant.download")}
                onClick={() => download(file.name, file.content)}>
          <Icon name="download" size={16} />
        </button>
      </div>
      <pre className="code">{file.content}</pre>
      {file.note && <p className="muted small-note file-note">{file.note}</p>}
    </div>
  );
}

function ExposePicker({ value, onChange, http }: { value: Expose; onChange: (e: Expose) => void; http: boolean }) {
  const { t } = useTranslation();
  const options = http ? EXPOSE : (["lan", "tunnel"] as Expose[]).filter((e) => e === "lan");
  return (
    <div className="choice-grid">
      {options.map((e) => (
        <button key={e} type="button" className={`kind-option${value === e ? " selected" : ""}`} onClick={() => onChange(e)}
                role="radio" aria-checked={value === e}>
          <strong>{t(`assistant.expose.${e}`)}</strong>
          <span>{t(`assistant.exposeHint.${e}`)}</span>
        </button>
      ))}
    </div>
  );
}

export function AssistantPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const services = useServices();
  const customers = useCustomers();
  const customersOn = useFeatures().data?.customers ?? false;
  const docker = useDocker();
  const about = useAbout();
  const save = useSaveService();
  const saveCreds = useSaveCredentials();

  const [step, setStep] = useState(0);
  const [template, setTemplate] = useState<Template>(TEMPLATES[0]);
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [folder, setFolder] = useState("");
  const [port, setPort] = useState<number | "">("");
  const [image, setImage] = useState(TEMPLATES[0].image);
  const [domain, setDomain] = useState("");
  const [expose, setExpose] = useState<Expose>("tunnel");
  const [customerId, setCustomerId] = useState("");
  const [storeSecrets, setStoreSecrets] = useState(true);
  const [secrets] = useState<Record<string, string>>(() =>
    Object.fromEntries(TEMPLATES.flatMap((tp) => tp.secrets).map((k) => [k, randomSecret()])));
  const [created, setCreated] = useState<Service | null>(null);
  const [error, setError] = useState("");

  const slug = slugify(name || template.id);
  const home = "~";
  const containerPorts = allContainers(docker.data?.snapshot).flatMap((c) => c.ports.map((p) => p.public));
  const used = useMemo(() => usedPorts(services.data ?? [], host.trim(), containerPorts),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [services.data, host, docker.data]);
  const effectivePort = port === "" ? suggestPort(template.internalPort, used) : port;
  const conflict = used.get(effectivePort);
  const domainOwner = (services.data ?? []).find((s) => domain && s.domains.includes(domain.trim().toLowerCase()));
  const effectiveExpose: Expose = template.http ? expose : "lan";

  const ctx: Ctx = {
    name: name || t("assistant.defaultName"), slug, host: host.trim(), folder: folder || `${home}/${slug}`,
    port: effectivePort, domain: domain.trim().toLowerCase(), expose: effectiveExpose, image: image || template.image,
    timezone: about.data?.timezone ?? "UTC", secrets,
  };
  const files: GeneratedFile[] = [
    ...(template.compose ? [{ name: "docker-compose.yml", lang: "yaml", content: template.compose(ctx) },
      { name: ".env", lang: "dotenv", content: envFile(template, ctx), note: t("assistant.envNote") }] : []),
    ...(template.extraFiles?.(ctx) ?? []),
    ...(template.http ? proxyFiles(ctx) : []),
  ];
  const commands = setupCommands(template, ctx);
  const steps = checklist(template, ctx);

  const pick = (tp: Template) => {
    setTemplate(tp);
    setImage(tp.image);
    setPort("");
    if (!tp.http) setExpose("lan");
  };

  const create = () => {
    setError("");
    save.mutate({
      body: {
        name: ctx.name, host: ctx.host, folder: ctx.folder, type: template.type || "Other",
        ports: [{ port: effectivePort, label: template.http ? "Web" : template.id === "postgres" ? "PostgreSQL" : "" }],
        domains: template.http && ctx.domain ? [ctx.domain] : [], notes: t("assistant.createdNote"),
        customer_id: customerId || null,
        checklist: steps.map((text) => ({ text, done: false })),
      } as never,
    }, {
      onSuccess: (svc) => {
        if (storeSecrets && template.secrets.length) {
          saveCreds.mutate({
            id: svc.id,
            body: template.secrets.map((k) => ({ label: k, username: "", password: secrets[k], url: "", note: t("assistant.generated") })),
          });
        }
        setCreated(svc);
      },
      onError: (e) => setError(e.message),
    });
  };

  if (created) {
    return (
      <>
        <PageHead title={t("assistant.doneTitle", { name: created.name })} sub={t("assistant.doneSub")} />
        <div className="card card-pad stack-lg">
          <p style={{ margin: 0 }}>{t("assistant.doneText")}</p>
          <ol className="steps">{steps.map((s) => <li key={s}>{s}</li>)}</ol>
          <div className="channel-actions">
            <button type="button" className="btn btn-primary" onClick={() => navigate("/services")}>{t("assistant.toServices")}</button>
            <button type="button" className="btn" onClick={() => setCreated(null)}>{t("assistant.backToFiles")}</button>
          </div>
        </div>
        {created && <div className="assistant-files">{files.map((f) => <FileBlock key={f.name} file={f} />)}</div>}
      </>
    );
  }

  const canNext = step === 0 || (step === 1 ? !!name.trim() && !!effectivePort : true);

  return (
    <>
      <p style={{ margin: "0 0 6px" }}><Link to="/services">‹ {t("nav.services")}</Link></p>
      <PageHead title={t("assistant.title")} sub={t("assistant.sub")} />
      <ol className="stepper">
        {STEPS.map((s, i) => (
          <li key={s} className={i === step ? "current" : i < step ? "done" : ""}>
            <button type="button" disabled={i > step} onClick={() => setStep(i)}>
              <span className="step-no">{i < step ? "✓" : i + 1}</span>{t(`assistant.steps.${s}`)}
            </button>
          </li>
        ))}
      </ol>

      <form className="card card-pad stack-lg" onSubmit={(e) => { e.preventDefault(); if (step < 3) setStep(step + 1); else create(); }}>
        {step === 0 && (
          <div className="choice-grid">
            {TEMPLATES.map((tp) => (
              <button key={tp.id} type="button" className={`kind-option${template.id === tp.id ? " selected" : ""}`}
                      onClick={() => pick(tp)} role="radio" aria-checked={template.id === tp.id}>
                <strong>{t(`assistant.templates.${tp.id}`)}</strong>
                <span>{t(`assistant.templatesHint.${tp.id}`)}</span>
              </button>
            ))}
          </div>
        )}

        {step === 1 && (
          <>
            <div className="grid-2">
              <label className="field">
                {t("services.name")}
                <input className="input" required autoFocus maxLength={80} placeholder={t("assistant.namePlaceholder")}
                       value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              {template.compose && (
                <label className="field">
                  {t("assistant.image")} <span className="hint">{t("assistant.imageHint")}</span>
                  <input className="input" value={image} disabled={template.id === "node"} onChange={(e) => setImage(e.target.value)} />
                </label>
              )}
            </div>
            <div className="grid-2">
              <label className="field">
                {t("services.host")} <span className="hint">{t("services.hostHint")}</span>
                <input className="input" placeholder="192.168.1.20" value={host} onChange={(e) => setHost(e.target.value)} />
              </label>
              <label className="field">
                {t("services.folder")}
                <input className="input" placeholder={`${home}/${slug}`} value={folder} onChange={(e) => setFolder(e.target.value)} />
              </label>
            </div>
            <div className="grid-2">
              <label className="field">
                {t("assistant.port")} <span className="hint">{t("assistant.portHint", { internal: template.internalPort })}</span>
                <input className="input" inputMode="numeric" value={port === "" ? effectivePort : port}
                       onChange={(e) => setPort(e.target.value === "" ? "" : Number(e.target.value.replace(/\D/g, "")) || "")} />
              </label>
              {customersOn && (
                <label className="field">
                  {t("services.customer")}
                  <select className="input" value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
                    <option value="">{t("services.noCustomer")}</option>
                    {customers.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </label>
              )}
            </div>
            {conflict && <p className="notice" style={{ margin: 0 }}>{t("assistant.portUsed", { port: effectivePort, by: conflict })}</p>}
          </>
        )}

        {step === 2 && (
          <>
            {template.http ? (
              <>
                <ExposePicker value={expose} onChange={setExpose} http={template.http} />
                {expose !== "lan" && (
                  <label className="field">
                    {t("assistant.domain")} <span className="hint">{t("assistant.domainHint")}</span>
                    <input className="input" required placeholder="app.example.com" value={domain}
                           onChange={(e) => setDomain(e.target.value)} />
                  </label>
                )}
                {domainOwner && <p className="notice" style={{ margin: 0 }}>{t("assistant.domainUsed", { name: domainOwner.name })}</p>}
              </>
            ) : (
              <p className="muted" style={{ margin: 0 }}>{t("assistant.noHttp")}</p>
            )}
            {template.secrets.length > 0 && (
              <label className="inline-check">
                <input type="checkbox" checked={storeSecrets} onChange={(e) => setStoreSecrets(e.target.checked)} />
                {t("assistant.storeSecrets", { names: template.secrets.join(", ") })}
              </label>
            )}
          </>
        )}

        {step === 3 && (
          <>
            <p className="muted" style={{ margin: 0 }}>{t("assistant.filesIntro")}</p>
            {files.length === 0 && <p className="muted">{t("assistant.noFiles")}</p>}
            <div className="assistant-files">{files.map((f) => <FileBlock key={f.name} file={f} />)}</div>
            {commands && <FileBlock file={{ name: t("assistant.commands"), lang: "sh", content: commands }} />}
            <div className="field">
              {t("assistant.checklist")}
              <ol className="steps">{steps.map((s) => <li key={s}>{s}</li>)}</ol>
            </div>
            {error && <p className="error-text">{error}</p>}
          </>
        )}

        <div className="wizard-foot">
          {step > 0 && <button type="button" className="btn" onClick={() => setStep(step - 1)}>{t("assistant.back")}</button>}
          <span className="spacer" />
          <button type="submit" className="btn btn-primary" disabled={!canNext || save.isPending}>
            {step < 3 ? t("assistant.next") : t("assistant.create")}
          </button>
        </div>
      </form>
    </>
  );
}

/** Proxy/tunnel configuration for an existing service. */
export function ConfigDialog({ service, onClose }: { service: Service; onClose: () => void }) {
  const { t } = useTranslation();
  const about = useAbout();
  const [expose, setExpose] = useState<Expose>("tunnel");
  const [domain, setDomain] = useState(service.domains[0] ?? "");
  const [port, setPort] = useState(service.ports[0]?.port ?? 8080);
  const ctx: Ctx = {
    name: service.name, slug: slugify(service.name), host: service.host, folder: service.folder, port,
    domain, expose, image: "", timezone: about.data?.timezone ?? "UTC", secrets: {},
  };
  const files = proxyFiles(ctx);
  return (
    <Dialog wide title={t("assistant.configsTitle", { name: service.name })} onClose={onClose}
            footer={<><span className="spacer" /><button type="button" className="btn btn-primary" onClick={onClose}>{t("common.done")}</button></>}>
      <ExposePicker value={expose} onChange={setExpose} http />
      <div className="grid-2">
        <label className="field">
          {t("assistant.domain")}
          {service.domains.length > 1 ? (
            <select className="input" value={domain} onChange={(e) => setDomain(e.target.value)}>
              {service.domains.map((d) => <option key={d}>{d}</option>)}
            </select>
          ) : (
            <input className="input" value={domain} placeholder="app.example.com" onChange={(e) => setDomain(e.target.value)} />
          )}
        </label>
        <label className="field">
          {t("services.port")}
          {service.ports.length > 1 ? (
            <select className="input" value={port} onChange={(e) => setPort(Number(e.target.value))}>
              {service.ports.map((p) => <option key={p.port} value={p.port}>{p.port}{p.label && ` (${p.label})`}</option>)}
            </select>
          ) : (
            <input className="input" inputMode="numeric" value={port} onChange={(e) => setPort(Number(e.target.value.replace(/\D/g, "")) || 0)} />
          )}
        </label>
      </div>
      {files.length ? files.map((f) => <FileBlock key={f.name} file={f} />) : (
        <p className="muted" style={{ margin: 0 }}>{t("assistant.lanOnly", { host: service.host || "<server-ip>", port })}</p>
      )}
    </Dialog>
  );
}
