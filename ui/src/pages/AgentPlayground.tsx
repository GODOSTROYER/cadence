import { Eraser, Play, Sparkles, TerminalSquare } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { Chip } from "@/components/Chip";
import { ConfidenceBar } from "@/components/ConfidenceBar";
import { DecisionPill } from "@/components/DecisionPill";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { EvidenceCard } from "@/components/EvidenceCard";
import { IntentBadge } from "@/components/IntentBadge";
import { PageHeader } from "@/components/PageHeader";
import { PageTransition } from "@/components/PageTransition";
import { ReplyPreview, TWEET_LIMIT } from "@/components/ReplyPreview";
import { Skeleton } from "@/components/Skeleton";
import { StepTimeline, type StepStatus, type TimelineStep } from "@/components/StepTimeline";
import { useAsync } from "@/hooks/useAsync";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { describeError, getGolden, getResults, handle, IS_STATIC, isStaticModeError } from "@/lib/api";
import { cx } from "@/lib/cx";
import { compact, int, ms as formatMs, truncate } from "@/lib/format";
import { intentColor } from "@/lib/intents";
import { reasonLabel, ruleFlagLabel, SENTIMENT_LABELS } from "@/lib/labels";
import type { AgentResponse, MergedGoldenExample } from "@/lib/types";

type Phase = "idle" | "running" | "done" | "error";

const STEP_IDS = ["rules", "retrieve", "llm", "decide"] as const;
type StepId = (typeof STEP_IDS)[number];

/** Six chips that span the taxonomy: preferred gold intents, first recorded example of each. */
const CHIP_INTENTS = ["billing_or_charge", "playback_or_app_bug", "account_hacked_or_security", "subscription_or_plan", "non_english", "other"];

function pickExamples(rows: MergedGoldenExample[]): MergedGoldenExample[] {
  const picked: MergedGoldenExample[] = [];
  for (const intent of CHIP_INTENTS) {
    const row = rows.find((r) => r.gold.intent === intent && r.predictions.agent && !picked.includes(r) && r.text.length > 12);
    if (row) picked.push(row);
  }
  for (const r of rows) {
    if (picked.length >= 6) break;
    if (r.predictions.agent && !picked.includes(r)) picked.push(r);
  }
  return picked.slice(0, 6);
}

function sleep(msec: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, msec));
}

/** Display durations for the step animation, derived from the trace but clamped so each step is visible. */
function stepDurations(r: AgentResponse): Record<StepId, number> {
  const retrieval = r.trace?.retrieval_ms ?? 15;
  const llm = r.trace?.llm_ms ?? Math.max(400, r.latency_ms - retrieval);
  return {
    rules: 220,
    retrieve: Math.min(700, Math.max(320, retrieval * 20)),
    llm: Math.min(1300, Math.max(600, llm * 0.55)),
    decide: 260,
  };
}

function buildSteps(statuses: Record<StepId, StepStatus>, result: AgentResponse | null): TimelineStep[] {
  const forced = result?.trace?.forced_by_rules ?? false;
  const flags = result?.rule_flags ?? [];
  return [
    {
      id: "rules",
      label: "Rules",
      status: statuses.rules,
      ms: statuses.rules === "done" ? 1 : null,
      detail: statuses.rules === "done" ? (flags.length ? `${flags.length} flag${flags.length === 1 ? "" : "s"}${forced ? ", forced" : ""}` : "no flags") : undefined,
    },
    {
      id: "retrieve",
      label: "Retrieve",
      status: statuses.retrieve,
      ms: statuses.retrieve === "done" ? result?.trace?.retrieval_ms ?? null : null,
      detail: statuses.retrieve === "done" && result ? `${result.evidence.length} BM25 threads` : undefined,
    },
    {
      id: "llm",
      label: "Gemini",
      status: statuses.llm,
      ms: statuses.llm === "done" ? result?.trace?.llm_ms ?? null : null,
      detail: statuses.llm === "done" && result?.trace ? `${compact(result.trace.prompt_tokens)} → ${int(result.trace.output_tokens)} tok` : undefined,
    },
    {
      id: "decide",
      label: "Decide",
      status: statuses.decide,
      ms: statuses.decide === "done" ? 0 : null,
      detail: statuses.decide === "done" && result ? (result.decision === "escalate" ? "escalate" : "auto-handle") : undefined,
    },
  ];
}

const PENDING: Record<StepId, StepStatus> = { rules: "pending", retrieve: "pending", llm: "pending", decide: "pending" };

function ResultSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]" aria-hidden="true">
      <div className="flex flex-col gap-4">
        <div className="region flex flex-col gap-4 px-5 py-5">
          <Skeleton height={16} width="55%" />
          <Skeleton height={6} />
          <Skeleton height={28} width={140} radius={999} />
        </div>
        <Skeleton height={150} radius={8} />
      </div>
      <div className="flex flex-col gap-3">
        <Skeleton height={120} radius={8} />
        <Skeleton height={120} radius={8} />
      </div>
    </div>
  );
}

export default function AgentPlayground() {
  useDocumentTitle("Playground");
  const reduced = useReducedMotion();
  const golden = useAsync(getGolden, []);
  const results = useAsync(getResults, []);
  const threshold = results.data?.meta.threshold ?? 0.6;
  const examples = useMemo(() => (golden.data ? pickExamples(golden.data) : []), [golden.data]);

  const [text, setText] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [statuses, setStatuses] = useState<Record<StepId, StepStatus>>(PENDING);
  const [result, setResult] = useState<AgentResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [typed, setTyped] = useState(false);
  const runId = useRef(0);
  const textarea = useRef<HTMLTextAreaElement | null>(null);

  const selected = examples.find((e) => e.id === selectedId) ?? null;
  const over = text.length > TWEET_LIMIT;
  const canRun = phase !== "running" && text.trim().length > 0 && !over && (!IS_STATIC || selected !== null);

  const reset = useCallback(() => {
    runId.current += 1;
    setPhase("idle");
    setStatuses(PENDING);
    setResult(null);
    setError(null);
    setTyped(false);
  }, []);

  const chooseExample = (row: MergedGoldenExample) => {
    reset();
    setSelectedId(row.id);
    setText(row.text);
    if (!IS_STATIC) textarea.current?.focus();
  };

  const clear = () => {
    reset();
    setSelectedId(null);
    setText("");
    textarea.current?.focus();
  };

  const run = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!canRun) return;
    const id = ++runId.current;
    const alive = () => runId.current === id;
    setPhase("running");
    setResult(null);
    setError(null);
    setTyped(false);
    setStatuses({ ...PENDING, rules: "active" });

    const wait = (msec: number) => (reduced ? Promise.resolve() : sleep(msec));
    const request = handle(text);
    // While the request is in flight, walk the first steps so the user sees progress on real latency.
    const staging = (async () => {
      await wait(260);
      if (alive()) setStatuses({ rules: "done", retrieve: "active", llm: "pending", decide: "pending" });
      await wait(420);
      if (alive()) setStatuses({ rules: "done", retrieve: "done", llm: "active", decide: "pending" });
    })();

    let response: AgentResponse;
    try {
      response = await request;
    } catch (err) {
      if (!alive()) return;
      await staging;
      setStatuses((s) => ({ ...s, ...(s.llm === "active" ? { llm: "error" } : s.retrieve === "active" ? { retrieve: "error" } : { rules: "error" }) }));
      setError(err);
      setPhase("error");
      return;
    }
    await staging;
    if (!alive()) return;

    const d = stepDurations(response);
    setStatuses({ rules: "done", retrieve: "active", llm: "pending", decide: "pending" });
    await wait(Math.max(0, d.retrieve - 420));
    if (!alive()) return;
    setStatuses({ rules: "done", retrieve: "done", llm: "active", decide: "pending" });
    await wait(d.llm);
    if (!alive()) return;
    setStatuses({ rules: "done", retrieve: "done", llm: "done", decide: "active" });
    await wait(d.decide);
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
    <PageTransition>
      <PageHeader
        eyebrow={IS_STATIC ? "playground · recorded runs" : "playground · live agent"}
        title="Agent playground"
        description={
          IS_STATIC
            ? "Replay how the agent handled real customer tweets: which rules fired, what it retrieved, and the reply it drafted."
            : "Paste a customer tweet and watch the agent classify it, retrieve precedent, draft a reply and decide whether a human should take over."
        }
      />

      <form onSubmit={run} className="region flex flex-col gap-4 px-5 py-5 sm:px-6" aria-label="Message composer">
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-3">
            <label htmlFor="composer" className="eyebrow">
              {IS_STATIC ? "recorded messages · pick one" : "try one of these, or write your own"}
            </label>
            {golden.data && <span className="t-mono text-[12px] text-faint">{examples.length} of {golden.data.length} golden tweets</span>}
          </div>
          <div className="flex flex-wrap gap-2" role="list" aria-label="Example messages">
            {golden.loading && [0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} height={28} width={150 + (i % 3) * 40} radius={999} />)}
            {golden.error ? <p className="text-[13px] text-rose">Couldn't load the example tweets: {describeError(golden.error)}</p> : null}
            {examples.map((row) => (
              <Chip
                key={row.id}
                onClick={() => chooseExample(row)}
                selected={row.id === selectedId}
                aria-pressed={row.id === selectedId}
                title={row.text}
                className="max-w-full"
                icon={<span className="size-2 rounded-full" style={{ background: intentColor(row.gold.intent) }} />}
              >
                {truncate(row.text, 46)}
              </Chip>
            ))}
          </div>
        </div>

        <div className="relative">
          <textarea
            id="composer"
            ref={textarea}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              if (selectedId && examples.find((x) => x.id === selectedId)?.text !== e.target.value) setSelectedId(null);
              if (phase !== "idle") reset();
            }}
            disabled={IS_STATIC}
            rows={3}
            placeholder={IS_STATIC ? "Free text is off in this build. Pick a recorded message above." : "@SpotifyCares my app keeps crashing since the update…"}
            aria-describedby="composer-count"
            className={cx(
              "w-full resize-y rounded-md border bg-bg px-4 py-3 text-[16px] leading-relaxed text-text placeholder:text-faint disabled:cursor-not-allowed disabled:opacity-80",
              over ? "border-rose" : "border-border-strong",
            )}
          />
          <span id="composer-count" className={cx("t-mono pointer-events-none absolute right-3 bottom-3 text-[12px]", over ? "text-rose" : "text-faint")}>
            {text.length} / {TWEET_LIMIT}
          </span>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[12px] text-faint">
            {IS_STATIC ? "Recorded runs replay the agent's exact output, evidence and latencies." : "⌘/Ctrl + Enter runs. Replies are drafts; nothing is posted."}
          </p>
          <div className="flex items-center gap-2">
            <button type="button" className="btn btn-ghost" onClick={clear} disabled={!text && phase === "idle"}>
              <Eraser className="size-4" aria-hidden="true" />
              Clear
            </button>
            <button type="submit" className="btn btn-primary" disabled={!canRun}>
              <Play className="size-4" aria-hidden="true" />
              {phase === "running" ? "Running…" : IS_STATIC ? "Replay run" : "Run agent"}
            </button>
          </div>
        </div>
      </form>

      <section className="mt-8" aria-live="polite" aria-label="Agent result">
        {phase === "idle" && IS_STATIC && !selected && (
          <EmptyState
            icon={<TerminalSquare />}
            title="Free text needs the live server"
            description={
              <>
                This build reads exported results and replays recorded runs, so the composer is disabled. Pick one of the six messages above to see
                the full run. To try your own tweet, start the API with <code className="t-mono text-text">make serve</code> and open the UI in live mode.
              </>
            }
          />
        )}
        {phase === "idle" && (!IS_STATIC || selected) && (
          <EmptyState
            icon={<Sparkles />}
            title={selected ? "Ready to run" : "Pick or write a message"}
            description={selected ? `Press ${IS_STATIC ? "Replay run" : "Run agent"} to see how the agent handled this tweet.` : "The decision, the evidence and the drafted reply appear here."}
          />
        )}

        {(phase === "running" || phase === "error") && (
          <div className="flex flex-col gap-6">
            <div className="region px-5 py-4">
              <StepTimeline steps={steps} />
            </div>
            {phase === "running" && <ResultSkeleton />}
            {phase === "error" &&
              (isStaticModeError(error) ? (
                <EmptyState tone="amber" icon={<TerminalSquare />} title="No recorded run for this text" description={describeError(error)} />
              ) : (
                <ErrorState error={error} what="the agent response" onRetry={() => void run()} />
              ))}
          </div>
        )}

        {phase === "done" && result && (
          <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
            <div className="flex min-w-0 flex-col gap-4">
              <div className="region flex flex-col gap-4 px-5 py-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <IntentBadge id={result.intent} />
                  <span className="flex items-center gap-2">
                    {result.secondary_intent && (
                      <Chip size="sm" mono title="secondary intent">
                        + {result.secondary_intent}
                      </Chip>
                    )}
                    <Chip size="sm" tone={result.sentiment === "angry" ? "rose" : result.sentiment === "frustrated" ? "amber" : result.sentiment === "positive" ? "green" : "neutral"} dot>
                      {SENTIMENT_LABELS[result.sentiment]}
                    </Chip>
                  </span>
                </div>
                <ConfidenceBar value={result.intent_confidence} threshold={threshold} />
                <div className="hairline-t flex flex-col gap-2 pt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <DecisionPill decision={result.decision} reasonCode={result.escalation?.reason_code ?? null} showReason />
                    {result.trace?.forced_by_rules && (
                      <Chip size="sm" tone="amber" mono title="A deterministic rule forced this decision">
                        forced by rules
                      </Chip>
                    )}
                  </div>
                  <p className="text-[14px] leading-relaxed text-muted">
                    {result.escalation?.reason ?? "Grounded self-serve reply; no rule fired and confidence cleared the threshold, so it can post without review."}
                  </p>
                  {result.rule_flags.length > 0 && (
                    <ul className="mt-1 flex flex-wrap gap-1.5" aria-label="Rule flags">
                      {result.rule_flags.map((f) => (
                        <li key={f}>
                          <span className="tag" title={ruleFlagLabel(f)}>
                            {f}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              <ReplyPreview text={result.reply_draft} animate={!typed} onTyped={() => setTyped(true)} />

              {result.grounding_notes && (
                <div className="region-plain px-5 py-4">
                  <p className="eyebrow mb-2">grounding notes</p>
                  <p className="text-[14px] leading-relaxed text-muted">{result.grounding_notes}</p>
                  {result.citations.length > 0 && (
                    <p className="t-mono mt-2 text-[12px] text-faint">cites {result.citations.join(", ")}</p>
                  )}
                </div>
              )}
            </div>

            <div className="flex min-w-0 flex-col gap-4">
              <div className="region px-5 py-4">
                <StepTimeline steps={steps} />
                <div className="hairline-t flex flex-wrap items-center gap-2 pt-3">
                  <Chip size="sm" mono>{result.model}</Chip>
                  <Chip size="sm" mono tone={result.cached ? "violet" : "green"} title={result.cached ? "Served from the committed LLM cache" : "Fresh Gemini call"}>
                    {result.cached ? "cached" : "live call"}
                  </Chip>
                  <Chip size="sm" mono>{formatMs(result.latency_ms)} total</Chip>
                  {result.escalation?.reason_code && (
                    <span className="ml-auto text-[12px] text-faint">{reasonLabel(result.escalation.reason_code)}</span>
                  )}
                </div>
              </div>

              <div className="flex flex-col gap-3">
                <div className="flex items-baseline justify-between">
                  <h3 className="eyebrow">evidence · {result.evidence.length} retrieved, {result.evidence.filter((e) => e.cited).length} cited</h3>
                </div>
                {result.evidence.length === 0 ? (
                  <EmptyState compact title="No retrieval for this system" description="Baselines and zero-shot runs skip the BM25 step." />
                ) : (
                  <ul className="flex flex-col gap-3">
                    {result.evidence.map((ev, i) => (
                      <li key={ev.thread_id}>
                        <EvidenceCard evidence={ev} rank={i + 1} />
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        )}
      </section>
    </PageTransition>
  );
}
