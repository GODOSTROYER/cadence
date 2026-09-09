import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cx } from "@/lib/cx";

export type ChipTone = "neutral" | "green" | "amber" | "rose" | "sky" | "violet";

export interface ChipProps {
  children: ReactNode;
  tone?: ChipTone;
  /** Mono type for ids, models and flags. */
  mono?: boolean;
  /** A leading dot in the tone colour. */
  dot?: boolean;
  icon?: ReactNode;
  /** Renders a button when set. */
  onClick?: () => void;
  selected?: boolean;
  disabled?: boolean;
  title?: string;
  className?: string;
  size?: "sm" | "md";
  "aria-pressed"?: ButtonHTMLAttributes<HTMLButtonElement>["aria-pressed"];
}

const TONE_TEXT: Record<ChipTone, string> = {
  neutral: "text-muted",
  green: "text-green",
  amber: "text-amber",
  rose: "text-rose",
  sky: "text-sky",
  violet: "text-violet",
};

const TONE_BG: Record<ChipTone, string> = {
  neutral: "bg-transparent",
  green: "bg-green-tint",
  amber: "bg-amber-tint",
  rose: "bg-rose-tint",
  sky: "bg-sky-tint",
  violet: "bg-violet-tint",
};

const TONE_DOT: Record<ChipTone, string> = {
  neutral: "bg-muted",
  green: "bg-green",
  amber: "bg-amber",
  rose: "bg-rose",
  sky: "bg-sky",
  violet: "bg-violet",
};

/** Small labelled pill: status, model, flag, or a clickable example. */
export function Chip({
  children,
  tone = "neutral",
  mono = false,
  dot = false,
  icon,
  onClick,
  selected = false,
  disabled = false,
  title,
  className,
  size = "md",
  ...aria
}: ChipProps) {
  const classes = cx(
    "inline-flex max-w-full items-center gap-1.5 rounded-full border whitespace-nowrap transition-colors duration-[120ms]",
    size === "sm" ? "h-[22px] px-2 text-[12px]" : "h-7 px-2.5 text-[13px]",
    mono && "font-mono",
    TONE_TEXT[tone],
    TONE_BG[tone],
    selected ? "border-border-strong bg-surface-2 text-text" : "border-border",
    onClick && !disabled && "cursor-pointer hover:border-border-strong hover:bg-surface-2 hover:text-text",
    disabled && "cursor-not-allowed opacity-50",
    className,
  );
  const inner = (
    <>
      {dot && <span aria-hidden="true" className={cx("size-1.5 shrink-0 rounded-full", TONE_DOT[tone])} />}
      {icon && <span aria-hidden="true" className="flex shrink-0 items-center [&>svg]:size-3.5">{icon}</span>}
      <span className="truncate">{children}</span>
    </>
  );
  if (onClick) {
    return (
      <button type="button" className={classes} onClick={onClick} disabled={disabled} title={title} {...aria}>
        {inner}
      </button>
    );
  }
  return (
    <span className={classes} title={title}>
      {inner}
    </span>
  );
}
