/**
 * Golden explorer query state: parsed from and written back to the URL search params so every
 * filtered view (and an open drawer) is a shareable link. Pure functions only; the page owns the
 * `useSearchParams` plumbing.
 */
import type { AgentResponse, Decision, IntentId, MergedGoldenExample, Split, SystemId } from "@/lib/types";

/** Systems that may appear in `predictions`, in display order (CONTRACT §15.1). */
export const SYSTEM_ORDER: readonly SystemId[] = ["agent", "llm_zero_shot", "simple", "simple_keyword", "trivial"];

export const CORRECTNESS = ["all", "correct", "incorrect"] as const;
export type Correctness = (typeof CORRECTNESS)[number];

export const DECISION_FILTERS = ["all", "escalate", "auto_handle", "mismatch"] as const;
export type DecisionFilter = (typeof DECISION_FILTERS)[number];

export const SPLIT_FILTERS = ["all", "dev", "test"] as const;
export type SplitFilter = (typeof SPLIT_FILTERS)[number];

export interface GoldenQuery {
  /** Free-text search over id, thread id, message, notes and sampling bucket. */
  q: string;
  /** Gold intent, or "" for any. */
  intent: IntentId | "";
  /** Predicted intent of the compared system, or "" for any (set by confusion-matrix links). */
  pred: IntentId | "";
  split: SplitFilter;
  /** Predicted intent versus gold. */
  correct: Correctness;
  /** Gold decision, or a gold-versus-predicted mismatch. */
  decision: DecisionFilter;
  /** Which system's predictions the table compares against gold. */
  system: SystemId;
  /** Open drawer row. */
  id: string | null;
}

export const DEFAULT_QUERY: GoldenQuery = {
  q: "",
  intent: "",
  pred: "",
  split: "all",
  correct: "all",
  decision: "all",
  system: "agent",
  id: null,
};

function oneOf<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return (allowed as readonly string[]).includes(value ?? "") ? (value as T) : fallback;
}

/** Read the query from URL params; `systems` are the systems present in the data (first is the fallback). */
export function parseQuery(params: URLSearchParams, systems: readonly SystemId[]): GoldenQuery {
  return {
    q: params.get("q") ?? "",
    intent: params.get("intent") ?? "",
    pred: params.get("pred") ?? "",
    split: oneOf(params.get("split"), SPLIT_FILTERS, "all"),
    correct: oneOf(params.get("correct"), CORRECTNESS, "all"),
    decision: oneOf(params.get("decision"), DECISION_FILTERS, "all"),
    system: oneOf(params.get("system"), systems, systems[0] ?? DEFAULT_QUERY.system),
    id: params.get("id"),
  };
}

/** Write the query into `params` in place, omitting keys at their default so URLs stay short. */
export function writeQuery(params: URLSearchParams, query: GoldenQuery): URLSearchParams {
  const set = (key: string, value: string | null, isDefault: boolean) => {
    if (value === null || value === "" || isDefault) params.delete(key);
    else params.set(key, value);
  };
  set("q", query.q.trim(), false);
  set("intent", query.intent, false);
  set("pred", query.pred, false);
  set("split", query.split, query.split === DEFAULT_QUERY.split);
  set("correct", query.correct, query.correct === DEFAULT_QUERY.correct);
  set("decision", query.decision, query.decision === DEFAULT_QUERY.decision);
  set("system", query.system, query.system === DEFAULT_QUERY.system);
  set("id", query.id, false);
  return params;
}

/** True when any filter other than the open row differs from the default. */
export function hasActiveFilters(query: GoldenQuery): boolean {
  return (
    query.q.trim() !== "" ||
    query.intent !== "" ||
    query.pred !== "" ||
    query.split !== DEFAULT_QUERY.split ||
    query.correct !== DEFAULT_QUERY.correct ||
    query.decision !== DEFAULT_QUERY.decision
  );
}

export type DecisionError = "missed" | "unnecessary" | null;

/** One system's prediction set against the gold labels of a row. */
export interface Comparison {
  pred: AgentResponse | undefined;
  goldDecision: Decision;
  /** null when the system produced no prediction for the row. */
  intentCorrect: boolean | null;
  /** "missed" = gold escalate, predicted auto-handle (the costly error); "unnecessary" = the reverse. */
  decisionError: DecisionError;
}

export function compareRow(row: MergedGoldenExample, system: SystemId): Comparison {
  const pred = row.predictions[system];
  const goldDecision: Decision = row.gold.should_escalate ? "escalate" : "auto_handle";
  if (!pred) return { pred, goldDecision, intentCorrect: null, decisionError: null };
  const decisionError: DecisionError = pred.decision === goldDecision ? null : goldDecision === "escalate" ? "missed" : "unnecessary";
  return { pred, goldDecision, intentCorrect: pred.intent === row.gold.intent, decisionError };
}

function haystack(row: MergedGoldenExample): string {
  return [row.id, row.thread_id, row.text, row.gold.notes, row.sampling_bucket].join(" \n ").toLowerCase();
}

/** Every whitespace-separated search term must occur somewhere in the row's searchable text. */
export function matchesSearch(row: MergedGoldenExample, q: string): boolean {
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const text = haystack(row);
  return terms.every((t) => text.includes(t));
}

export function matchesQuery(row: MergedGoldenExample, query: GoldenQuery, cmp: Comparison): boolean {
  if (query.split !== "all" && row.split !== (query.split as Split)) return false;
  if (query.intent && row.gold.intent !== query.intent) return false;
  if (query.pred && cmp.pred?.intent !== query.pred) return false;
  if (query.correct === "correct" && cmp.intentCorrect !== true) return false;
  if (query.correct === "incorrect" && cmp.intentCorrect !== false) return false;
  if (query.decision === "escalate" && cmp.goldDecision !== "escalate") return false;
  if (query.decision === "auto_handle" && cmp.goldDecision !== "auto_handle") return false;
  if (query.decision === "mismatch" && cmp.decisionError === null) return false;
  return matchesSearch(row, query.q);
}

export interface RowStats {
  shown: number;
  withPrediction: number;
  intentCorrect: number;
  decisionErrors: number;
}

export function summarize(entries: readonly { cmp: Comparison }[]): RowStats {
  let withPrediction = 0;
  let intentCorrect = 0;
  let decisionErrors = 0;
  for (const { cmp } of entries) {
    if (cmp.pred) withPrediction += 1;
    if (cmp.intentCorrect) intentCorrect += 1;
    if (cmp.decisionError) decisionErrors += 1;
  }
  return { shown: entries.length, withPrediction, intentCorrect, decisionErrors };
}
