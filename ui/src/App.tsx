import { MotionConfig } from "framer-motion";
import { Suspense, type ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { RequireAdmin } from "@/components/RequireAdmin";
import { Skeleton } from "@/components/Skeleton";
import { ToastProvider } from "@/components/Toast";
import { AuthProvider } from "@/lib/auth";
import { lazyRetry } from "@/lib/lazyRetry";

const Landing = lazyRetry(() => import("@/pages/Landing"), "Landing");
const AgentPlayground = lazyRetry(() => import("@/pages/AgentPlayground"), "AgentPlayground");
const Method = lazyRetry(() => import("@/pages/Method"), "Method");
const SignIn = lazyRetry(() => import("@/pages/SignIn"), "SignIn");
const Evaluation = lazyRetry(() => import("@/pages/Evaluation"), "Evaluation");
const GoldenExplorer = lazyRetry(() => import("@/pages/GoldenExplorer"), "GoldenExplorer");
const FailureModes = lazyRetry(() => import("@/pages/FailureModes"), "FailureModes");
const Rate = lazyRetry(() => import("@/pages/Rate"), "Rate");
const Decisions = lazyRetry(() => import("@/pages/Decisions"), "Decisions");
const NotFound = lazyRetry(() => import("@/pages/NotFound"), "NotFound");

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
