import { useState, type ReactNode } from "react";

export interface Column<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  /** Value to sort by (and to export as CSV unless `csv` is given). */
  value: (row: T) => string | number;
  csv?: (row: T) => string;
  nowrap?: boolean;
  /** hidden on phones, where the table has to be narrow */
  hideSmall?: boolean;
}

/** IPv4 addresses sort numerically, IPv6 after them as text. */
export function ipSortKey(ip: string): string {
  const parts = ip.split(".");
  return parts.length === 4 ? parts.map((p) => p.padStart(3, "0")).join(".") : `z${ip}`;
}

export function downloadCsv<T>(columns: Column<T>[], rows: T[], filename: string) {
  const esc = (v: string) => (/[",\n;]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const lines = [columns.map((c) => esc(c.label)).join(","),
    ...rows.map((r) => columns.map((c) => esc(c.csv ? c.csv(r) : String(c.value(r) ?? ""))).join(","))];
  const url = URL.createObjectURL(new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** A table whose columns sort when their heading is clicked. */
export function DataTable<T>({ columns, rows, rowKey, rowClass, initialSort }: {
  columns: Column<T>[]; rows: T[]; rowKey: (row: T) => string; rowClass?: (row: T) => string; initialSort?: string;
}) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 }>({ key: initialSort ?? columns[0].key, dir: 1 });
  const col = columns.find((c) => c.key === sort.key) ?? columns[0];
  const sorted = [...rows].sort((a, b) => {
    const x = col.value(a), y = col.value(b);
    return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true })) * sort.dir;
  });
  return (
    <div className="card data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.hideSmall ? "hide-sm" : undefined} aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                <button type="button" onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? (-s.dir as 1 | -1) : 1 }))}>
                  {c.label}{sort.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={rowKey(r)} className={rowClass?.(r)}>
              {columns.map((c) => <td key={c.key} className={[c.nowrap ? "nowrap" : "", c.hideSmall ? "hide-sm" : ""].filter(Boolean).join(" ") || undefined}>{c.render(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
