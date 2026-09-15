import { Lock } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { PageTransition } from "@/components/PageTransition";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { describeError, isApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cx } from "@/lib/cx";

export interface SignInProps {
  /** Rendered in place of a locked admin page: says so, and returns to that page after sign-in. */
  inline?: boolean;
  /** Where to go after a successful sign-in (defaults to the page that was locked, else /eval). */
  returnTo?: string;
}

interface FromState {
  from?: string;
}

/** Quiet admin door: serif title, two fields, one error line, and a note on what lives behind it. */
export default function SignIn({ inline = false, returnTo }: SignInProps) {
  useDocumentTitle("Admin");
  const { status, user, login, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const userRef = useRef<HTMLInputElement | null>(null);

  const target = returnTo ?? (inline ? location.pathname + location.search : (location.state as FromState | null)?.from ?? "/eval");

  useEffect(() => {
    userRef.current?.focus();
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy || !username.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
      navigate(target, { replace: true });
    } catch (err) {
      if (isApiError(err) && err.status === 503) setError("Admin sign-in is not configured on this deployment.");
      else if (isApiError(err) && err.status === 401) setError("Wrong username or password.");
      else setError(describeError(err));
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  if (status === "admin" && !inline) {
    return (
      <PageTransition className="mx-auto flex w-full max-w-[420px] flex-col gap-6 py-10 sm:py-16">
        <div>
          <p className="eyebrow mb-3">admin</p>
          <h1 className="t-display t-display-40 text-text">Signed in</h1>
          <p className="mt-3 text-[14px] leading-relaxed text-muted">
            You are <span className="t-mono text-text">{user}</span>. The internal pages are in the sidebar.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/eval" className="btn btn-primary">
            Open the evaluation
          </Link>
          <button type="button" className="btn" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </PageTransition>
    );
  }

  return (
    <PageTransition className={cx("mx-auto flex w-full max-w-[420px] flex-col gap-8", inline ? "py-6 sm:py-10" : "py-10 sm:py-16")}>
      <div>
        <p className="eyebrow mb-3 flex items-center gap-2">
          <Lock className="size-3" aria-hidden="true" />
          {inline ? "sign in to continue" : "admin"}
        </p>
        <h1 className="t-display t-display-40 text-text">Admin</h1>
        <p className="mt-3 text-[14px] leading-relaxed text-muted">
          The evaluation dashboards, golden set and failure analysis live behind this door; the public site carries the summary.
        </p>
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4" aria-label="Admin sign-in" noValidate>
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] text-muted">Username</span>
          <input
            ref={userRef}
            name="username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={busy}
            className="h-10 rounded-md border border-border-strong bg-bg px-3 text-[14px] text-text placeholder:text-faint disabled:opacity-60"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] text-muted">Password</span>
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
            className="h-10 rounded-md border border-border-strong bg-bg px-3 text-[14px] text-text placeholder:text-faint disabled:opacity-60"
          />
        </label>
        <p role="alert" aria-live="polite" className={cx("min-h-5 text-[13px]", error ? "text-rose" : "text-faint")}>
          {error ?? ""}
        </p>
        <div className="flex items-center justify-between gap-3">
          <Link to="/" className="link text-[13px] text-muted">
            Back to the public site
          </Link>
          <button type="submit" className="btn btn-primary" disabled={busy || !username.trim() || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </div>
      </form>
    </PageTransition>
  );
}
