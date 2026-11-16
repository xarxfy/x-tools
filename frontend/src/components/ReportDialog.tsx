import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "./ui";
import { useCustomers } from "../api/data";

/** Asks what the PDF report should contain and downloads it (the session cookie authorizes the request). */
export function ReportDialog({ onClose, customerId = "" }: { onClose: () => void; customerId?: string }) {
  const { t, i18n } = useTranslation();
  const customers = useCustomers();
  const [customer, setCustomer] = useState(customerId);
  const [servers, setServers] = useState(true);
  const [services, setServices] = useState(true);

  const download = () => {
    const q = new URLSearchParams({ lang: i18n.language.startsWith("de") ? "de" : "en", servers: String(servers), services: String(services) });
    if (customer) q.set("customer", customer);
    const a = document.createElement("a");
    a.href = `/api/reports/pdf?${q}`;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
    onClose();
  };

  return (
    <Dialog title={t("report.title")} onClose={onClose} onSubmit={download}
            footer={<><span className="spacer" />
              <button type="button" className="btn" onClick={onClose}>{t("common.cancel")}</button>
              <button type="submit" className="btn btn-primary" disabled={!servers && !services}>{t("report.create")}</button></>}>
      <p className="muted" style={{ margin: 0 }}>{t("report.hint")}</p>
      <label className="field">
        <span>{t("report.scope")}</span>
        <select className="input" value={customer} onChange={(e) => setCustomer(e.target.value)}>
          <option value="">{t("report.allCustomers")}</option>
          {(customers.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
      <label className="check"><input type="checkbox" checked={servers} onChange={(e) => setServers(e.target.checked)} /> {t("report.servers")}</label>
      <label className="check"><input type="checkbox" checked={services} onChange={(e) => setServices(e.target.checked)} /> {t("report.services")}</label>
    </Dialog>
  );
}
