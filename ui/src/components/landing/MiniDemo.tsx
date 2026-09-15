import { ArrowRight, Play } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { Chip } from "@/components/Chip";
import { ConfidenceBar } from "@/components/ConfidenceBar";
import { DecisionPill } from "@/components/DecisionPill";
import { IntentBadge } from "@/components/IntentBadge";
import { ReplyPreview, TWEET_LIMIT } from "@/components/ReplyPreview";
import { Skeleton } from "@/components/Skeleton";
import { StepTimeline, type StepStatus, type TimelineStep } from "@/components/StepTimeline";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { AGENT_AVAILABLE, describeError, handle } from "@/lib/api";
import { cx } from "@/lib/cx";
import { compact, int, ms as formatMs, truncate } from "@/lib/format";
import { intentColor } from "@/lib/intents";
import { ruleFlagLabel, SENTIMENT_LABELS } from "@/lib/labels";
import { RECORDED } from "@/lib/recorded";
import type { AgentResponse } from "@/lib/types";

type Phase = "idle" | "running" | "done" | "error";
const STEP_IDS = ["rules", "retrieve", "llm", "decide"] as const;
type StepId = (typeof STEP_IDS)[number];
const PENDING: Record<StepId, StepStatus> = { rules: "pending", retrieve: "pending", llm: "pending", decide: "pending" };

function sleep(msec: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, msec));
}

function normalise(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

function buildSteps(statuses: Record<StepId, StepStatus>, r: AgentResponse | null): TimelineStep[] {
  const flags = r?.rule_flags ?? [];
  const forced = r?.trace?.forced_by_rules ?? false;
  return [
    { id: "rules", label: "Rules", status: statuses.rules, ms: statuses.rules === "done" ? 1 : null, detail: statuses.rules === "done" ? (flags.length ? `${flags.length} flag${flags.length === 1 ? "" : "s"}${forced ? ", forced" : ""}` : "no flags") : undefined },
    { id: "retrieve", label: "Retrieve", status: statuses.retrieve, ms: statuses.retrieve === "done" ? r?.trace?.retrieval_ms ?? null : null, detail: statuses.retrieve === "done" ? "BM25 top-6" : undefined },
    { id: "llm", label: "Gemini", status: statuses.llm, ms: statuses.llm === "done" ? r?.trace?.llm_ms ?? null : null, detail: statuses.llm === "done" && r?.trace ? `${compact(r.trace.prompt_tokens)} → ${int(r.trace.output_tokens)} tok` : undefined },
    { id: "decide", label: "Decide", status: statuses.decide, ms: statuses.decide === "done" ? 0 : null, detail: statuses.decide === "done" && r ? (r.decision === "escalate" ? "escalate" : "auto-handle") : undefined },
  ];
}

export interface MiniDemoProps {
  /** Confidence threshold from the evaluation, drawn on the confidence bar. */
  threshold?: number;
  className?: string;
}

/** A compact composer that runs the agent (live) or replays a recorded run, and shows intent, decision and reply. */
export function MiniDemo({ threshold, className }: MiniDemoProps) {
  const reduced = useReducedMotion();
  const [text, setText] = useState(RECORDED[0]?.input_text ?? "");
  const [phase, setPhase] = useState<Phase>("idle");
  const [statuses, setStatuses] = useState<Record<StepId, StepStatus>>(PENDING);
  const [result, setResult] = useState<AgentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState(false);
  const runId = useRef(0);
  const textarea = useRef<HTMLTextAreaElement | null>(null);

  const over = text.length > TWEET_LIMIT;
  const recordedMatch = RECORDED.find((r) => normalise(r.input_text) === normalise(text)) ?? null;
  const canRun = phase !== "running" && text.trim().length > 0 && !over && (AGENT_AVAILABLE || recordedMatch !== null);

  const reset = useCallback(() => {
    runId.current += 1;
    setPhase("idle");
    setStatuses(PENDING);
    setResult(null);
    setError(null);
    setTyped(false);
  }, []);

  const run = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!canRun) return;
    const id = ++runId.current;
    const alive = () => runId.current === id;
    const wait = (msec: number) => (reduced ? Promise.resolve() : sleep(msec));
    setPhase("running");
    setResult(null);
    setError(null);
    setTyped(false);
    setStatuses({ ...PENDING, rules: "active" });

    let response: AgentResponse;
    try {
      if (AGENT_AVAILABLE) {
        const request = handle(text);
        await wait(240);
        if (alive()) setStatuses({ rules: "done", retrieve: "active", llm: "pending", decide: "pending" });
        await wait(360);
        if (alive()) setStatuses({ rules: "done", retrieve: "done", llm: "active", decide: "pending" });
        response = await request;
      } else {
        if (!recordedMatch) throw new Error("Only the three recorded messages replay here.");
        await wait(240);
        if (alive()) setStatuses({ rules: "done", retrieve: "active", llm: "pending", decide: "pending" });
        await wait(360);
        if (alive()) setStatuses({ rules: "done", retrieve: "done", llm: "active", decide: "pending" });
        await wait(700);
        response = recordedMatch;
      }
    } catch (err) {
      if (!alive()) return;
      setStatuses((s) => ({ ...s, llm: s.llm === "active" ? "error" : s.llm, retrieve: s.retrieve === "active" ? "error" : s.retrieve, rules: s.rules === "active" ? "error" : s.rules }));
      setError(describeError(err));
      setPhase("error");
      return;
    }
    if (!alive()) return;
    setStatuses({ rules: "done", retrieve: "done", llm: "done", decide: "active" });
    await wait(220);
    if (!alive()) return;
    setStatuses({ rules: "done", retrieve: "done", llm: "done", decide: "done" });
    setResult(response);
    setPhase("done");
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && document.activeElement === textarea.current) void run();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run reads current state at call time
  }, [canRun, text]);

  const steps = buildSteps(statuses, result);

  return (
    <div className={cx("region grid gap-0 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]", className)}>
      <form onSubmit={run} className="flex flex-col gap-4 px-5 py-5 sm:px-6 lg:border-r lg:border-border" aria-label="Try the agent">
        <div className="flex flex-col gap-2">
          <p className="eyebrow">{AGENT_AVAILABLE ? "a real customer tweet, or your own" : "three recorded runs"}</p>
          <div className="flex flex-wrap gap-2" role="list" aria-label="Example messages">
            {RECORDED.map((r) => (
              <Chip
                key={r.id}
                onClick={() => {
                  reset();
                  setText(r.input_text);
                  if (AGENT_AVAILABLE) textarea.current?.focus();
                }}
                selected={recordedMatch?.id === r.id}
                aria-pressed={recordedMatch?.id === r.id}
                title={r.input_text}
                className="max-w-full"
                icon={<span className="size-2 rounded-full" style={{ background: intentColor(r.intent) }} />}
              >
                {truncate(r.input_text, 38)}
              </Chip>
            ))}
          </div>
        </div>
        <div className="relative">
          <textarea
            ref={textarea}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              if (phase !== "idle") reset();
            }}
            rows={3}
            readOnly={!AGENT_AVAILABLE}
            aria-label="Customer tweet"
            placeholder="@SpotifyCares my app keeps crashing since the update…"
            className={cx("w-full resize-y rounded-md border bg-bg px-4 pt-3 pb-8 text-[15px] leading-relaxed text-text placeholder:text-faint", over ? "border-rose" : "border-border-strong", !AGENT_AVAILABLE && "cursor-default")}
          />
          <span className={cx("t-mono pointer-events-none absolute right-3 bottom-3 text-[12px]", over ? "text-rose" : "text-faint")}>
            {text.length} / {TWEET_LIMIT}
          </span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[12px] text-faint">{AGENT_AVAILABLE ? "Nothing is posted; the reply is a draft." : "This build replays recorded runs; the live build runs the model."}</p>
          <button type="submit" className="btn btn-primary" disabled={!canRun}>
            <Play className="size-4" aria-hidden="true" />
            {phase === "running" ? "Running…" : AGENT_AVAILABLE ? "Run the agent" : "Replay"}
          </button>
        </div>
      </form>

      <div className="flex min-w-0 flex-col gap-4 border-t border-border px-5 py-5 sm:px-6 lg:border-t-0" aria-live="polite" aria-label="Agent result">
        {phase === "idle" && (
          <div className="flex h-full min-h-[220px] flex-col items-center justify-center gap-2 text-center">
            <p className="t-display text-[22px] text-text">Intent, decision, reply.</p>
            <p className="measure text-[13px] text-muted">
              Run a message to see what the agent classifies it as, whether it hands it to a human and why, and the reply it drafts.
            </p>
          </div>
        )}
        {(phase === "running" || phase === "error") && (
          <>
            <StepTimeline steps={steps} />
            {phase === "running" && (
              <div className="flex flex-col gap-3" aria-hidden="true">
                <Skeleton height={14} width="45%" />
                <Skeleton height={6} />
                <Skeleton height={96} radius={8} />
              </div>
            )}
            {phase === "error" && (
              <p role="alert" className="rounded-md border border-rose/40 px-4 py-3 text-[13px] text-rose">
                {error}
              </p>
            )}
          </>
        )}
        {phase === "done" && result && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <IntentBadge id={result.intent} />
              <Chip size="sm" tone={result.sentiment === "angry" ? "rose" : result.sentiment === "frustrated" ? "amber" : result.sentiment === "positive" ? "green" : "neutral"} dot>
                {SENTIMENT_LABELS[result.sentiment]}
              </Chip>
            </div>
            <ConfidenceBar value={result.intent_confidence} threshold={threshold} />
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <DecisionPill decision={result.decision} reasonCode={result.escalation?.reason_code ?? null} showReason />
                {result.trace?.forced_by_rules && (
                  <Chip size="sm" tone="amber" mono title="A deterministic rule forced this decision; the model cannot override it">
                    forced by rules
                  </Chip>
                )}
                {result.rule_flags.map((f) => (
                  <span key={f} className="tag" title={ruleFlagLabel(f)}>
                    {f}
                  </span>
                ))}
              </div>
              <p className="text-[13px] leading-relaxed text-muted">
                {result.escalation?.reason ??
                  (typeof threshold === "number"
                    ? `Grounded self-serve reply; no rule fired and confidence cleared the ${threshold.toFixed(2)} guard, so it can post without review.`
                    : "Grounded self-serve reply; no rule fired, so it can post without review.")}
              </p>
            </div>
            <ReplyPreview text={result.reply_draft} animate={!typed} onTyped={() => setTyped(true)} compact />
            <div className="flex flex-wrap items-center gap-2">
              <Chip size="sm" mono>{result.model}</Chip>
              <Chip size="sm" mono tone={result.cached ? "violet" : "green"} title={result.cached ? "Served from the committed LLM cache" : "Fresh Gemini call"}>
                {result.cached ? "cached" : "live call"}
              </Chip>
              <Chip size="sm" mono>{formatMs(result.latency_ms)}</Chip>
              <Link to="/agent" className="link ml-auto inline-flex items-center gap-1 text-[12px] text-muted">
                Open the full playground
                <ArrowRight className="size-3" aria-hidden="true" />
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
