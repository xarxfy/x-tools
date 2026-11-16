import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import "./i18n";
import "./styles/tokens.css";
import "./styles/base.css";

import { AuthGate } from "./components/AuthGate";
import { Layout } from "./components/Layout";
import { LoginPage, SetupPage } from "./pages/AuthPages";
import { NotFoundPage } from "./pages/SimplePages";
import { OverviewPage } from "./pages/OverviewPage";
import { AccountPage, MovedRedirect, SettingsRedirect } from "./pages/AccountPage";
import { DomainsHub, MonitoringHub, ServicesHub } from "./pages/Hubs";
import { HelpPage } from "./pages/HelpPage";
import { CustomerPage, CustomersPage } from "./pages/CustomersPage";
import { DockerPage, ProxmoxPage, ServerRedirect } from "./pages/FleetPages";
import { ServerRoute, ServersPage } from "./pages/ServersPage";
import { AdminPage } from "./pages/AdminPage";
import { AssistantPage } from "./pages/AssistantPage";
import { GuestPage } from "./pages/GuestPage";
import "./styles/mobile.css"; // last: phone rules override the page styles

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: true, retry: 1 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route
            element={
              <AuthGate>
                <Layout />
              </AuthGate>
            }
          >
            <Route index element={<OverviewPage />} />
            <Route path="/services" element={<ServicesHub />} />
            <Route path="/services/new" element={<AssistantPage />} />
            <Route path="/customers" element={<CustomersPage />} />
            <Route path="/customers/:id" element={<CustomerPage />} />
            <Route path="/domains" element={<DomainsHub />} />
            <Route path="/servers" element={<ServersPage />} />
            <Route path="/servers/:id" element={<ServerRoute />} />
            <Route path="/servers/:id/guest/:node/:vmid" element={<ServerRedirect />} />
            <Route path="/proxmox/:id/:node/:vmid" element={<GuestPage />} />
            <Route path="/monitoring" element={<MonitoringHub />} />
            <Route path="/jobs" element={<MovedRedirect to="/monitoring" />} />
            <Route path="/proxmox" element={<ProxmoxPage />} />
            <Route path="/docker" element={<DockerPage />} />
            <Route path="/cloudflare" element={<MovedRedirect to="/domains?view=cloudflare" />} />
            <Route path="/credentials" element={<MovedRedirect to="/services?view=logins" />} />
            <Route path="/settings" element={<SettingsRedirect />} />
            <Route path="/account" element={<AccountPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
