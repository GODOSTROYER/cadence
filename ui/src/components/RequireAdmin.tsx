import { lazy, Suspense } from "react";
import { Outlet } from "react-router-dom";

import { Skeleton } from "@/components/Skeleton";
import { useAuth } from "@/lib/auth";

const SignIn = lazy(() => import("@/pages/SignIn"));

export function AdminSkeleton() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true" aria-label="Checking the admin session">
      <Skeleton height={12} width={160} />
      <Skeleton height={40} width="45%" radius={8} />
      <Skeleton height={16} width="70%" />
    </div>
  );
}

/**
 * Gate for the internal routes. `anon` renders the sign-in page in place (and returns here afterwards);
 * `admin` and `unavailable` (no admin endpoints: local dev) render the page.
 */
export function RequireAdmin() {
  const { status } = useAuth();
  if (status === "loading") return <AdminSkeleton />;
  if (status === "anon") {
    return (
      <Suspense fallback={<AdminSkeleton />}>
        <SignIn inline />
      </Suspense>
    );
  }
  return <Outlet />;
}
