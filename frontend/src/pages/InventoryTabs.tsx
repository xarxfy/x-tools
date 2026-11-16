import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useInventory, useNetwork, useNetworkEntries, type InventoryRow, type NetItem } from "../api/inventory";
import { useCan } from "../api/users";
import { DataTable, downloadCsv, ipSortKey, type Column } from "../components/DataTable";
import { ago, fmtDuration } from "../components/format";
import { ConfirmDelete, Dialog, Empty, Loading, SearchField, matches } from "../components/ui";

const KIND_KEY: Record<string, string> = { linux: "kinds.linux", proxmox: "kinds.proxmox", docker: "kinds.docker", local: "inventory.thisServer" };

/** One row per server: system, kernel, agent version, updates, uptime – with a hint for systems that are out of support. */
export function InventoryTab() {
  const { t } = useTranslation();
  const inventory = useInventory();
  const [query, setQuery] = useState("");
  if (!inventory.data) return <Loading error={inventory.error} retry={() => inventory.refetch()} />;
  const rows = inventory.data.filter((r) => matches(query, r.name, r.hostname, r.os, r.kernel, r.group, ...r.tags, ...r.ips));

  const columns: Column<InventoryRow>[] = [
    { key: "name", label: t("inventory.name"), value: (r) => r.name, render: (r) => <Link to={r.link}><strong>{r.name}</strong></Link> },
    { key: "kind", nowrap: true, label: t("inventory.kind"), value: (r) => t(KIND_KEY[r.kind] ?? r.kind), render: (r) => <span className="badge">{t(KIND_KEY[r.kind] ?? r.kind)}</span> },
    { key: "group", hideSmall: true, label: t("inventory.group"), value: (r) => r.group, render: (r) => r.group || <span className="muted">–</span> },
    { key: "tags", hideSmall: true, label: t("inventory.tags"), value: (r) => r.tags.join(" "), csv: (r) => r.tags.join(" "), render: (r) => r.tags.map((x) => <span key={x} className="tag">#{x}</span>) },
    {
      key: "os", label: t("inventory.os"), value: (r) => r.os,
      csv: (r) => [r.os, r.support.state === "eol" ? `support ended ${r.support.until}` : r.support.state === "soon" ? `support ends ${r.support.until}` : ""].filter(Boolean).join(" – "),
      render: (r) => (
        <>
          {r.os || <span className="muted">–</span>}
          {r.support.state === "eol" && <span className="badge badge-down inv-badge" title={r.support.until}>{t("inventory.eol")}</span>}
          {r.support.state === "soon" && <span className="badge badge-warn inv-badge" title={r.support.until}>{t("inventory.eolSoon", { date: r.support.until })}</span>}
        </>
      ),
    },
    { key: "kernel", hideSmall: true, label: t("inventory.kernel"), value: (r) => r.kernel, render: (r) => r.kernel || <span className="muted">–</span> },
    { key: "ips", nowrap: true, label: t("inventory.ips"), value: (r) => r.ips[0] ? ipSortKey(r.ips[0]) : "", csv: (r) => r.ips.join(" "), render: (r) => <span className="mono small-note">{r.ips.join(", ") || "–"}</span> },
    {
      key: "version", hideSmall: true, nowrap: true, label: t("inventory.agent"), value: (r) => r.version,
      render: (r) => (r.version ? <>{r.version}{r.outdated && <span className="badge badge-warn inv-badge">{t("inventory.outdated")}</span>}</> : <span className="muted">–</span>),
    },
    { key: "uptime", hideSmall: true, nowrap: true, label: t("inventory.uptime"), value: (r) => r.uptime ?? -1, csv: (r) => (r.uptime ? fmtDuration(r.uptime) : ""), render: (r) => (r.uptime ? fmtDuration(r.uptime) : <span className="muted">–</span>) },
    {
      key: "updates", nowrap: true, label: t("inventory.updates"), value: (r) => r.updates ?? -1, csv: (r) => (r.updates === null ? "" : String(r.updates)) + (r.reboot ? " (reboot)" : ""),
      render: (r) => (r.updates === null ? <span className="muted">–</span> : <>{r.updates > 0 ? <span className="badge badge-warn">{r.updates}</span> : <span className="state-up">0</span>}{r.reboot && <span className="badge badge-warn inv-badge">{t("overview.reboot")}</span>}</>),
    },
    { key: "seen", hideSmall: true, nowrap: true, label: t("inventory.lastReport"), value: (r) => r.last_report_at ?? "", csv: (r) => r.last_report_at ?? "", render: (r) => (r.last_report_at ? ago(Date.parse(r.last_report_at) / 1000) : <span className="muted">–</span>) },
  ];
  return (
    <>
      <div className="section-row">
        <p className="muted intro">{t("inventory.intro")}</p>
        <div className="section-tools">
          <SearchField value={query} onChange={setQuery} />
          <button type="button" className="btn" onClick={() => downloadCsv(columns, rows, "x-tools-inventory.csv")}>{t("inventory.export")}</button>
        </div>
      </div>
      {rows.length === 0 ? <Empty>{t("common.noMatch")}</Empty> : (
        <div style={{ marginTop: 16 }}><DataTable columns={columns} rows={rows} rowKey={(r) => r.id} /></div>
      )}
    </>
  );
}

function EntryDialog({ item, onClose }: { item: NetItem | null; onClose: () => void }) {
  const { t } = useTranslation();
  const { save } = useNetworkEntries();
  const [f, setF] = useState({ ip: item?.ip ?? "", name: item?.name ?? "", notes: item?.notes ?? "" });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((x) => ({ ...x, [k]: e.target.value }));
  return (
    <Dialog title={item ? t("network.editEntry") : t("network.addEntry")} onClose={onClose}
            onSubmit={() => save.mutate({ id: item?.entry_id || undefined, ...f }, { onSuccess: onClose })}
            footer={<><span className="spacer" /><button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={save.isPending}>{t("common.save")}</button></>}>
      <p className="hint">{t("network.entryHint")}</p>
      <div className="grid-2">
        <label className="field">{t("network.ip")}<input className="input mono" required autoFocus maxLength={45} placeholder="10.0.0.1" value={f.ip} onChange={set("ip")} /></label>
        <label className="field">{t("network.name")}<input className="input" required maxLength={80} placeholder="Router" value={f.name} onChange={set("name")} /></label>
      </div>
      <label className="field">{t("network.notes")}<input className="input" maxLength={300} value={f.notes} onChange={set("notes")} /></label>
      {save.error && <p className="error-text">{save.error.message}</p>}
    </Dialog>
  );
}

/** All IP addresses X-TOOLS knows: servers, Proxmox guests and your own entries; the same address twice is flagged. */
export function NetworkTab() {
  const { t } = useTranslation();
  const network = useNetwork();
  const canEdit = useCan()("network.edit");
  const { remove } = useNetworkEntries();
  const [query, setQuery] = useState("");
  const [virtual, setVirtual] = useState(false);
  const [editing, setEditing] = useState<NetItem | "new" | null>(null);
  if (!network.data) return <Loading error={network.error} retry={() => network.refetch()} />;
  const rows = network.data.items.filter((i) => (virtual || !i.virtual) && matches(query, i.ip, i.name, i.iface, i.mac, i.network, i.notes, i.source));
  const kindLabel = (k: string) => t(`network.kinds.${k}`);

  const columns: Column<NetItem>[] = [
    { key: "ip", label: t("network.ip"), value: (r) => ipSortKey(r.ip), csv: (r) => r.ip, render: (r) => <span className="mono">{r.ip}</span> },
    { key: "name", label: t("network.name"), value: (r) => r.name, render: (r) => (r.link ? <Link to={r.link}><strong>{r.name}</strong></Link> : <strong>{r.name}</strong>) },
    { key: "kind", label: t("network.type"), value: (r) => kindLabel(r.kind), render: (r) => <span className="badge">{kindLabel(r.kind)}</span> },
    { key: "iface", hideSmall: true, label: t("network.iface"), value: (r) => r.iface, render: (r) => r.iface || <span className="muted">–</span> },
    { key: "network", hideSmall: true, label: t("network.network"), value: (r) => r.network, render: (r) => <span className="mono small-note">{r.network || "–"}</span> },
    { key: "mac", hideSmall: true, label: "MAC", value: (r) => r.mac, render: (r) => <span className="mono small-note">{r.mac || "–"}</span> },
    { key: "notes", label: t("network.notes"), value: (r) => (r.kind === "manual" ? r.notes : r.source), render: (r) => <span className="muted small-note">{r.kind === "manual" ? r.notes : r.source}</span> },
    {
      key: "actions", label: "", value: () => "", csv: () => "",
      render: (r) => canEdit && r.kind === "manual" ? (
        <span className="agent-bar">
          <button type="button" className="btn btn-ghost btn-small" onClick={() => setEditing(r)}>{t("common.edit")}</button>
          <ConfirmDelete compact busy={remove.isPending} onConfirm={() => remove.mutate(r.entry_id)} />
        </span>
      ) : null,
    },
  ];
  return (
    <>
      <div className="section-row">
        <p className="muted intro">{t("network.intro")}</p>
        <div className="section-tools">
          <SearchField value={query} onChange={setQuery} />
          <label className="inline-check small-note"><input type="checkbox" checked={virtual} onChange={(e) => setVirtual(e.target.checked)} />{t("network.showVirtual")}</label>
          <button type="button" className="btn" onClick={() => downloadCsv(columns.slice(0, -1), rows, "x-tools-network.csv")}>{t("inventory.export")}</button>
          {canEdit && <button type="button" className="btn btn-primary" onClick={() => setEditing("new")}>{t("network.addEntry")}</button>}
        </div>
      </div>
      {network.data.conflicts.length > 0 && (
        <div className="card card-pad net-conflicts">
          <strong>{t("network.conflicts", { count: network.data.conflicts.length })}</strong>
          <ul className="plain-list">
            {network.data.conflicts.map((c) => <li key={c.ip}><span className="mono">{c.ip}</span> – {c.names.join(", ")}</li>)}
          </ul>
          <span className="muted small-note">{t("network.conflictHint")}</span>
        </div>
      )}
      {rows.length === 0 ? <Empty>{network.data.items.length ? t("common.noMatch") : t("network.none")}</Empty> : (
        <div style={{ marginTop: 16 }}>
          <DataTable columns={columns} rows={rows} rowKey={(r) => `${r.ip}-${r.name}-${r.iface}-${r.kind}-${r.entry_id}`} rowClass={(r) => (r.conflict ? "is-conflict" : "")} initialSort="ip" />
        </div>
      )}
      {editing && <EntryDialog item={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </>
  );
}
