/**
 * Display labels for every backend vocabulary, so raw enum ids never reach the UI unlabelled.
 * Raw ids are still shown in mono where the id itself is the information (intent ids, thread ids).
 */
import { titleCase } from "./format";
import type { Decision, JudgeDimension, JudgeFlag, ReasonCode, Sentiment, Verdict } from "./types";

/** Systems under both naming schemes: CONTRACT §15.1 ids and the §8 eval_summary keys. */
const SYSTEM_LABELS: Record<string, { name: string; short: string; kind: "agent" | "baseline" }> = {
  agent: { name: "Cadence agent", short: "Agent", kind: "agent" },
  trivial: { name: "Trivial baseline", short: "Trivial", kind: "baseline" },
  simple: { name: "Simple baseline (TF-IDF + rules + nearest neighbour)", short: "Simple", kind: "baseline" },
  simple_keyword: { name: "Keyword rules", short: "Keywords", kind: "baseline" },
  llm_zero_shot: { name: "LLM zero-shot (no retrieval)", short: "Zero-shot", kind: "baseline" },
  trivial_majority: { name: "Majority class", short: "Majority", kind: "baseline" },
  simple_tfidf_lr: { name: "TF-IDF + logistic regression", short: "TF-IDF LR", kind: "baseline" },
  trivial_always_escalate: { name: "Always escalate", short: "Always", kind: "baseline" },
  trivial_never_escalate: { name: "Never escalate", short: "Never", kind: "baseline" },
  simple_rules: { name: "Keyword rules only", short: "Rules", kind: "baseline" },
  trivial_template: { name: "Most common template", short: "Template", kind: "baseline" },
  nn_reply: { name: "Nearest-neighbour reply", short: "Nearest neighbour", kind: "baseline" },
};

export function systemLabel(id: string): string {
  return SYSTEM_LABELS[id]?.name ?? titleCase(id);
}

export function systemShort(id: string): string {
  return SYSTEM_LABELS[id]?.short ?? titleCase(id);
}

export function isBaseline(id: string): boolean {
  return (SYSTEM_LABELS[id]?.kind ?? "baseline") === "baseline";
}

export const REASON_CODE_LABELS: Record<ReasonCode, string> = {
  billing_dispute: "Billing dispute",
  account_security: "Account security",
  needs_account_lookup: "Needs account lookup",
  high_frustration_or_churn: "High frustration / churn risk",
  legal_or_safety: "Legal or safety",
  ambiguous_or_media_only: "Ambiguous or media-only",
  low_confidence: "Low model confidence",
  out_of_scope: "Out of scope",
};

export function reasonLabel(code: ReasonCode | string | null | undefined): string {
  if (!code) return "";
  return (REASON_CODE_LABELS as Record<string, string>)[code] ?? titleCase(code);
}

export const DECISION_LABELS: Record<Decision, string> = {
  auto_handle: "Auto-handle",
  escalate: "Escalate",
};

export const SENTIMENT_LABELS: Record<Sentiment, string> = {
  positive: "Positive",
  neutral: "Neutral",
  frustrated: "Frustrated",
  angry: "Angry",
};

export const VERDICT_LABELS: Record<Verdict, string> = {
  ship: "Ship",
  edit: "Edit",
  reject: "Reject",
};

export const JUDGE_DIMENSIONS: readonly JudgeDimension[] = ["grounded", "resolves", "tone", "safe", "overall"];

export const JUDGE_DIMENSION_LABELS: Record<JudgeDimension, string> = {
  grounded: "Grounded",
  resolves: "Resolves",
  tone: "Tone",
  safe: "Safe",
  overall: "Overall",
};

export const JUDGE_DIMENSION_HINTS: Record<JudgeDimension, string> = {
  grounded: "Every claim, step and link traces to evidence or general brand practice. 1 = invented policy.",
  resolves: "Addresses the actual issue with a concrete next step. 1 = irrelevant.",
  tone: "SpotifyCares voice: warm, brief, at most one emoji, no grovelling, under 280 characters.",
  safe: "No refund or compensation promises, no legal commitments; asks only for a DM, never for passwords or card numbers.",
  overall: "Holistic. Ship needs overall ≥ 4 and no flags.",
};

export const JUDGE_FLAGS: readonly JudgeFlag[] = ["hallucinated_link_or_policy", "asks_sensitive_info", "wrong_issue"];

export const JUDGE_FLAG_LABELS: Record<JudgeFlag, string> = {
  hallucinated_link_or_policy: "Hallucinated link or policy",
  asks_sensitive_info: "Asks for sensitive info",
  wrong_issue: "Wrong issue",
};

/** Rule flags from config/escalation.yaml (forced and soft). */
export const RULE_FLAG_LABELS: Record<string, string> = {
  money_keywords: "Money keywords",
  security_keywords: "Security keywords",
  legal_keywords: "Legal keywords",
  churn_or_abuse: "Churn threat or abuse",
  media_only_or_too_short: "Media-only or too short",
  password_or_card_shared: "Credentials shared publicly",
  profanity: "Profanity",
  repeated_contact: "Repeated contact",
  asks_for_human: "Asks for a human",
};

export function ruleFlagLabel(flag: string): string {
  return RULE_FLAG_LABELS[flag] ?? titleCase(flag);
}

export const SPLIT_LABELS: Record<"dev" | "test", string> = { dev: "Dev", test: "Test" };
