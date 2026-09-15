import type { AgentResponse, MergedGoldenExample } from "./types";

/**
 * Three recorded runs from the golden set (results/ui/golden_merged.json, agent predictions), embedded so the
 * landing page can show a real output even where no agent endpoint exists. A rule-forced billing escalation,
 * a self-served playback bug, and a rule-forced security escalation.
 */
export const RECORDED: readonly AgentResponse[] = [
  {
    id: "g_038",
    system: "agent",
    input_text: "Hey My premium payment failed but my card is good! I've tried to re-enter my info but keep getting the same error message!",
    intent: "billing_or_charge",
    intent_confidence: 0.95,
    secondary_intent: null,
    sentiment: "frustrated",
    reply_draft: "Hey there! Sorry to hear that. Can you DM us your account's email address or username, and a screenshot of the error message? We'll take a look backstage. /AI",
    citations: ["t_1815772"],
    grounding_notes: "The reply follows the exact brand pattern for payment update errors by asking for a DM with account email/username and an error screenshot.",
    decision: "escalate",
    escalation: { reason_code: "billing_dispute", reason: "Customer mentions a charge, payment or refund; billing actions need a human with account access." },
    rule_flags: ["money_keywords"],
    evidence: [],
    model: "gemini-3.5-flash-lite",
    latency_ms: 1,
    cached: true,
    trace: { retrieval_ms: 0, llm_ms: 0, prompt_tokens: 2381, output_tokens: 213, llm_decision: "escalate", llm_reason_code: "billing_dispute", forced_by_rules: true, enforced_default: false },
  },
  {
    id: "g_034",
    system: "agent",
    input_text: "ios11 doesn’t let me control Spotify from the lock screen anymore. Same in command centre.",
    intent: "playback_or_app_bug",
    intent_confidence: 0.95,
    secondary_intent: null,
    sentiment: "neutral",
    reply_draft: "Hey there! Can you try logging out > restarting your device > logging back in to see if it helps? Let us know how it goes 💚 /AI",
    citations: ["t_771451"],
    grounding_notes: "Steps come from evidence thread 1, which addresses iOS control centre and lock screen issues with log out, restart, and log back in.",
    decision: "auto_handle",
    escalation: null,
    rule_flags: [],
    evidence: [],
    model: "gemini-3.5-flash-lite",
    latency_ms: 1,
    cached: true,
    trace: { retrieval_ms: 0, llm_ms: 0, prompt_tokens: 2314, output_tokens: 186, llm_decision: "auto_handle", llm_reason_code: null, forced_by_rules: false, enforced_default: false },
  },
  {
    id: "g_017",
    system: "agent",
    input_text: "I have account spotify premium has been hacked with someone that change my mail. Can you provide it back to me?",
    intent: "account_hacked_or_security",
    intent_confidence: 1.0,
    secondary_intent: null,
    sentiment: "frustrated",
    reply_draft: "Hey! Sorry to hear that, help's here! DM us your account's email or username? We'll take a look backstage. /AI",
    citations: ["t_102218", "t_106328"],
    grounding_notes: "The steps and DM request follow the brand's standard pattern for hacked accounts in evidence threads t_102218 and t_106328.",
    decision: "escalate",
    escalation: { reason_code: "account_security", reason: "Possible unauthorized account access; security cases must be handled by a human." },
    rule_flags: ["security_keywords"],
    evidence: [],
    model: "gemini-3.5-flash-lite",
    latency_ms: 1,
    cached: true,
    trace: { retrieval_ms: 0, llm_ms: 0, prompt_tokens: 2322, output_tokens: 234, llm_decision: "escalate", llm_reason_code: "account_security", forced_by_rules: true, enforced_default: false },
  },
];


const CREATED_AT: Record<string, string> = { g_038: "2017-10-31T03:15:52Z", g_034: "2017-10-05T23:18:47Z", g_017: "2017-11-06T14:53:05Z" };

/**
 * The recorded runs shaped like golden rows, for the playground's example chips when the golden set is not
 * readable (anonymous visitor on the static build). Gold labels equal the agent's output here, which is true
 * for these three examples; the full rows with annotations live behind the admin endpoint.
 */
export function recordedAsGolden(): MergedGoldenExample[] {
  return RECORDED.map((r) => ({
    id: r.id ?? "recorded",
    thread_id: r.citations[0] ?? "",
    split: "test",
    text: r.input_text,
    text_raw: r.input_text,
    created_at: CREATED_AT[r.id ?? ""] ?? "2017-10-01T00:00:00Z",
    historical_brand_reply: "",
    historical_thread: [],
    gold: { intent: r.intent, secondary_intent: null, should_escalate: r.decision === "escalate", escalation_reason_code: r.escalation?.reason_code ?? null, sentiment: r.sentiment, media_only: false, notes: "" },
    annotations: {
      a: { intent: r.intent, should_escalate: r.decision === "escalate", escalation_reason_code: r.escalation?.reason_code ?? null, sentiment: r.sentiment, media_only: false, notes: "" },
      b: { intent: r.intent, should_escalate: r.decision === "escalate", escalation_reason_code: r.escalation?.reason_code ?? null, sentiment: r.sentiment, media_only: false, notes: "" },
    },
    agreement: { intent: true, should_escalate: true },
    adjudicated: false,
    sampling_bucket: "recorded",
    predictions: { agent: r },
    judge: {},
  }));
}
