import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { DataTable, type Column } from "../components/DataTable";
import { Empty, Loading, PageHead, SearchField, matches } from "../components/ui";
import { ago } from "../components/format";
import { useMe } from "../api/auth";
import { useAssignees, useTickets, PRIORITIES, type Ticket } from "../api/tickets";
import { DueBadge, PriorityBadge, StatusBadge, TicketDialog } from "./TicketParts";
import "./Tickets.css";

/** All tickets of all customers: who has to do what. */
export function TicketsPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState<"open" | "all" | "done">("open");
  const [who, setWho] = useState("");
  const [prio, setPrio] = useState("");
  const [query, setQuery] = useState("");
  const tickets = useTickets(status);
  const assignees = useAssignees().data ?? [];
  const me = useMe().data;
  const openId = params.get("open");
  const all = useTickets("all");
  const opened = openId ? all.data?.find((x) => x.id === openId) ?? null : null;

  if (!tickets.data) return <Loading error={tickets.error} retry={() => tickets.refetch()} />;
  const myId = assignees.find((u) => u.username === me?.username)?.id;
  const rows = tickets.data
    .filter((x) => !prio || x.priority === prio)
    .filter((x) => !who || (who === "me" ? x.assignee_id === myId : who === "none" ? x.assignee_id === null : String(x.assignee_id) === who))
    .filter((x) => matches(query, `#${x.number}`, x.title, x.customer, x.assignee ?? ""));
  const close = () => { const p = new URLSearchParams(params); p.delete("open"); setParams(p, { replace: true }); };

  const columns: Column<Ticket>[] = [
    { key: "number", label: "#", nowrap: true, value: (x) => x.number, render: (x) => `#${x.number}` },
    { key: "title", label: t("tickets.title"), value: (x) => x.title,
      render: (x) => <button type="button" className="linklike" onClick={() => setParams({ open: x.id }, { replace: true })}>{x.title}</button> },
    { key: "customer", label: t("tickets.customer"), value: (x) => x.customer, render: (x) => <Link to={`/customers/${x.customer_id}`}>{x.customer}</Link> },
    { key: "status", label: t("tickets.statusLabel"), nowrap: true, value: (x) => ["open", "progress", "waiting", "done"].indexOf(x.status), csv: (x) => x.status, render: (x) => <StatusBadge status={x.status} /> },
    { key: "priority", label: t("tickets.priorityLabel"), nowrap: true, value: (x) => PRIORITIES.length - PRIORITIES.indexOf(x.priority), csv: (x) => x.priority, render: (x) => <PriorityBadge priority={x.priority} /> },
    { key: "assignee", label: t("tickets.assignee"), value: (x) => x.assignee ?? "", render: (x) => x.assignee ?? <span className="muted">–</span> },
    { key: "due", label: t("tickets.due"), nowrap: true, value: (x) => x.due ?? "9999", csv: (x) => x.due ?? "", render: (x) => <DueBadge ticket={x} /> },
    { key: "updated", label: t("tickets.updated"), hideSmall: true, nowrap: true, value: (x) => x.updated_at, csv: (x) => x.updated_at, render: (x) => ago(Date.parse(x.updated_at) / 1000) },
  ];

  return (
    <>
      <PageHead title={t("nav.tickets")} sub={t("tickets.sub", { count: rows.length })}>
        <SearchField value={query} onChange={setQuery} />
      </PageHead>
      <div className="filters">
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value as typeof status)} aria-label={t("tickets.filter")}>
          <option value="open">{t("tickets.filterOpen")}</option>
          <option value="done">{t("tickets.filterDone")}</option>
          <option value="all">{t("tickets.filterAll")}</option>
        </select>
        <select className="input" value={who} onChange={(e) => setWho(e.target.value)} aria-label={t("tickets.assignee")}>
          <option value="">{t("tickets.anyone")}</option>
          <option value="me">{t("tickets.mine")}</option>
          <option value="none">{t("tickets.unassigned")}</option>
          {assignees.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
        </select>
        <select className="input" value={prio} onChange={(e) => setPrio(e.target.value)} aria-label={t("tickets.priorityLabel")}>
          <option value="">{t("tickets.anyPriority")}</option>
          {PRIORITIES.map((x) => <option key={x} value={x}>{t(`tickets.priority.${x}`)}</option>)}
        </select>
      </div>
      {rows.length === 0 ? <Empty>{t("tickets.none")}</Empty>
        : <DataTable rows={rows} rowKey={(x) => x.id} columns={columns} initialSort="priority" />}
      {opened && <TicketDialog ticket={opened} onClose={close} />}
    </>
  );
}
