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
import { ComingSoonPage, NotFoundPage, OverviewPage } from "./pages/SimplePages";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: true, retry: 1 } },
});

const SOON = ["customers", "services", "servers", "domains", "credentials", "settings", "help"];

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
            {SOON.map((key) => (
              <Route key={key} path={`/${key}`} element={<ComingSoonPage titleKey={`nav.${key}`} />} />
            ))}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
