/**
 * Naming bridge between `eval_summary.json` system keys and the prediction / judge keys inside
 * `golden_merged.json` rows.
 *
 * The eval module writes the CONTRACT §15.1 ids (`agent`, `trivial`, `simple`, `simple_keyword`,
 * `llm_zero_shot`) plus computed escalation baselines; the illustrative §8 names
 * (`trivial_majority`, `simple_tfidf_lr`, `simple_rules`, `nn_reply`, `trivial_template`) also
 * appear in older exports and the mock data. Both spellings resolve here.
 */
import { systemLabel, systemLabelFor, systemShort, systemShortFor, type SystemTask } from "@/lib/labels";
import type { JudgedSystemId, SystemId } from "@/lib/types";

const PREDICTION_SYSTEM: Record<string, SystemId> = {
  agent: "agent",
  trivial: "trivial",
  trivial_majority: "trivial",
  trivial_template: "trivial",
  simple: "simple",
  simple_tfidf_lr: "simple",
  simple_rules: "simple",
  nn_reply: "simple",
  simple_keyword: "simple_keyword",
  llm_zero_shot: "llm_zero_shot",
};

const JUDGED_SYSTEM: Record<string, JudgedSystemId> = {
  agent: "agent",
  simple: "simple",
  simple_tfidf_lr: "simple",
  nn_reply: "simple",
  trivial: "trivial",
  trivial_majority: "trivial",
  trivial_template: "trivial",
};

/** Agent first, LLM baseline next, then the simple and trivial families; unknown keys last, alphabetically. */
const DISPLAY_ORDER: readonly string[] = [
  "agent",
  "llm_zero_shot",
  "simple",
  "simple_tfidf_lr",
  "simple_rules",
  "nn_reply",
  "simple_keyword",
  "trivial",
  "trivial_majority",
  "trivial_template",
  "trivial_always_escalate",
  "trivial_never_escalate",
];

/** The prediction system whose golden rows back a summary key; undefined for computed baselines. */
export function predictionSystem(key: string): SystemId | undefined {
  return PREDICTION_SYSTEM[key];
}

/** The judged system (CONTRACT §15.1: agent, simple, trivial) behind a reply-quality key. */
export function judgedSystem(key: string): JudgedSystemId | undefined {
  return JUDGED_SYSTEM[key];
}

/** Stable display order for any set of summary system keys. */
export function orderSystems(keys: readonly string[]): string[] {
  const rank = (k: string): number => {
    const i = DISPLAY_ORDER.indexOf(k);
    return i === -1 ? DISPLAY_ORDER.length : i;
  };
  return [...keys].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

export interface SystemOption {
  value: string;
  label: string;
  hint: string;
}

/** Options for a SegmentedControl over summary system keys, labelled for the task they are scored on. */
export function systemOptions(keys: readonly string[], task?: SystemTask): SystemOption[] {
  return orderSystems(keys).map((k) => ({
    value: k,
    label: task ? systemShortFor(task, k) : systemShort(k),
    hint: task ? systemLabelFor(task, k) : systemLabel(k),
  }));
}

/** The requested key when present, else the first ordered key (agent when available). */
export function resolveSystem(keys: readonly string[], requested: string | null | undefined): string | null {
  const ordered = orderSystems(keys);
  if (requested && ordered.includes(requested)) return requested;
  return ordered[0] ?? null;
}
