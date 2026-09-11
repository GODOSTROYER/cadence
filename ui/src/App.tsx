import { MotionConfig } from "framer-motion";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { Skeleton } from "@/components/Skeleton";
import { ToastProvider } from "@/components/Toast";

const Overview = lazy(() => import("@/pages/Overview"));
const AgentPlayground = lazy(() => import("@/pages/AgentPlayground"));
const Evaluation = lazy(() => import("@/pages/Evaluation"));
const GoldenExplorer = lazy(() => import("@/pages/GoldenExplorer"));
const FailureModes = lazy(() => import("@/pages/FailureModes"));
const Rate = lazy(() => import("@/pages/Rate"));
const Decisions = lazy(() => import("@/pages/Decisions"));
const Method = lazy(() => import("@/pages/Method"));
const NotFound = lazy(() => import("@/pages/NotFound"));

/** Router basename follows Vite's `base` so the app works under a sub-path (e.g. GitHub Pages). */
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

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <ToastProvider>
        <BrowserRouter basename={BASENAME} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes>
            <Route element={<AppShell />}>
              <Route
                index
                element={
                  <Suspense fallback={<RouteFallback />}>
                    <Overview />
                  </Suspense>
                }
              />
              <Route path="agent" element={<Suspense fallback={<RouteFallback />}><AgentPlayground /></Suspense>} />
              <Route path="eval" element={<Suspense fallback={<RouteFallback />}><Evaluation /></Suspense>} />
              <Route path="golden" element={<Suspense fallback={<RouteFallback />}><GoldenExplorer /></Suspense>} />
              <Route path="failures" element={<Suspense fallback={<RouteFallback />}><FailureModes /></Suspense>} />
              <Route path="rate" element={<Suspense fallback={<RouteFallback />}><Rate /></Suspense>} />
              <Route path="decisions" element={<Suspense fallback={<RouteFallback />}><Decisions /></Suspense>} />
              <Route path="method" element={<Suspense fallback={<RouteFallback />}><Method /></Suspense>} />
              <Route path="*" element={<Suspense fallback={<RouteFallback />}><NotFound /></Suspense>} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </MotionConfig>
  );
}
