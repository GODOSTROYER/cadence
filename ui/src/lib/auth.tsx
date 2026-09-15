/**
 * Admin session for the internal dashboards (/eval, /golden, /failures, /rate, /decisions).
 *
 * Backed by the serverless function's `POST /api/admin/login`, `POST /api/admin/logout` and
 * `GET /api/admin/me` (HttpOnly cookie). Four states:
 *
 * - `loading`     — the first `/api/admin/me` call is in flight.
 * - `anon`        — the server answered and nobody is signed in: admin routes render the sign-in page.
 * - `admin`       — signed in as `user`.
 * - `unavailable` — the admin endpoints do not exist here (plain `npm run dev` against the FastAPI server,
 *                   or `dev:static` with no function): a dev convenience, everything is shown unlocked.
 *
 * Only a 404 (and, in dev builds, a proxy/network failure) means "unavailable"; on a production build any
 * other answer locks the admin routes, so a broken cookie never opens the door.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { adminLogin, adminLogout, adminMe, isApiError } from "@/lib/api";

export type AuthStatus = "loading" | "anon" | "admin" | "unavailable";

export interface AuthState {
  status: AuthStatus;
  user: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Re-check the session (e.g. after a 401 from a data endpoint). */
  refresh: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function classify(e: unknown): AuthStatus {
  if (isApiError(e)) {
    // Only a dev build may treat a missing endpoint as "no admin here"; a production build always locks.
    if (import.meta.env.DEV && (e.status === 404 || e.status === 0 || e.status >= 500)) return "unavailable";
  }
  return "anon";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    adminMe().then(
      (s) => {
        if (!alive) return;
        setUser(s.authenticated ? s.user : null);
        setStatus(s.authenticated ? "admin" : "anon");
      },
      (e: unknown) => {
        if (!alive) return;
        setUser(null);
        setStatus(classify(e));
      },
    );
    return () => {
      alive = false;
    };
  }, [tick]);

  const login = useCallback(async (username: string, password: string) => {
    const s = await adminLogin(username, password);
    setUser(s.authenticated ? s.user : null);
    setStatus(s.authenticated ? "admin" : "anon");
  }, []);

  const logout = useCallback(async () => {
    try {
      await adminLogout();
    } finally {
      setUser(null);
      setStatus("anon");
    }
  }, []);

  const refresh = useCallback(() => setTick((t) => t + 1), []);

  const value = useMemo<AuthState>(() => ({ status, user, login, logout, refresh }), [status, user, login, logout, refresh]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>.");
  return ctx;
}
