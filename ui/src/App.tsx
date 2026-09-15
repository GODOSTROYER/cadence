import { MotionConfig } from "framer-motion";
import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { RequireAdmin } from "@/components/RequireAdmin";
import { Skeleton } from "@/components/Skeleton";
import { ToastProvider } from "@/components/Toast";
import { AuthProvider } from "@/lib/auth";

const Landing = lazy(() => import("@/pages/Landing"));
const AgentPlayground = lazy(() => import("@/pages/AgentPlayground"));
const Method = lazy(() => import("@/pages/Method"));
const SignIn = lazy(() => import("@/pages/SignIn"));
const Evaluation = lazy(() => import("@/pages/Evaluation"));
const GoldenExplorer = lazy(() => import("@/pages/GoldenExplorer"));
const FailureModes = lazy(() => import("@/pages/FailureModes"));
const Rate = lazy(() => import("@/pages/Rate"));
const Decisions = lazy(() => import("@/pages/Decisions"));
const NotFound = lazy(() => import("@/pages/NotFound"));

/** Router basename follows Vite's `base` so the app works under a sub-path (e.g. /hiver-assignment/). */
const BASENAME = import.meta.env.BASE_URL.replace(/\/$/, "");

function RouteFallback() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true" aria-label="Loading page">
      <Skeleton height={12} width={160} />
      <Skeleton height={40} width="45%" radius={8} />
      <Skeleton height={16} width="70%" />
    </div>
  );
}

function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={<RouteFallback />}>{children}</Suspense>;
}

/**
 * Public routes: the landing page, the playground, the method page and the admin door.
 * Admin routes sit behind <RequireAdmin>, which renders the sign-in page in place until a session exists.
 */
export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter basename={BASENAME} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <Routes>
              <Route element={<AppShell />}>
                <Route index element={<Page><Landing /></Page>} />
                <Route path="agent" element={<Page><AgentPlayground /></Page>} />
                <Route path="method" element={<Page><Method /></Page>} />
                <Route path="admin" element={<Page><SignIn /></Page>} />
                <Route element={<RequireAdmin />}>
                  <Route path="eval" element={<Page><Evaluation /></Page>} />
                  <Route path="golden" element={<Page><GoldenExplorer /></Page>} />
                  <Route path="failures" element={<Page><FailureModes /></Page>} />
                  <Route path="rate" element={<Page><Rate /></Page>} />
                  <Route path="decisions" element={<Page><Decisions /></Page>} />
                </Route>
                <Route path="*" element={<Page><NotFound /></Page>} />
              </Route>
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ToastProvider>
    </MotionConfig>
  );
}
