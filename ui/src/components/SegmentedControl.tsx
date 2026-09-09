import { useEffect, useRef, type KeyboardEvent } from "react";

import { cx } from "@/lib/cx";

export interface SegmentOption<T extends string | number> {
  value: T;
  label: string;
  /** Optional hint for a tooltip/title. */
  hint?: string;
  disabled?: boolean;
}

export interface SegmentedControlProps<T extends string | number> {
  options: readonly SegmentOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
  /** Accessible group name. */
  label: string;
  size?: "sm" | "md";
  /** When set, pressing the digit keys 1..n while the group is focused selects the nth option. */
  digitHotkeys?: boolean;
  /** Listen for digit hotkeys on the whole document (used by the rating flow). */
  globalHotkeys?: boolean;
  disabled?: boolean;
  className?: string;
}

/** Radio-group styled as a segmented switch; arrow keys move, digits select (optional). */
export function SegmentedControl<T extends string | number>({
  options,
  value,
  onChange,
  label,
  size = "md",
  digitHotkeys = false,
  globalHotkeys = false,
  disabled = false,
  className,
}: SegmentedControlProps<T>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const selectByDigit = (key: string): boolean => {
    const n = Number(key);
    if (!Number.isInteger(n) || n < 1 || n > options.length) return false;
    const opt = options[n - 1];
    if (!opt || opt.disabled) return false;
    onChange(opt.value);
    return true;
  };

  useEffect(() => {
    if (!globalHotkeys || disabled) return;
    const handler = (e: globalThis.KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT")) return;
      if (selectByDigit(e.key)) e.preventDefault();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- options/onChange captured per render is intended
  }, [globalHotkeys, disabled, options, onChange]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (digitHotkeys && selectByDigit(e.key)) {
      e.preventDefault();
      return;
    }
    const i = options.findIndex((o) => o.value === value);
    let next = i;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (i + 1) % options.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (i - 1 + options.length) % options.length;
    else return;
    e.preventDefault();
    const opt = options[next];
    if (!opt) return;
    onChange(opt.value);
    refs.current[next]?.focus();
  };

  return (
    <div
      role="radiogroup"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cx(
        "inline-flex max-w-full items-stretch overflow-x-auto rounded-md border border-border bg-surface p-0.5",
        disabled && "opacity-50",
        className,
      )}
    >
      {options.map((o, i) => {
        const active = o.value === value;
        return (
          <button
            key={String(o.value)}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="radio"
            type="button"
            aria-checked={active}
            tabIndex={active || (value === null && i === 0) ? 0 : -1}
            disabled={disabled || o.disabled}
            title={o.hint}
            onClick={() => onChange(o.value)}
            className={cx(
              "shrink-0 rounded-[5px] font-medium whitespace-nowrap transition-colors duration-[120ms] disabled:cursor-not-allowed",
              size === "sm" ? "h-6 px-2 text-[12px]" : "h-8 px-3 text-[13px]",
              active ? "bg-surface-2 text-text" : "text-muted hover:text-text",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
