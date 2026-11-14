import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { agentAction } from "../api/docker";
import { useAgent, type PveConfig, type ProxmoxGuest } from "../api/monitor";
import { useCan } from "../api/users";
import { Icon } from "../components/Icon";
import { Dialog, Empty, Loading, PageHead } from "../components/ui";
import { ago, fmtBytes, fmtDuration, level, pct } from "../components/format";
import { GuestActions } from "./ServersPage";
import { FileBlock } from "./AssistantPage";
import "./GuestPage.css";

const OS: Record<string, string> = { l26: "Linux", win11: "Windows 11", win10: "Windows 10", other: "Other" };

export function GuestPage() {
  const { id = "", node = "", vmid = "" } = useParams();
  const { t } = useTranslation();
  const agent = useAgent(id);
  const can = useCan();
  const [editing, setEditing] = useState(false);
  const [grow, setGrow] = useState<string | null>(null);

  if (!agent.data) return <Loading error={agent.error} retry={() => agent.refetch()} />;
  const px = agent.data.report?.proxmox;
  const guest = px?.guests?.find((g) => g.node === node && String(g.vmid) === vmid);
  const back = <p style={{ margin: "0 0 6px" }}><Link to={`/servers/${id}?tab=proxmox`}>‹ {agent.data.name}</Link></p>;
  if (!guest) return <>{back}<Empty>{t("guest.notFound")}</Empty></>;
  const details = px?.details?.guests?.[`${node}/${vmid}`];
  const cfg = details?.config;
  const backups = (px?.details?.backups ?? []).filter((b) => String(b.vmid) === vmid);
  const control = agent.data.control && can("operator");
  const on = guest.status === "running";

  return (
    <>
      {back}
      <PageHead title={`${guest.vmid} · ${guest.name}`}
                sub={[guest.type === "lxc" ? "LXC" : "VM", t(`proxmox.status.${guest.status}`, { defaultValue: guest.status }),
                  on && t("proxmox.upFor", { duration: fmtDuration(guest.uptime) }), `${t("guest.node")} ${guest.node}`]
                  .filter(Boolean).join(" · ")}>
        {control && cfg && (
          <button type="button" className="btn" onClick={() => setEditing(true)}>
            <Icon name="edit" size={16} />{t("common.edit")}
          </button>
        )}
      </PageHead>
      {control && <div className="guest-power"><GuestActions agentId={id} guest={guest} /></div>}

      {!px?.details ? (
        <p className="notice">{t("guest.needsAgent")}</p>
      ) : details?.error ? (
        <p className="notice">{details.error}</p>
      ) : !cfg ? (
        <Empty>{t("guest.noDetails")}</Empty>
      ) : (
        <>
          <p className="muted small-note">{t("guest.updated", { when: ago(details!.fetched_at) })}</p>
          <div className="guest-grid">
            <Resources guest={guest} cfg={cfg} control={!!control} onGrow={setGrow} />
            <Network cfg={cfg} ips={details?.ips} running={on} />
            <section className="card card-pad">
              <h3>{t("guest.snapshots")}</h3>
              {details?.snapshots === null ? <p className="muted">{t("guest.noPermission")}</p>
                : !details?.snapshots?.length ? <p className="muted">{t("guest.none")}</p> : (
                  <ul className="kv-list">
                    {details.snapshots.map((s) => (
                      <li key={s.name}>
                        <span><strong>{s.name}</strong>{s.description && <span className="muted"> · {s.description}</span>}</span>
                        <span className="muted">{s.time ? new Date(s.time * 1000).toLocaleString() : ""}</span>
                      </li>
                    ))}
                  </ul>
                )}
            </section>
            <section className="card card-pad">
              <h3>{t("guest.backups")}</h3>
              {!backups.length ? <p className="muted">{t("guest.noBackups")}</p> : (
                <ul className="kv-list">
                  {backups.slice(0, 10).map((b) => (
                    <li key={b.volid}>
                      <span>
                        {b.time ? new Date(b.time * 1000).toLocaleString() : "?"}
                        <span className="muted"> · {b.storage}{b.notes && ` · ${b.notes}`}</span>
                      </span>
                      <span className="muted">{fmtBytes(b.size ?? undefined)}</span>
                    </li>
                  ))}
                </ul>
              )}
              {backups[0]?.time && Date.now() / 1000 - backups[0].time > 3 * 86400 && (
                <p className="warn-text small-note" style={{ marginBottom: 0 }}>{t("guest.oldBackup", { when: ago(backups[0].time) })}</p>
              )}
            </section>
            <Other guest={guest} cfg={cfg} />
            {details?.conf && (
              <section className="guest-conf">
                <FileBlock file={{
                  name: details.conf.path, lang: "ini", content: details.conf.content,
                  note: details.conf.source === "file" ? t("guest.confFile") : t("guest.confApi"),
                }} />
              </section>
            )}
          </div>
        </>
      )}
      {editing && cfg && <EditDialog agentId={id} guest={guest} cfg={cfg} onClose={() => setEditing(false)} />}
      {grow && cfg && <GrowDialog agentId={id} guest={guest} disk={cfg.disks.find((d) => d.key === grow)!} onClose={() => setGrow(null)} />}
    </>
  );
}

function Resources({ guest, cfg, control, onGrow }: { guest: ProxmoxGuest; cfg: PveConfig; control: boolean; onGrow: (key: string) => void }) {
  const { t } = useTranslation();
  const memPct = guest.status === "running" ? pct(guest.mem, guest.maxmem) : 0;
  return (
    <section className="card card-pad">
      <h3>{t("guest.resources")}</h3>
      <dl className="details compact">
        <dt>CPU</dt>
        <dd>{t("guest.cores", { count: cfg.cores * (cfg.sockets || 1) })}{guest.status === "running" && ` · ${(guest.cpu * 100).toFixed(0)} %`}</dd>
        <dt>{t("servers.memory")}</dt>
        <dd>
          {fmtBytes(cfg.memory * 1024 * 1024)}
          {guest.status === "running" && (
            <span className="inline-bar"><span className={`bar-${level(memPct)}`} style={{ width: `${Math.min(100, memPct)}%` }} /></span>
          )}
        </dd>
        {cfg.swap !== null && (<><dt>Swap</dt><dd>{fmtBytes(cfg.swap * 1024 * 1024)}</dd></>)}
      </dl>
      <h4>{t("guest.disks")}</h4>
      <ul className="kv-list">
        {cfg.disks.map((d) => (
          <li key={d.key}>
            <span>
              <code>{d.key}</code> {d.mountpoint && <span>{d.mountpoint}</span>}
              <span className="muted"> · {d.storage}{!d.backup && ` · ${t("guest.noBackup")}`}</span>
            </span>
            <span className="disk-size">
              {d.size}
              {control && !d.key.startsWith("efidisk") && !d.key.startsWith("tpmstate") && (
                <button type="button" className="btn btn-ghost btn-small" onClick={() => onGrow(d.key)}>{t("guest.grow")}</button>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Network({ cfg, ips, running }: { cfg: PveConfig; ips?: { interface: string; address: string }[]; running: boolean }) {
  const { t } = useTranslation();
  return (
    <section className="card card-pad">
      <h3>{t("guest.network")}</h3>
      {!cfg.nets.length ? <p className="muted">{t("guest.none")}</p> : (
        <ul className="kv-list">
          {cfg.nets.map((n) => (
            <li key={n.key} className="net-item">
              <span>
                <strong>{n.name}</strong> <span className="muted">({n.key}{n.model && `, ${n.model}`})</span>
                <span className="chips">
                  <span className="chip">{n.bridge}{n.vlan && ` · VLAN ${n.vlan}`}</span>
                  {n.ip && <span className="chip">IPv4 {n.ip}{n.gw && ` → ${n.gw}`}</span>}
                  {n.ip6 && <span className="chip">IPv6 {n.ip6}</span>}
                  {n.firewall && <span className="chip">{t("guest.firewall")}</span>}
                </span>
              </span>
              <span className="muted mono">{n.mac}</span>
            </li>
          ))}
        </ul>
      )}
      <h4>{t("guest.currentIps")}</h4>
      {!running ? <p className="muted">{t("guest.notRunning")}</p> : !ips?.length ? (
        <p className="muted">{t("guest.noIps")}</p>
      ) : (
        <ul className="kv-list">
          {ips.map((ip) => <li key={ip.address}><span className="mono">{ip.address}</span><span className="muted">{ip.interface}</span></li>)}
        </ul>
      )}
    </section>
  );
}

function Other({ guest, cfg }: { guest: ProxmoxGuest; cfg: PveConfig }) {
  const { t } = useTranslation();
  const rows: [string, React.ReactNode][] = [
    [t("guest.hostname"), cfg.hostname],
    [t("guest.os"), OS[cfg.ostype] ?? cfg.ostype],
    [t("guest.onboot"), cfg.onboot ? t("guest.yes") : t("guest.no")],
    ...(cfg.startup ? [[t("guest.startup"), cfg.startup] as [string, string]] : []),
    ...(guest.type === "lxc" ? [[t("guest.unprivileged"), cfg.unprivileged ? t("guest.yes") : t("guest.no")] as [string, string]] : []),
    ...(Object.keys(cfg.features).length ? [[t("guest.features"), Object.entries(cfg.features).map(([k, v]) => `${k}=${v}`).join(", ")] as [string, string]] : []),
    ...(cfg.agent !== null ? [[t("guest.qemuAgent"), cfg.agent ? t("guest.yes") : t("guest.no")] as [string, string]] : []),
    ...(cfg.nameserver ? [["DNS", cfg.nameserver] as [string, string]] : []),
  ];
  return (
    <section className="card card-pad">
      <h3>{t("guest.other")}</h3>
      <dl className="details compact">
        {rows.map(([k, v]) => (<div key={k} style={{ display: "contents" }}><dt>{k}</dt><dd>{v || "–"}</dd></div>))}
        <dt>{t("guest.tags")}</dt>
        <dd>{cfg.tags.length ? <span className="chips">{cfg.tags.map((tag) => <span key={tag} className="chip">{tag}</span>)}</span> : "–"}</dd>
      </dl>
    </section>
  );
}

function useGuestAction(agentId: string, guest: ProxmoxGuest) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { action: string; changes?: Record<string, unknown>; disk?: string; add_gb?: number }) =>
      agentAction(agentId, { ...body, target: String(guest.vmid), node: guest.node, type: guest.type } as never),
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ["agents"] }), 4000),
  });
}

function EditDialog({ agentId, guest, cfg, onClose }: { agentId: string; guest: ProxmoxGuest; cfg: PveConfig; onClose: () => void }) {
  const { t } = useTranslation();
  const save = useGuestAction(agentId, guest);
  const [cores, setCores] = useState(cfg.cores);
  const [memory, setMemory] = useState(cfg.memory);
  const [swap, setSwap] = useState(cfg.swap ?? 0);
  const [onboot, setOnboot] = useState(cfg.onboot);
  const [tags, setTags] = useState(cfg.tags.join(", "));

  const submit = () => {
    const changes: Record<string, unknown> = {};
    if (cores !== cfg.cores) changes.cores = cores;
    if (memory !== cfg.memory) changes.memory = memory;
    if (cfg.swap !== null && swap !== cfg.swap) changes.swap = swap;
    if (onboot !== cfg.onboot) changes.onboot = onboot;
    const tagList = tags.split(/[\s,;]+/).map((x) => x.trim().toLowerCase()).filter(Boolean);
    if (tagList.join(";") !== cfg.tags.join(";")) changes.tags = tagList;
    if (!Object.keys(changes).length) return onClose();
    save.mutate({ action: "proxmox.config", changes }, { onSuccess: onClose });
  };

  return (
    <Dialog title={t("guest.editTitle", { name: guest.name })} onClose={onClose} onSubmit={submit}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={save.isPending}>{save.isPending ? t("docker.working") : t("common.save")}</button>
            </>}>
      <div className="grid-2">
        <label className="field">
          {t("guest.coresLabel")}
          <input className="input" type="number" min={1} max={512} required value={cores} onChange={(e) => setCores(Number(e.target.value))} />
        </label>
        <label className="field">
          {t("guest.memoryLabel")} <span className="hint">{fmtBytes(memory * 1024 * 1024)}</span>
          <input className="input" type="number" min={16} step="any" required value={memory} onChange={(e) => setMemory(Number(e.target.value))} />
        </label>
        {cfg.swap !== null && (
          <label className="field">
            {t("guest.swapLabel")} <span className="hint">{fmtBytes(swap * 1024 * 1024)}</span>
            <input className="input" type="number" min={0} step="any" value={swap} onChange={(e) => setSwap(Number(e.target.value))} />
          </label>
        )}
        <label className="field">
          {t("guest.tags")} <span className="hint">{t("guest.tagsHint")}</span>
          <input className="input" value={tags} onChange={(e) => setTags(e.target.value)} />
        </label>
      </div>
      <label className="inline-check">
        <input type="checkbox" checked={onboot} onChange={(e) => setOnboot(e.target.checked)} />
        {t("guest.onbootLabel")}
      </label>
      {guest.type === "qemu" && guest.status === "running" && <p className="muted small-note" style={{ margin: 0 }}>{t("guest.vmPending")}</p>}
      {save.error && <p className="error-text">{save.error.message}</p>}
    </Dialog>
  );
}

function GrowDialog({ agentId, guest, disk, onClose }: {
  agentId: string; guest: ProxmoxGuest; disk: PveConfig["disks"][number]; onClose: () => void;
}) {
  const { t } = useTranslation();
  const save = useGuestAction(agentId, guest);
  const [add, setAdd] = useState(5);
  const newSize = disk.size_bytes ? fmtBytes(disk.size_bytes + add * 1024 ** 3) : "";
  return (
    <Dialog title={t("guest.growTitle", { disk: disk.key })} onClose={onClose}
            onSubmit={() => save.mutate({ action: "proxmox.resize", disk: disk.key, add_gb: add }, { onSuccess: onClose })}
            footer={<>
              <span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={save.isPending}>{save.isPending ? t("docker.working") : t("guest.grow")}</button>
            </>}>
      <p style={{ margin: 0 }}>{t("guest.growText", { disk: disk.key, size: disk.size, storage: disk.storage })}</p>
      <label className="field">
        {t("guest.growBy")} <span className="hint">{newSize && t("guest.newSize", { size: newSize })}</span>
        <input className="input" type="number" min={1} max={4096} required value={add} onChange={(e) => setAdd(Number(e.target.value))} />
      </label>
      <p className="notice" style={{ margin: 0 }}>{t("guest.growNote")}</p>
      {save.error && <p className="error-text">{save.error.message}</p>}
    </Dialog>
  );
}
