import { AlertTriangle, BarChart3, BookOpen, Compass, FlaskConical, ListOrdered, Lock, LogOut, MessageSquareText, Star, type LucideIcon } from "lucide-react";
import { NavLink } from "react-router-dom";

import { Chip, type ChipTone } from "@/components/Chip";
import { Skeleton } from "@/components/Skeleton";
import { Tooltip } from "@/components/Tooltip";
import { useAuth } from "@/lib/auth";
import { cx } from "@/lib/cx";
import type { Health, UiMode } from "@/lib/types";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

/** What every visitor sees. */
export const PUBLIC_NAV: readonly NavItem[] = [
  { to: "/", label: "Overview", icon: Compass, end: true },
  { to: "/agent", label: "Try the agent", icon: MessageSquareText },
  { to: "/method", label: "How it works", icon: FlaskConical },
];

/** Internal tooling, shown once signed in (or when there is no admin door: local dev). */
export const ADMIN_NAV: readonly NavItem[] = [
  { to: "/eval", label: "Evaluation", icon: BarChart3 },
  { to: "/golden", label: "Golden set", icon: BookOpen },
  { to: "/failures", label: "Failure modes", icon: AlertTriangle },
  { to: "/rate", label: "Rate replies", icon: Star },
  { to: "/decisions", label: "Decisions", icon: ListOrdered },
];

export interface SidebarProps {
  /** Icon rail (labels hidden, tooltips on). */
  collapsed?: boolean;
  health: Health | null;
  healthLoading: boolean;
  mode: UiMode;
  /** Close the drawer after navigating (mobile). */
  onNavigate?: () => void;
  className?: string;
}

const MODE_CHIP: Record<UiMode, { label: string; tone: ChipTone; title: string }> = {
  static: { label: "static", tone: "violet", title: "Reading exported results from public/data. The live agent is disabled." },
  "cache-only": { label: "cache-only", tone: "amber", title: "Model network calls are disabled; only exact cached requests can run." },
  live: { label: "live", tone: "green", title: "A Gemini key is configured: free-text messages run the real agent." },
};

function NavList({ items, collapsed, onNavigate }: { items: readonly NavItem[]; collapsed: boolean; onNavigate?: () => void }) {
  return (
    <>
      {items.map((item) => {
        const link = (
          <NavLink key={item.to} to={item.to} end={item.end} onClick={onNavigate} aria-label={collapsed ? item.label : undefined} className={cx("nav-item", collapsed && "w-9 justify-center px-0")}>
            <item.icon aria-hidden="true" />
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        );
        return collapsed ? (
          <Tooltip key={item.to} content={item.label} side="bottom">
            {link}
          </Tooltip>
        ) : (
          link
        );
      })}
    </>
  );
}

/** Wordmark, public navigation, the admin section (door or full nav), and the status chips fed by getHealth(). */
export function Sidebar({ collapsed = false, health, healthLoading, mode, onNavigate, className }: SidebarProps) {
  const auth = useAuth();
  const unlocked = auth.status === "admin" || auth.status === "unavailable";
  const chip = MODE_CHIP[mode];

  return (
    <div className={cx("flex h-full flex-col", className)}>
      <div className={cx("flex h-16 items-center", collapsed ? "justify-center px-0" : "px-3")}>
        <NavLink to="/" className="flex items-center gap-2" aria-label="Cadence home" onClick={onNavigate}>
          <span aria-hidden="true" className="flex h-6 w-5 items-end gap-[2px]">
            <span className="w-[3px] rounded-full bg-green" style={{ height: 8 }} />
            <span className="w-[3px] rounded-full bg-green" style={{ height: 18 }} />
            <span className="w-[3px] rounded-full bg-green" style={{ height: 12 }} />
            <span className="w-[3px] rounded-full bg-green" style={{ height: 22 }} />
          </span>
          {!collapsed && <span className="t-display t-italic text-[28px] leading-none text-text">Cadence</span>}
        </NavLink>
      </div>

      <nav aria-label="Primary" className={cx("mt-2 flex flex-1 flex-col gap-0.5", collapsed ? "items-center px-0" : "px-3")}>
        <NavList items={PUBLIC_NAV} collapsed={collapsed} onNavigate={onNavigate} />

        {unlocked && (
          <>
            {!collapsed && (
              <p className="eyebrow mt-5 mb-1.5 px-3 text-faint" aria-hidden="true">
                {auth.status === "admin" ? `admin · ${auth.user ?? ""}` : "admin · local"}
              </p>
            )}
            {collapsed && <span aria-hidden="true" className="my-3 h-px w-6 bg-border" />}
            <NavList items={ADMIN_NAV} collapsed={collapsed} onNavigate={onNavigate} />
          </>
        )}

        <div className="mt-auto pt-4">
          {auth.status === "admin" ? (
            collapsed ? (
              <Tooltip content={`Sign out ${auth.user ?? ""}`} side="top">
                <button type="button" onClick={() => void auth.logout()} aria-label="Sign out" className="nav-item w-9 justify-center px-0">
                  <LogOut aria-hidden="true" />
                </button>
              </Tooltip>
            ) : (
              <button type="button" onClick={() => void auth.logout()} className="nav-item w-full text-faint">
                <LogOut aria-hidden="true" />
                <span>Sign out</span>
              </button>
            )
          ) : auth.status === "anon" || auth.status === "loading" ? (
            collapsed ? (
              <Tooltip content="Admin" side="top">
                <NavLink to="/admin" onClick={onNavigate} aria-label="Admin" className="nav-item w-9 justify-center px-0">
                  <Lock aria-hidden="true" />
                </NavLink>
              </Tooltip>
            ) : (
              <NavLink to="/admin" onClick={onNavigate} className="nav-item text-faint">
                <Lock aria-hidden="true" />
                <span>Admin</span>
              </NavLink>
            )
          ) : null}
        </div>
      </nav>

      <footer className={cx("hairline-t mt-3 flex flex-col gap-2 py-4", collapsed ? "items-center px-0" : "px-3")} aria-label="Status">
        {collapsed ? (
          <Tooltip content={`${chip.title} Agent ${health?.agent_model ?? "…"}, judge ${health?.judge_model ?? "…"}.`} side="top">
            <span className={cx("size-2.5 rounded-full", chip.tone === "green" ? "bg-green" : chip.tone === "amber" ? "bg-amber" : "bg-violet")} tabIndex={0} aria-label={`Mode: ${chip.label}`} />
          </Tooltip>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <Chip tone={chip.tone} dot size="sm" mono title={chip.title}>
                {chip.label}
              </Chip>
              {health && !healthLoading && (
                <span className="t-mono text-[11px] text-faint" title={`${health.cache_entries} cached LLM calls · ${health.index_size} indexed threads`}>
                  {health.index_size.toLocaleString()} threads
                </span>
              )}
            </div>
            <dl className="flex flex-col gap-1 text-[11px]">
              <div className="flex items-center justify-between gap-2">
                <dt className="text-faint">agent</dt>
                <dd className="t-mono truncate text-muted">{healthLoading ? <Skeleton width={96} height={11} /> : health?.agent_model ?? "unavailable"}</dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="text-faint">judge</dt>
                <dd className="t-mono truncate text-muted">{healthLoading ? <Skeleton width={84} height={11} /> : health?.judge_model ?? "unavailable"}</dd>
              </div>
            </dl>
          </>
        )}
      </footer>
    </div>
  );
}
