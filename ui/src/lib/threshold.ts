/**
 * The evaluated escalation policy (CONTRACT §5), mirrored from `cadence.eval.metrics.decision_at_threshold`.
 *
 * Recorded agent runs carry the decision the pipeline made at its run-time threshold; the evaluation
 * re-derives every decision at the threshold chosen on the dev split (`eval_summary.meta.threshold`):
 * escalate if a rule forced it, or the model said so, or the intent confidence is below the threshold.
 * Every page that shows a decision next to an evaluated number applies the same guard so the golden
 * explorer, the playground and the failure modes agree with the metrics.
 */
import type { AgentResponse, Decision, ReasonCode } from "./types";

export const LOW_CONFIDENCE: ReasonCode = "low_confidence";

export type GuardTrigger = "rules" | "model" | "threshold";

export interface Guard {
  /** The threshold the decision was re-derived at. */
  threshold: number;
  /** What the recorded run decided before re-derivation. */
  recorded: Decision;
  /** True when the guard changed the recorded decision. */
  changed: boolean;
  /** Why the re-derived decision escalates; null when it auto-handles. */
  trigger: GuardTrigger | null;
}

export type GuardedResponse = AgentResponse & { guard: Guard | null };

function hasLlmTrace(pred: AgentResponse): boolean {
  const trace = pred.trace;
  return trace !== null && trace !== undefined && ("llm_decision" in trace || "forced_by_rules" in trace || "enforced_default" in trace);
}

function triggerAt(pred: AgentResponse, threshold: number): GuardTrigger | null {
  const trace = pred.trace;
  if (!trace) return null;
  if (trace.forced_by_rules || trace.enforced_default) return "rules";
  if (trace.llm_decision === "escalate") return "model";
  if (typeof pred.intent_confidence === "number" && pred.intent_confidence < threshold) return "threshold";
  return null;
}

/** The decision the evaluated policy makes for a recorded run at `threshold`. */
export function decisionAtThreshold(pred: AgentResponse, threshold: number): Decision {
  if (!hasLlmTrace(pred)) return pred.decision;
  return triggerAt(pred, threshold) ? "escalate" : "auto_handle";
}

/**
 * A copy of the run with `decision` / `escalation` re-derived at `threshold`, plus a `guard` record.
 * Baseline rows (no LLM trace) and runs with no known threshold come back unchanged with `guard: null`.
 */
export function applyThreshold(pred: AgentResponse, threshold: number | undefined | null): GuardedResponse {
  if (typeof threshold !== "number" || !Number.isFinite(threshold) || !hasLlmTrace(pred)) return { ...pred, guard: null };
  const trigger = triggerAt(pred, threshold);
  const decision: Decision = trigger ? "escalate" : "auto_handle";
  const guard: Guard = { threshold, recorded: pred.decision, changed: decision !== pred.decision, trigger };
  if (decision === "auto_handle") return { ...pred, decision, escalation: null, guard };
  if (!guard.changed && pred.escalation) return { ...pred, guard };
  const recordedCode = pred.escalation?.reason_code ?? null;
  const code: ReasonCode =
    trigger === "rules"
      ? recordedCode ?? LOW_CONFIDENCE
      : trigger === "model"
        ? pred.trace?.llm_reason_code ?? recordedCode ?? LOW_CONFIDENCE
        : LOW_CONFIDENCE;
  const reason =
    trigger === "threshold"
      ? `Intent confidence ${pred.intent_confidence?.toFixed(2) ?? "—"} is below the ${threshold.toFixed(2)} guard chosen on the dev split, so the evaluated policy escalates for a human to confirm the intent.`
      : pred.escalation?.reason_code === code && pred.escalation.reason
        ? pred.escalation.reason
        : `Escalated with reason code '${code}' at confidence threshold ${threshold.toFixed(2)}.`;
  return { ...pred, decision, escalation: { reason_code: code, reason }, guard };
}

/** One line for the guard chip's tooltip. */
export function describeGuard(guard: Guard): string {
  const recorded = guard.recorded === "escalate" ? "escalate" : "auto-handle";
  if (!guard.changed) return `Re-derived at the evaluated threshold ${guard.threshold.toFixed(2)}; same as the recorded run (${recorded}).`;
  return guard.trigger === "threshold"
    ? `The recorded run said ${recorded}; at the evaluated threshold ${guard.threshold.toFixed(2)} its confidence is too low, so the policy escalates (low_confidence). Metrics use this decision.`
    : `The recorded run said ${recorded}; the evaluated policy at threshold ${guard.threshold.toFixed(2)} decides otherwise. Metrics use this decision.`;
}
