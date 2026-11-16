import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { agentAction } from "../api/docker";
import type { AgentSummary, LinuxInfo, LinuxService } from "../api/monitor";
import { useCan } from "../api/users";
import { fmtBytes, level, pct } from "../components/format";
import { Collapsible, Dialog, Dot, Empty, SearchField, matches } from "../components/ui";
import { FirewallSection, UpdateControl, UsersSection } from "./LinuxAdmin";

const PROTECTED = new Set(["x-tools-agent.service"]);

function serviceState(s: LinuxService): "up" | "down" | "warn" | "off" {
  if (s.active === "failed") return "down";
  if (s.active === "active") return "up";
  if (s.active === "activating" || s.active === "reloading") return "warn";
  return "off";
}

function ServiceActions({ agentId, service, onLogs }: { agentId: string; service: LinuxService; onLogs: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState<"" | "stop" | "restart">("");
  const run = useMutation({
    mutationFn: (verb: string) => agentAction(agentId, { action: `systemd.${verb}`, target: service.name }),
    onSettled: () => {
      setConfirm("");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["agents"] }), 4000);
    },
  });
  const on = service.active === "active";
  const locked = PROTECTED.has(service.name);
  if (run.isPending) return <span className="muted small-note">{t("docker.working")}</span>;
  return (
    <div className="list-side guest-actions">
      {run.error && <span className="error-text small-note" title={run.error.message}>{t("proxmox.failed")}</span>}
      {run.isSuccess && <span className="state-up small-note">{t("proxmox.sent")}</span>}
      {confirm ? (
        <>
          <span className="muted small-note">{t(`linux.confirm.${confirm}`, { name: service.name })}</span>
          <button type="button" className="btn btn-small btn-danger" onClick={() => run.mutate(confirm)}>{t("proxmox.yes")}</button>
          <button type="button" className="btn btn-small btn-ghost" onClick={() => setConfirm("")}>{t("common.cancel")}</button>
        </>
      ) : (
        <>
          <button type="button" className="btn btn-small btn-ghost" onClick={onLogs}>{t("docker.logs")}</button>
          {!locked && (on ? (
            <>
              <button type="button" className="btn btn-small" onClick={() => setConfirm("restart")}>{t("docker.restart")}</button>
              <button type="button" className="btn btn-small btn-stop" onClick={() => setConfirm("stop")}>{t("docker.stop")}</button>
            </>
          ) : (
            <button type="button" className="btn btn-small btn-start" onClick={() => run.mutate("start")}>{t("docker.start")}</button>
          ))}
        </>
      )}
    </div>
  );
}

function RebootButton({ agentId, hostname }: { agentId: string; hostname: string }) {
  const { t } = useTranslation();
  const [confirm, setConfirm] = useState(false);
  const run = useMutation({
    mutationFn: () => agentAction(agentId, { action: "system.reboot", target: "host" }),
    onSettled: () => setConfirm(false),
  });
  if (run.isPending) return <span className="muted small-note">{t("docker.working")}</span>;
  if (run.isSuccess) return <span className="state-up small-note">{t("linux.rebooting")}</span>;
  return confirm ? (
    <>
      <span className="muted small-note">{t("linux.confirm.reboot", { name: hostname })}</span>
      <button type="button" className="btn btn-small btn-danger" onClick={() => run.mutate()}>{t("proxmox.yes")}</button>
      <button type="button" className="btn btn-small btn-ghost" onClick={() => setConfirm(false)}>{t("common.cancel")}</button>
    </>
  ) : (
    <>
      {run.error && <span className="error-text small-note" title={run.error.message}>{t("proxmox.failed")}</span>}
      <button type="button" className="btn btn-small" onClick={() => setConfirm(true)}>{t("linux.reboot")}</button>
    </>
  );
}

export type ServerTab = "overview" | "services" | "network" | "users";

/** The content of one tab on the page of a server. */
export function LinuxTab({ agent, info, tab }: { agent: AgentSummary; info: LinuxInfo; tab: ServerTab }) {
  const { t } = useTranslation();
  const canOperate = useCan()("operator");
  const control = canOperate && agent.control;
  const canManage = useCan()("admin") && agent.control;
  const [query, setQuery] = useState("");
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [allPorts, setAllPorts] = useState(false);
  const [logs, setLogs] = useState<{ name: string; text: string | null; error?: string } | null>(null);
  const [showUpdates, setShowUpdates] = useState(false);

  const services = (info.services ?? []).filter((s) => (!onlyFailed || s.active === "failed") && matches(query, s.name, s.description));
  const failed = (info.services ?? []).filter((s) => s.active === "failed").length;
  const running = (info.services ?? []).filter((s) => s.active === "active").length;
  const ports = info.ports ?? [];

  const openLogs = (name: string) => {
    setLogs({ name, text: null });
    agentAction(agent.id, { action: "systemd.logs", target: name, lines: 300 })
      .then((r) => setLogs({ name, text: r.logs ?? "" }))
      .catch((e: Error) => setLogs({ name, text: "", error: e.message }));
  };

  return (
    <>
      {tab === "overview" && (
        <div className="card card-pad linux-facts">
          {info.os && <span>{info.os}</span>}
          {info.kernel && <span className="muted">Kernel {info.kernel}</span>}
          {info.updates === null || info.updates === undefined ? (
            <span className="muted">{t("linux.updatesUnknown")}</span>
          ) : info.updates.length ? (
            <button type="button" className="badge badge-warn badge-button" onClick={() => setShowUpdates(true)}>
              {t("linux.updates", { count: info.updates.length })}
            </button>
          ) : (
            <span className="state-up">{t("linux.upToDate")}</span>
          )}
          {info.reboot_required && <span className="badge badge-warn">{t("linux.rebootRequired")}</span>}
          <UpdateControl agent={agent} info={info} canManage={canManage} />
          <span className="spacer" />
          {control && <RebootButton agentId={agent.id} hostname={agent.hostname || agent.name} />}
        </div>
      )}

      {tab === "services" && <Collapsible flat title={t("linux.services")}
                   summary={<>
                     <span>{t("linux.summary", { running: running, total: (info.services ?? []).length })}</span>
                     {failed > 0 && <span className="badge badge-down">{t("linux.failed", { count: failed })}</span>}
                   </>}
                   tools={<>
                     {failed > 0 && (
                       <label className="inline-check small-note">
                         <input type="checkbox" checked={onlyFailed} onChange={(e) => setOnlyFailed(e.target.checked)} />
                         {t("linux.onlyFailed")}
                       </label>
                     )}
                     <SearchField value={query} onChange={setQuery} />
                   </>}>
        {info.services == null ? (
          <Empty>{t("linux.noSystemd")}</Empty>
        ) : services.length === 0 ? (
          <Empty>{t("common.noMatch")}</Empty>
        ) : (
          <div className="card list">
            {services.map((s) => (
              <div key={s.name} className="list-row static-row">
                <Dot state={serviceState(s)} />
                <div className="list-main">
                  <div className="list-title">{s.name.replace(/\.service$/, "")}<span className="muted small-note"> {s.sub}</span></div>
                  {s.description && <div className="list-sub">{s.description}</div>}
                </div>
                {control ? <ServiceActions agentId={agent.id} service={s} onLogs={() => openLogs(s.name)} />
                  : canOperate && <button type="button" className="btn btn-small btn-ghost" onClick={() => openLogs(s.name)}>{t("docker.logs")}</button>}
              </div>
            ))}
          </div>
        )}
      </Collapsible>}

      {tab === "network" && <Collapsible flat title={t("linux.ports")} summary={<span>{t("linux.portCount", { count: ports.length })}</span>}>
        {ports.length === 0 ? <Empty>{t("linux.noPorts")}</Empty> : (
          <div className="card list">
            {(allPorts ? ports : ports.slice(0, 10)).map((p) => (
              <div key={`${p.proto}${p.port}${p.address}`} className="list-row static-row">
                <div className="list-main">
                  <div className="list-title"><span className="mono">{p.port}</span> <span className="badge">{p.proto.toUpperCase()}</span></div>
                  <div className="list-sub">{[p.address, p.process].filter(Boolean).join(" · ")}</div>
                </div>
              </div>
            ))}
            {ports.length > 10 && (
              <button type="button" className="btn btn-ghost btn-small list-more" onClick={() => setAllPorts((v) => !v)}>
                {allPorts ? t("linux.less") : t("linux.more", { count: ports.length - 10 })}
              </button>
            )}
          </div>
        )}
      </Collapsible>}

      {tab === "overview" && (info.disks?.length ?? 0) > 0 && (
        <Collapsible flat title={t("linux.disks")}
                     summary={<span>{info.disks!.map((d) => `${d.mount} ${pct(d.used, d.total).toFixed(0)} %`).join(" · ")}</span>}>
          <div className="card list">
            {info.disks!.map((d) => {
              const p = pct(d.used, d.total);
              return (
                <div key={d.mount} className="list-row static-row">
                  <div className="list-main">
                    <div className="list-title mono">{d.mount}</div>
                    <div className="list-sub">{d.fstype} · {fmtBytes(d.used)} / {fmtBytes(d.total)}</div>
                  </div>
                  <div className="guest-bar">
                    <div className="bar"><span className={`bar-${level(p)}`} style={{ width: `${Math.min(100, p)}%` }} /></div>
                  </div>
                  <b className="small-note">{p.toFixed(0)} %</b>
                </div>
              );
            })}
          </div>
        </Collapsible>
      )}

      {tab === "network" && <FirewallSection agent={agent} info={info} canManage={canManage} />}
      {tab === "users" && <UsersSection agent={agent} info={info} canManage={canManage} />}

      {logs && (
        <Dialog wide title={`${logs.name} – ${t("docker.logs")}`} onClose={() => setLogs(null)}
                footer={<><span className="spacer" /><button type="button" className="btn" onClick={() => setLogs(null)}>{t("common.close")}</button></>}>
          {logs.error ? <p className="error-text">{logs.error}</p> : <pre className="code deploy-log">{logs.text === null ? t("common.loading") : logs.text || t("deploy.noLog")}</pre>}
        </Dialog>
      )}
      {showUpdates && (
        <Dialog title={t("linux.updatesTitle")} onClose={() => setShowUpdates(false)}
                footer={<><span className="spacer" /><button type="button" className="btn" onClick={() => setShowUpdates(false)}>{t("common.close")}</button></>}>
          <pre className="code">{(info.updates ?? []).join("\n")}</pre>
        </Dialog>
      )}
    </>
  );
}
