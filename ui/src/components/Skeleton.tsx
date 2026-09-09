import type { CSSProperties } from "react";

import { cx } from "@/lib/cx";

export interface SkeletonProps {
  /** CSS width (default 100%). */
  width?: string | number;
  /** CSS height (default 1em). */
  height?: string | number;
  radius?: string | number;
  className?: string;
  /** Sized like the content it replaces, so data load causes no layout shift. */
  style?: CSSProperties;
}

/** Shimmering placeholder block. Compose several to mirror the shape of the loading content. */
export function Skeleton({ width = "100%", height = "1em", radius = 6, className, style }: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      className={cx("skeleton block", className)}
      style={{ width, height, borderRadius: radius, ...style }}
    />
  );
}

export interface SkeletonTextProps {
  lines?: number;
  /** Width of the last line as a CSS value, to avoid a rectangular block. */
  lastWidth?: string;
  lineHeight?: number;
  className?: string;
}

/** Paragraph-shaped skeleton. */
export function SkeletonText({ lines = 3, lastWidth = "62%", lineHeight = 14, className }: SkeletonTextProps) {
  return (
    <span className={cx("flex flex-col gap-2", className)} aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} height={lineHeight} width={i === lines - 1 ? lastWidth : "100%"} />
      ))}
    </span>
  );
}
