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
import { SettingsPage } from "./pages/SettingsPage";
import { HelpPage } from "./pages/HelpPage";
import { ServicesPage } from "./pages/ServicesPage";
import { CredentialsPage } from "./pages/CredentialsPage";
import { CustomerPage, CustomersPage } from "./pages/CustomersPage";
import { DomainsPage } from "./pages/DomainsPage";
import { JobsPage } from "./pages/JobsPage";
import { DockerPage, ProxmoxPage, ServerRedirect } from "./pages/FleetPages";
import { ServerRoute, ServersPage } from "./pages/ServersPage";
import { AssistantPage } from "./pages/AssistantPage";
import { CloudflarePage } from "./pages/CloudflarePage";
import { GuestPage } from "./pages/GuestPage";

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
            <Route path="/services" element={<ServicesPage />} />
            <Route path="/services/new" element={<AssistantPage />} />
            <Route path="/customers" element={<CustomersPage />} />
            <Route path="/customers/:id" element={<CustomerPage />} />
            <Route path="/domains" element={<DomainsPage />} />
            <Route path="/servers" element={<ServersPage />} />
            <Route path="/servers/:id" element={<ServerRoute />} />
            <Route path="/servers/:id/guest/:node/:vmid" element={<ServerRedirect />} />
            <Route path="/proxmox/:id/:node/:vmid" element={<GuestPage />} />
            <Route path="/jobs" element={<JobsPage />} />
            <Route path="/proxmox" element={<ProxmoxPage />} />
            <Route path="/docker" element={<DockerPage />} />
            <Route path="/cloudflare" element={<CloudflarePage />} />
            <Route path="/credentials" element={<CredentialsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/help" element={<HelpPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
