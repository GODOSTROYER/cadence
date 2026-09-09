/**
 * TypeScript mirror of CONTRACT.md §6–§10: agent output, golden examples, ratings, eval summary,
 * failure modes and the API payloads. Field names and shapes match the JSON exactly.
 */

// ---------------------------------------------------------------------------- vocabularies

/** Prediction systems (CONTRACT §15.1). */
export type SystemId = "agent" | "trivial" | "simple" | "simple_keyword" | "llm_zero_shot";
/** Systems whose reply drafts are judged. */
export type JudgedSystemId = "agent" | "simple" | "trivial";

export type Decision = "auto_handle" | "escalate";
export type Sentiment = "positive" | "neutral" | "frustrated" | "angry";
export type Split = "dev" | "test";
export type Verdict = "ship" | "edit" | "reject";

/** Escalation reason codes (CONTRACT §5). */
export type ReasonCode =
  | "billing_dispute"
  | "account_security"
  | "needs_account_lookup"
  | "high_frustration_or_churn"
  | "legal_or_safety"
  | "ambiguous_or_media_only"
  | "low_confidence"
  | "out_of_scope";

/**
 * Intent ids are stable snake_case strings from config/intents.yaml. Kept as `string` because the
 * taxonomy pass may merge or split intents; `src/lib/intents.ts` holds the known list and colours.
 */
export type IntentId = string;

export type JudgeDimension = "grounded" | "resolves" | "tone" | "safe" | "overall";
export type JudgeFlag = "hallucinated_link_or_policy" | "asks_sensitive_info" | "wrong_issue";

/** Two-sided 95% confidence interval `[low, high]`. */
export type CI95 = [number, number];

// ---------------------------------------------------------------------------- §6 AgentResponse

export interface Escalation {
  reason_code: ReasonCode;
  reason: string;
}

export interface Evidence {
  thread_id: string;
  score: number;
  customer_text: string;
  brand_reply: string;
  resolved_links: string[];
  cited: boolean;
}

export interface AgentTrace {
  retrieval_ms: number;
  llm_ms: number;
  prompt_tokens: number;
  output_tokens: number;
  llm_decision: Decision | null;
  llm_reason_code: ReasonCode | null;
  forced_by_rules: boolean;
}

export interface AgentResponse {
  id: string | null;
  system: SystemId;
  input_text: string;
  intent: IntentId;
  intent_confidence: number | null;
  secondary_intent: IntentId | null;
  sentiment: Sentiment;
  reply_draft: string;
  citations: string[];
  grounding_notes: string;
  decision: Decision;
  escalation: Escalation | null;
  rule_flags: string[];
  evidence: Evidence[];
  model: string;
  latency_ms: number;
  cached: boolean;
  trace: AgentTrace | null;
}

// ---------------------------------------------------------------------------- §3 processed thread

export interface ThreadTurn {
  role: "customer" | "brand";
  tweet_id: number;
  created_at: string;
  text: string;
  agent_sig?: string | null;
}

export interface BrandReply {
  tweet_id: number;
  created_at: string;
  text_raw: string;
  text: string;
  agent_sig: string | null;
  links: string[];
  resolved_links: string[];
  asks_dm: boolean;
}

export interface ProcessedThread {
  thread_id: string;
  opener_tweet_id: number;
  created_at: string;
  customer_author_id: string;
  customer_text_raw: string;
  customer_text: string;
  has_link: boolean;
  n_words: number;
  language: "en" | "other";
  brand_replies: BrandReply[];
  turns: ThreadTurn[];
  n_brand_replies: number;
  n_turns: number;
  first_reply_text: string;
  first_reply_asks_dm: boolean;
}

// ---------------------------------------------------------------------------- §7 golden + ratings

export interface GoldLabels {
  intent: IntentId;
  secondary_intent: IntentId | null;
  should_escalate: boolean;
  escalation_reason_code: ReasonCode | null;
  sentiment: Sentiment;
  media_only: boolean;
  notes: string;
}

export interface Annotation {
  intent: IntentId;
  should_escalate: boolean;
  escalation_reason_code: ReasonCode | null;
  sentiment: Sentiment;
  media_only: boolean;
  notes: string;
}

export interface GoldenExample {
  id: string;
  thread_id: string;
  split: Split;
  text: string;
  text_raw: string;
  created_at: string;
  historical_brand_reply: string;
  historical_thread: ThreadTurn[];
  gold: GoldLabels;
  annotations: { a: Annotation; b: Annotation };
  agreement: { intent: boolean; should_escalate: boolean };
  adjudicated: boolean;
  sampling_bucket: string;
}

export type JudgeScores = Record<JudgeDimension, number>;
export type JudgeFlags = Record<JudgeFlag, boolean>;

/** Shared by human ratings and judge scores (CONTRACT §7). */
export interface RatingRecord {
  id: string;
  system: SystemId;
  /** `"human"` or the judge model name. */
  rater: string;
  scores: JudgeScores;
  flags: JudgeFlags;
  verdict: Verdict;
  rationale: string;
  rated_at: string;
}

export type JudgeScore = RatingRecord;

/** `GET /api/golden` row: a golden example merged with every system's prediction and judge score. */
export interface MergedGoldenExample extends GoldenExample {
  predictions: Partial<Record<SystemId, AgentResponse>>;
  judge: Partial<Record<JudgedSystemId, JudgeScore>>;
}

// ---------------------------------------------------------------------------- §8 eval summary

export interface DatasetFacts {
  n_openers: number;
  n_brand_tweets: number;
  n_rows_total: number;
  n_brands: number;
  date_from: string;
  date_to: string;
  share_english: number;
  share_with_link: number;
  share_single_reply: number;
  n_resolved_links: number;
}

export interface EvalMeta {
  brand: string;
  n_golden: number;
  n_dev: number;
  n_test: number;
  generated_at: string;
  agent_model: string;
  judge_model: string;
  zero_shot_model?: string;
  git_sha: string;
  cache_hit_rate: number;
  threshold: number;
  /** Honest bullets for the "What is misleading about these numbers" callout. */
  caveats?: string[];
  /** Corpus facts for the Method page; falls back to CONTRACT §2 constants when absent. */
  dataset?: DatasetFacts;
}

export interface Headline {
  intent_macro_f1: number;
  escalation_recall: number;
  auto_handle_rate: number;
  judge_overall_mean: number;
  judge_overall_mean_nn: number;
  ci95: {
    intent_macro_f1: CI95;
    escalation_recall: CI95;
    auto_handle_rate: CI95;
    judge_overall_mean: CI95;
  };
}

export interface PerClassMetrics {
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface ConfusionData {
  labels: IntentId[];
  matrix: number[][];
}

export interface IntentSystemMetrics {
  accuracy: number;
  macro_f1: number;
  weighted_f1: number;
  per_class: Record<IntentId, PerClassMetrics>;
  confusion: ConfusionData;
  ci95: { accuracy: CI95; macro_f1: CI95 };
}

/** Intent system keys as named in eval_summary (CONTRACT §8), which differ from `SystemId`. */
export type IntentSystemKey = "agent" | "trivial_majority" | "simple_keyword" | "simple_tfidf_lr" | "llm_zero_shot";

export interface IntentBlock {
  labels: IntentId[];
  support: Record<IntentId, number>;
  systems: Record<string, IntentSystemMetrics>;
}

export interface EscalationSystemMetrics {
  precision: number;
  recall: number;
  f1: number;
  auto_handle_rate: number;
  accuracy: number;
  missed_escalations: number;
  unnecessary_escalations: number;
  reason_code_accuracy: number;
  confusion: { tp: number; fp: number; fn: number; tn: number };
  ci95: Partial<Record<"recall" | "precision" | "auto_handle_rate" | "f1", CI95>>;
  missed_examples: string[];
}

export type EscalationSystemKey = "agent" | "trivial_always_escalate" | "trivial_never_escalate" | "simple_rules";

export interface ThresholdPoint {
  threshold: number;
  recall: number;
  precision: number;
  auto_handle_rate: number;
}

export interface EscalationBlock {
  systems: Record<string, EscalationSystemMetrics>;
  threshold_sweep: ThresholdPoint[];
}

export interface ReplyQualitySystem {
  mean: JudgeScores;
  /** Counts of overall = 1..5. */
  dist_overall: [number, number, number, number, number];
  ship_rate: number;
  flag_rates: Record<JudgeFlag, number>;
  ci95: { overall: CI95 };
}

export type ReplySystemKey = "agent" | "trivial_template" | "nn_reply";

export interface ReplyQualityBlock {
  systems: Record<string, ReplyQualitySystem>;
  pairwise: { agent_vs_nn_win_rate: number; agent_vs_trivial_win_rate: number };
}

export interface AgreementPair {
  id: string;
  system: SystemId;
  human: number;
  judge: number;
}

export interface JudgeAgreementBlock {
  n: number;
  weighted_kappa_overall: number;
  spearman_overall: number;
  exact_agreement: number;
  within_one: number;
  judge_minus_human_mean?: number;
  per_dimension: Record<string, { weighted_kappa: number; spearman: number }>;
  pairs: AgreementPair[];
}

export interface AnnotatorAgreement {
  intent_kappa: number;
  intent_raw: number;
  escalation_kappa: number;
  escalation_raw: number;
  n_disagreements: number;
}

export interface CostBlock {
  n_llm_calls: number;
  total_prompt_tokens: number;
  total_output_tokens: number;
  wall_minutes: number;
}

export interface EvalSummary {
  meta: EvalMeta;
  headline: Headline;
  intent: IntentBlock;
  escalation: EscalationBlock;
  reply_quality: ReplyQualityBlock;
  judge_agreement: JudgeAgreementBlock;
  annotator_agreement: AnnotatorAgreement;
  cost: CostBlock;
}

// ---------------------------------------------------------------------------- §9 failure modes

export interface FailureExample {
  golden_id: string;
  text: string;
  gold_intent: IntentId;
  pred_intent: IntentId;
  gold_decision: Decision;
  pred_decision: Decision;
  reply_draft: string;
  why: string;
}

export interface FailureMode {
  id: string;
  title: string;
  count: number;
  share: number;
  hypothesis: string;
  examples: FailureExample[];
  proposed_fix: string;
}

// ---------------------------------------------------------------------------- §10 API payloads

export interface Health {
  status: string;
  has_api_key: boolean;
  cache_only: boolean;
  agent_model: string;
  judge_model: string;
  cache_entries: number;
  index_size: number;
  n_golden: number;
}

export type HandleMode = "live" | "cache_only";

export interface HandleRequest {
  text: string;
  mode?: HandleMode;
}

export type RatingAlias = "A" | "B" | "C";

export interface RatingQueueItem {
  id: string;
  system_alias: RatingAlias;
  text: string;
  reply_draft: string;
  evidence: Evidence[];
}

/** Body of `POST /api/ratings`; the server forces `rater` to `"human"`. */
export interface RatingSubmission {
  id: string;
  /** The alias shown to the rater; the server resolves it to a system. */
  system: RatingAlias | SystemId;
  rater: "human";
  scores: JudgeScores;
  flags: JudgeFlags;
  verdict: Verdict;
  rationale: string;
  rated_at: string;
}

export interface DecisionEntry {
  n: number;
  title: string;
  decision: string;
  why: string;
}

// ---------------------------------------------------------------------------- config exports (static)

/** One row of public/data/intents.json, derived from config/intents.yaml. */
export interface IntentDefinition {
  id: IntentId;
  name: string;
  description: string;
  examples: string[];
  default_decision: Decision;
  default_reason_code: ReasonCode | null;
  keywords: string[];
}

export interface ReasonCodeDefinition {
  id: ReasonCode;
  name: string;
  description: string;
}

export interface RuleDefinition {
  flag: string;
  force_escalate: boolean;
  reason_code: ReasonCode;
  reason: string;
  n_patterns: number;
}

/** public/data/escalation.json, derived from config/escalation.yaml. */
export interface EscalationPolicy {
  confidence_threshold: number;
  min_words_for_auto_handle: number;
  reason_codes: ReasonCodeDefinition[];
  rules: RuleDefinition[];
  soft_flags: { flag: string; n_patterns: number }[];
}

/** UI mode derived from build env + health. */
export type UiMode = "static" | "live" | "cache-only";
