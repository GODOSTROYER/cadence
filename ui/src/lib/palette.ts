/**
 * Token values for places that cannot read CSS variables directly (recharts fills, inline SVG
 * attributes). Kept byte-identical to src/styles/tokens.css.
 */
export const TOKENS = {
  bg: "#0B0C0F",
  surface: "#12141A",
  surface2: "#191C24",
  border: "rgba(255,255,255,0.08)",
  borderStrong: "rgba(255,255,255,0.14)",
  text: "#ECEDEF",
  muted: "#8B8F98",
  faint: "#5B5F69",
  green: "#1ED760",
  amber: "#F5B841",
  rose: "#FF5C77",
  sky: "#6CB6FF",
  violet: "#A78BFA",
} as const;

export type TokenName = keyof typeof TOKENS;

/** Colour for a system: the agent is green, the judge sky, every baseline a violet shade. */
export function systemColor(system: string): string {
  if (system === "agent") return TOKENS.green;
  if (system.startsWith("trivial")) return "#7C6BC4";
  if (system.startsWith("simple") || system === "nn_reply") return TOKENS.violet;
  if (system.startsWith("llm")) return "#C7B8FF";
  return TOKENS.muted;
}

/** Sequential ramp for heatmap cells: transparent → green (correct diagonal) or → rose (errors). */
export function heatColor(value: number, max: number, kind: "diagonal" | "error"): string {
  if (max <= 0 || value <= 0) return "transparent";
  const t = Math.min(1, value / max);
  const alpha = 0.12 + 0.78 * Math.sqrt(t);
  return kind === "diagonal" ? `rgba(30,215,96,${alpha.toFixed(3)})` : `rgba(255,92,119,${alpha.toFixed(3)})`;
}
