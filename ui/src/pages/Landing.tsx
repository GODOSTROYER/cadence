import { ArrowDown, ArrowRight, ArrowUpRight, Lock } from "lucide-react";
import { useState, type ReactNode } from "react";
import { BenchmarkOverview } from "@/components/BenchmarkOverview";
import { Link } from "react-router-dom";

import { Callout } from "@/components/Callout";
import { Chip } from "@/components/Chip";
import { ErrorState } from "@/components/ErrorState";
import { isNum } from "@/components/eval/maybe";
import { StatTile } from "@/components/eval/StatTile";
import { MiniDemo } from "@/components/landing/MiniDemo";
import { MetricTile } from "@/components/MetricTile";
import { PageTransition, Reveal } from "@/components/PageTransition";
import { PipelineDiagram } from "@/components/PipelineDiagram";
import { Skeleton, SkeletonText } from "@/components/Skeleton";
import { useAsync } from "@/hooks/useAsync";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { AGENT_AVAILABLE, getHealth, getPublicSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cx } from "@/lib/cx";
import { HISTORICAL_CAVEATS } from "@/lib/evidenceCaveats";
import { ciPct, fixed, int, pct } from "@/lib/format";
import { systemLabelFor, systemShortFor, type SystemTask } from "@/lib/labels";
import { systemColor } from "@/lib/palette";
import type { Health, PublicSummary } from "@/lib/types";

const REPO = "https://github.com/GODOSTROYER/cadence";
const REPORT = `${REPO}/blob/main/REPORT.md`;
const DECISION_LOG = `${REPO}/blob/main/DECISION_LOG.md`;

// ---------------------------------------------------------------------------- small pieces

function SectionHead({ n, eyebrow, title, lede, id }: { n: string; eyebrow: string; title: ReactNode; lede?: ReactNode; id?: string }) {
  return (
    <div className="max-w-[72ch]">
      <p className="eyebrow mb-3 leading-relaxed">
        {n} · {eyebrow}
      </p>
      <h2 id={id} className="t-display t-display-40 text-text">
        {title}
      </h2>
      {lede && <p className="mt-3 text-[15px] leading-relaxed text-muted">{lede}</p>}
    </div>
  );
}

/** A link that says where it goes; admin destinations carry a lock and still work (the door opens in place). */
function GoLink({ to, href, children, admin = false }: { to?: string; href?: string; children: ReactNode; admin?: boolean }) {
  const inner = (
    <>
      {admin && <Lock className="size-3 shrink-0" aria-hidden="true" />}
      <span>{children}</span>
      {href ? <ArrowUpRight className="size-3.5 shrink-0" aria-hidden="true" /> : <ArrowRight className="size-3.5 shrink-0" aria-hidden="true" />}
    </>
  );
  const cls = "inline-flex items-center gap-1.5 text-[13px] text-muted transition-colors duration-[120ms] hover:text-green";
  if (href) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={cls}>
        {inner}
      </a>
    );
  }
  return (
    <Link to={to ?? "/"} className={cls}>
      {inner}
    </Link>
  );
}

interface StripRow {
  id: string;
  value: number;
  /** Secondary figure printed after the value (escalation: auto-handle rate). */
  aside?: string;
}

/** Agent vs baselines on one task: hairline rows, agent green, baselines violet. */
function BaselineStrip({ title, task, rows, format, note }: { title: string; task: SystemTask; rows: StripRow[]; format: (v: number) => string; note?: ReactNode }) {
  const max = Math.max(...rows.map((r) => r.value), 1e-9);
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <h3 className="t-display-20 text-text">{title}</h3>
      <ul className="flex flex-col gap-2.5">
        {rows.map((r) => (
          <li key={r.id} className="grid grid-cols-[minmax(0,120px)_1fr_auto] items-center gap-3 text-[13px]">
            <span className={cx("truncate", r.id === "agent" ? "font-medium text-text" : "text-muted")} title={systemLabelFor(task, r.id)}>
              {systemShortFor(task, r.id)}
            </span>
            <span className="relative h-1.5 overflow-hidden rounded-full bg-surface-2">
              <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${(r.value / max) * 100}%`, background: systemColor(r.id) }} />
            </span>
            <span className={cx("t-mono text-right whitespace-nowrap", r.id === "agent" ? "text-text" : "text-muted")}>
              {format(r.value)}
              {r.aside && <span className="ml-1.5 text-faint">{r.aside}</span>}
            </span>
          </li>
        ))}
      </ul>
      {note && <p className="text-[12px] leading-snug text-faint">{note}</p>}
    </div>
  );
}

function LandingSkeleton() {
  return (
    <div className="flex flex-col gap-12" aria-busy="true" aria-label="Loading">
      <div className="flex flex-col gap-5">
        <Skeleton height={12} width={260} />
        <Skeleton height={120} width="80%" radius={10} />
        <SkeletonText lines={2} lastWidth="55%" />
      </div>
      <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <MetricTile key={i} label="loading" value={0} loading />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------- content

function Content({ s, health }: { s: PublicSummary; health: Health | null }) {
  const { status } = useAuth();
  const unlocked = status === "admin" || status === "unavailable";
  const { meta, headline, intent, escalation, reply_quality: reply, annotator_agreement: annot } = s;
  const nOpeners = meta.dataset?.n_openers ?? health?.index_size ?? 0;
  const agentEsc = escalation.systems.agent;
  const noGuard = escalation.threshold_sweep.find((p) => p.threshold === 0) ?? escalation.threshold_sweep[0];
  const nnGap = isNum(headline.judge_overall_mean) && isNum(headline.judge_overall_mean_nn) ? headline.judge_overall_mean - headline.judge_overall_mean_nn : null;
  const zeroShot = intent.systems.llm_zero_shot;
  const live = Boolean(health?.has_api_key) && !health?.cache_only && AGENT_AVAILABLE;

  // Best simple baseline per task, chosen by the task's own headline metric.
  const bestSimpleIntent = (["simple_keyword", "simple"] as const).map((id) => ({ id, m: intent.systems[id] })).filter((x) => x.m).sort((a, b) => b.m!.macro_f1 - a.m!.macro_f1)[0];
  const simpleEsc = escalation.systems.simple ?? escalation.systems.simple_keyword;
  const trivialEsc = escalation.systems.trivial_always_escalate ?? escalation.systems.trivial;
  const zeroEsc = escalation.systems.llm_zero_shot;

  const scrollToResults = () => document.getElementById("results")?.scrollIntoView({ behavior: "smooth", block: "start" });

  const deliverables: { eyebrow: string; title: string; body: ReactNode; link: ReactNode }[] = [
    {
      eyebrow: "golden set",
      title: `${int(meta.n_golden)} tweets, labelled twice`,
      body: (
        <>
          Stratified sample of real openers; two AI annotation passes plus adjudication of the {int(annot.n_disagreements)} disagreements. AI agreement κ {fixed(annot.intent_kappa, 2)} on intent,{" "}
          {fixed(annot.escalation_kappa, 2)} on escalation. {int(meta.n_dev)} dev / {int(meta.n_test)} repeatedly inspected test examples.
        </>
      ),
      link: (
        <GoLink to="/golden" admin={!unlocked}>
          Golden explorer{unlocked ? "" : " · behind admin"}
        </GoLink>
      ),
    },
    {
      eyebrow: "baselines",
      title: "Seven things it has to beat",
      body: (
        <>
          Majority class, keyword rules, TF-IDF + logistic regression (out-of-fold), a zero-shot LLM with no retrieval (the ablation), always- and never-escalate, the most common brand template, and the nearest historical reply. Same {int(meta.n_test)}{" "}
          tweets, bootstrap CIs on all of them.
        </>
      ),
      link: (
        <button type="button" onClick={scrollToResults} className="inline-flex items-center gap-1.5 text-[13px] text-muted transition-colors duration-[120ms] hover:text-green">
          Results below
          <ArrowDown className="size-3.5" aria-hidden="true" />
        </button>
      ),
    },
    {
      eyebrow: "llm-as-judge",
      title: "Blind, comparative, a different model",
      body: (
        <>
          {meta.judge_model} scores agent, nearest-neighbour and template replies in one shuffled A/B/C call on five dimensions with three failure flags. Arnav Bule has reviewed and approved the latest 200-example benchmark and its existing scores.
        </>
      ),
      link: <GoLink to="/method#judge">The rubric</GoLink>,
    },
    {
      eyebrow: "failure analysis",
      title: "Three runs, five modes, verbatim",
      body: (
        <>
          Every error on the test split is mined into recurring modes with the real tweets, a hypothesis and a fix. Reading run 1 found three defects, run 2 found two more caused by the fixes; both earlier runs stay in the repo under{" "}
          <span className="t-mono text-text">results/v1</span> and <span className="t-mono text-text">v2</span>.
        </>
      ),
      link: (
        <GoLink to="/failures" admin={!unlocked}>
          Failure modes{unlocked ? "" : " · behind admin"}
        </GoLink>
      ),
    },
    {
      eyebrow: "reproducibility",
      title: "Archived calls, no key needed",
      body: (
        <>
          <span className="t-mono text-text">python -m cadence.cli reproduce</span> verifies recorded inputs and archived call receipts, then recomputes these archived metrics without a model call. This is artifact replay, not execution of the revised agent.
        </>
      ),
      link: <GoLink href={REPO}>GitHub · GODOSTROYER/cadence</GoLink>,
    },
    {
      eyebrow: "decision log",
      title: "Fifteen decisions in the revised submission",
      body: <>Why BM25 and not embeddings, why one structured call, why the judge is a different model, why the churn rule matches "switching to". Each with the reasoning at the time, not after.</>,
      link: unlocked ? <GoLink to="/decisions">Decision log</GoLink> : <GoLink href={DECISION_LOG}>DECISION_LOG.md</GoLink>,
    },
  ];

  const pipelineLines: { k: string; v: ReactNode }[] = [
    { k: "rules", v: "Deterministic regex flags for money, security, legal, churn and media-only messages. A forced flag decides on its own; the model cannot undo it." },
    { k: "retrieve", v: <>BM25 over {int(nOpeners)} historical threads, re-ranked towards ones that contain a resolution; the example's own thread is excluded so it never sees its answer key.</> },
    { k: "one call", v: <>{meta.agent_model} returns one JSON object: intent + confidence, sentiment, a reply, cited thread ids, and its own decision proposal.</> },
    { k: "policy", v: <>Rules veto first, then enforced defaults for security and billing, then the model's proposal, then a confidence guard at {fixed(meta.threshold, 2)} chosen on the dev split.</> },
    { k: "reply", v: "≤280 characters, brand voice measured from 43k real replies, at most one emoji, never asks for a password, signed /AI." },
  ];

  const next = [
    "The fresh locked 200-example benchmark and human review by Arnav Bule are complete. Compare the same agent with and without evidence before deciding whether another model call is justified.",
    "Judge order sensitivity is measured, and Arnav Bule has completed human review of all 200 revised benchmark examples.",
    "Expand the reviewed canonical links and label retrieval usefulness. Measure remaining broken-reference errors before claiming the link problem is solved.",
  ];

  return (
    <PageTransition className="flex flex-col gap-16 md:gap-20">
      {/* ------------------------------------------------------------------ hero */}
      <Reveal>
        <section className="grid items-center gap-8 pt-2 xl:grid-cols-[minmax(0,7fr)_minmax(0,4fr)] xl:gap-x-12 xl:pt-4" aria-labelledby="hero-title">
          <div className="min-w-0">
            <p className="eyebrow mb-6 leading-relaxed">Hiver SDE Intern take-home · Arnav Bule</p>
            <h1 id="hero-title" className="t-display t-italic max-w-[20ch] text-[clamp(48px,5vw,80px)] leading-[1.04] text-balance text-text">
              An AI support agent that knows when to stay quiet.
            </h1>
            <p className="mt-6 max-w-[58ch] text-[16px] leading-[1.7] text-muted sm:text-[17px]">
              Cadence reads a customer tweet, classifies the intent, drafts a reply grounded in {int(nOpeners)} real @SpotifyCares conversations, and decides whether a human must step in.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              <Link to="/agent" className="btn btn-primary h-10 w-full justify-center px-5 text-[14px] sm:w-auto">
                Try the live agent
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
              <button type="button" onClick={scrollToResults} className="btn h-10 w-full justify-center px-5 text-[14px] sm:w-auto">
                Read the evidence
                <ArrowDown className="size-4" aria-hidden="true" />
              </button>
            </div>
            <div className="mt-4 flex items-center gap-2">
              <Chip size="sm" mono tone={live ? "green" : "violet"} dot title={live ? "A Gemini key is configured; free text runs the real model." : "Live inference is unavailable or disabled. Historical results are shown separately."}>
                {live ? "live" : health?.cache_only ? "cache-only" : "recorded"}
              </Chip>
              <span className="t-mono text-[12px] text-faint">{health?.agent_model ?? meta.agent_model}</span>
            </div>
          </div>

          <dl className="hairline-t flex min-w-0 flex-col text-[13px] xl:border-t-0 xl:border-l xl:border-border xl:pl-8" aria-label="Facts">
            {[
              ["corpus", `${int(nOpeners)} SpotifyCares threads, 2017`],
              ["golden set", `${int(meta.n_golden)} tweets · two passes · κ ${fixed(annot.intent_kappa, 2)}`],
              ["test split", `${int(meta.n_test)} tweets, 12 intents, reused across runs`],
              ["baselines", "7 · trivial, simple, zero-shot LLM"],
              ["agent · judge", `${meta.agent_model} · ${meta.judge_model}`],
              ["replayable", "archived call receipts, no key needed"],
            ].map(([k, v]) => (
              <div key={k} className="hairline-b grid grid-cols-[100px_minmax(0,1fr)] items-baseline gap-4 py-3.5">
                <dt className="t-mono text-[12px] text-faint">{k}</dt>
                <dd className="min-w-0 leading-relaxed [overflow-wrap:anywhere] text-muted">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="border-t border-border pt-5 text-[13px] leading-relaxed text-muted xl:col-span-2">
            These charts show the archived agent on {int(meta.n_test)} repeatedly inspected AI-labelled test tweets. Revised benchmark results are reported separately in the repository; Arnav Bule has completed human review of all 200 revised benchmark examples.
          </p>
        </section>
      </Reveal>

      {/* ------------------------------------------------------------------ 60 seconds */}
      <Reveal>
        <section className="grid items-start gap-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)] lg:gap-12" aria-labelledby="sixty">
          <SectionHead n="01" eyebrow="for the evaluators" title={<span className="t-italic">In sixty seconds.</span>} id="sixty" />
          <div className="flex max-w-[64ch] flex-col gap-4 text-[16px] leading-relaxed text-text">
            <p>
              It classifies, drafts and decides. The interesting part is the third verb: the agent is built to know when it should not answer, and the evaluation is built to catch it when it gets that wrong.
            </p>
            <p className="text-muted">
              What was measured: intent against {intent.labels.length} hand-defined intents, whether a human was needed and whether the agent said so, and reply quality, each against trivial and simple baselines on the same{" "}
              {int(meta.n_test)} tweets with bootstrap intervals.
            </p>
            <p className="text-muted">
              The number to distrust is escalation recall, {pct(headline.escalation_recall)}. It is a policy setting, not a model property: a confidence guard chosen on {int(meta.n_dev)} dev tweets. Without it the same model scores{" "}
              {noGuard ? pct(noGuard.recall) : "less"}, and with it {int(agentEsc?.unnecessary_escalations ?? 0)} tweets go to a human who was not needed. The historical retrieval and zero-shot systems have similar classification scores
              {zeroShot ? ` (zero-shot scores ${fixed(zeroShot.macro_f1, 2)})` : ""}. This older comparison changes both prompt and policy; it does not isolate retrieval.
            </p>
            <p className="text-muted">
              Every claim here links to where it can be checked: the playground runs the real model, the method page shows the pipeline and the policy, and one command verifies saved receipts and recomputes historical metrics without a key.
            </p>
          </div>
        </section>
      </Reveal>

      {/* ------------------------------------------------------------------ brief → deliverables */}
      <Reveal>
        <section className="flex flex-col gap-8" aria-labelledby="brief">
          <SectionHead
            n="02"
            eyebrow="the brief, answered"
            title="Why this is a strong answer"
            id="brief"
            lede="The assignment asked for an agent and, in its own words, for proof worth more than the system. Each deliverable it named exists here, with a place to check it."
          />
          <ul className="grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 xl:grid-cols-3" role="list">
            {deliverables.map((d) => (
              <li key={d.eyebrow} className="flex min-w-0 flex-col gap-3 bg-bg px-6 py-6">
                <p className="eyebrow">{d.eyebrow}</p>
                <h3 className="t-display text-[24px] leading-tight text-text">{d.title}</h3>
                <p className="flex-1 text-[13px] leading-relaxed text-muted">{d.body}</p>
                <div className="pt-1">{d.link}</div>
              </li>
            ))}
          </ul>
          <p className="text-[13px] text-muted">
            The long form is the report:{" "}
            <a href={REPORT} target="_blank" rel="noreferrer" className="link">
              REPORT.md
            </a>
            , with the caveats section before the headline table.
          </p>
        </section>
      </Reveal>

      {/* ------------------------------------------------------------------ try it */}
      <Reveal>
        <section className="flex flex-col gap-8" aria-labelledby="try">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <SectionHead n="03" eyebrow="try it" title="Watch it decide" id="try" lede={AGENT_AVAILABLE ? "Real tweets from the golden set, or type your own. The steps light up on real latency; the reply is a draft and nothing is posted." : "Three recorded runs from the golden set. The deployed build runs the real model on your own text."} />
            <Link to="/agent" className="btn">
              Open the full playground
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </div>
          <MiniDemo threshold={meta.threshold} />
        </section>
      </Reveal>

      {/* ------------------------------------------------------------------ results */}
      <Reveal>
        <section id="results" className="flex flex-col gap-8 scroll-mt-8" aria-labelledby="results-title">
          <SectionHead n="04" eyebrow={`results · test split n=${int(meta.n_test)} · 95% bootstrap CI`} title="The evidence" id="results-title" lede="Four headline numbers with their intervals, the baselines they are measured against, and what is misleading about them." />
          <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
            <MetricTile label="intent macro-F1" value={headline.intent_macro_f1} format={(v) => fixed(v, 2)} ci={headline.ci95.intent_macro_f1 ?? undefined} hint="Unweighted mean of per-intent F1, so rare intents count as much as common ones." />
            <MetricTile
              label="escalation recall"
              value={headline.escalation_recall}
              format={(v) => pct(v)}
              ci={headline.ci95.escalation_recall ?? undefined}
              ciFormat={ciPct}
              tone="amber"
              hint="Share of tweets a human should handle that the agent did escalate. The costly error is the miss."
              sub={agentEsc ? <span className="t-mono text-rose">{agentEsc.missed_escalations} missed</span> : undefined}
            />
            <MetricTile label="auto-handle rate" value={headline.auto_handle_rate} format={(v) => pct(v)} ci={headline.ci95.auto_handle_rate ?? undefined} ciFormat={ciPct} tone="green" hint="Share of tweets the agent would answer without human review." />
            <StatTile
              label="judge overall · 1–5"
              value={headline.judge_overall_mean}
              format={(v) => fixed(v, 2)}
              ci={headline.ci95.judge_overall_mean ?? undefined}
              tone="sky"
              delta={isNum(nnGap) ? { value: nnGap, label: "vs nearest-neighbour reply" } : undefined}
              hint={`Mean holistic score from ${meta.judge_model}. The nearest-neighbour baseline reuses the closest historical brand reply verbatim. Reviewed and approved by Arnav Bule.`}
            />
          </div>

          <div className="region grid gap-8 px-6 py-6 md:grid-cols-3 md:gap-10">
            <BaselineStrip
              title="Intent macro-F1"
              task="intent"
              format={(v) => fixed(v, 2)}
              rows={[
                { id: "agent", value: intent.systems.agent?.macro_f1 ?? 0 },
                ...(zeroShot ? [{ id: "llm_zero_shot", value: zeroShot.macro_f1 }] : []),
                ...(bestSimpleIntent ? [{ id: bestSimpleIntent.id, value: bestSimpleIntent.m!.macro_f1 }] : []),
                ...(intent.systems.trivial ? [{ id: "trivial", value: intent.systems.trivial.macro_f1 }] : []),
              ]}
              note="Zero-shot sees the same taxonomy but no retrieved threads; it ties the agent, which is the honest finding."
            />
            <BaselineStrip
              title="Escalation recall · auto-handle"
              task="escalation"
              format={(v) => pct(v)}
              rows={[
                ...(agentEsc ? [{ id: "agent", value: agentEsc.recall, aside: pct(agentEsc.auto_handle_rate) }] : []),
                ...(zeroEsc ? [{ id: "llm_zero_shot", value: zeroEsc.recall, aside: pct(zeroEsc.auto_handle_rate) }] : []),
                ...(simpleEsc ? [{ id: "simple", value: simpleEsc.recall, aside: pct(simpleEsc.auto_handle_rate) }] : []),
                ...(trivialEsc ? [{ id: "trivial", value: trivialEsc.recall, aside: pct(trivialEsc.auto_handle_rate) }] : []),
              ]}
              note="Always-escalate has perfect recall and answers nothing. The second figure is how much each system self-serves."
            />
            {reply ? (
              <BaselineStrip
                title="Reply quality · judge 1–5"
                task="reply"
                format={(v) => fixed(v, 2)}
                rows={Object.entries(reply.systems)
                  .flatMap(([id, sys]) => (isNum(sys.mean.overall) ? [{ id, value: sys.mean.overall }] : []))
                  .sort((a, b) => b.value - a.value)}
                note={
                  reply.pairwise && isNum(reply.pairwise.agent_vs_nn_win_rate) && isNum(reply.pairwise.agent_vs_trivial_win_rate)
                    ? `Wins ${pct(reply.pairwise.agent_vs_nn_win_rate)} of head-to-heads against the nearest-neighbour reply, ${pct(reply.pairwise.agent_vs_trivial_win_rate)} against the template. AI-generated scores; the latest benchmark was reviewed and approved by Arnav Bule.`
                    : "AI-generated scores; the latest benchmark was reviewed and approved by Arnav Bule."
                }
              />
            ) : (
              <div className="flex flex-col gap-3">
                <h3 className="t-display-20 text-text">Reply quality · judge 1–5</h3>
                <p className="text-[13px] text-faint">Not judged in this export.</p>
              </div>
            )}
          </div>

          {HISTORICAL_CAVEATS.length > 0 && (
            <Callout title="What is misleading about these numbers" eyebrow="read before quoting them · the caveats are part of the submission">
              <ul>
                {HISTORICAL_CAVEATS.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </Callout>
          )}
        </section>
      </Reveal>

      {/* ------------------------------------------------------------------ how it works */}
      <Reveal>
        <section className="flex flex-col gap-8" aria-labelledby="how">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <SectionHead n="05" eyebrow="how it works" title="One message, one call, four gates" id="how" lede="Rules run first and can force an escalation the model cannot undo. Retrieval supplies precedent, the model drafts, and a policy layer has the last word." />
            <Link to="/method" className="btn">
              The full method
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </div>
          <div className="region px-5 py-6">
            <PipelineDiagram threshold={meta.threshold} />
          </div>
          <dl className="grid gap-x-10 gap-y-4 sm:grid-cols-2 lg:grid-cols-5">
            {pipelineLines.map((l) => (
              <div key={l.k} className="hairline-t pt-3">
                <dt className="eyebrow mb-1.5">{l.k}</dt>
                <dd className="text-[13px] leading-relaxed text-muted">{l.v}</dd>
              </div>
            ))}
          </dl>
        </section>
      </Reveal>

      {/* ------------------------------------------------------------------ next + footer */}
      <Reveal>
        <section className="grid gap-8 lg:grid-cols-[minmax(0,4fr)_minmax(0,7fr)] lg:gap-16" aria-labelledby="next">
          <SectionHead n="06" eyebrow="what I'd do next" title={<span className="t-italic">With one more week.</span>} id="next" />
          <ol className="flex flex-col divide-y divide-border">
            {next.map((line, i) => (
              <li key={i} className="grid grid-cols-[40px_1fr] gap-3 py-4 text-[14px] leading-relaxed text-muted">
                <span className="numeral text-[24px] text-faint">{String(i + 1).padStart(2, "0")}</span>
                <span>{line}</span>
              </li>
            ))}
          </ol>
        </section>
      </Reveal>

      <footer className="hairline-t flex flex-col gap-4 pt-8 text-[13px] text-muted sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <p className="text-text">Arnav Bule</p>
          <p className="flex flex-wrap gap-x-4 gap-y-1">
            <a href="https://github.com/GODOSTROYER" target="_blank" rel="noreferrer" className="link">
              github.com/GODOSTROYER
            </a>
            <a href="https://arnavbule.in" target="_blank" rel="noreferrer" className="link">
              arnavbule.in
            </a>
            <a href="mailto:arnav.bule05@gmail.com" className="link">
              arnav.bule05@gmail.com
            </a>
          </p>
        </div>
        <div className="flex max-w-[48ch] flex-col gap-1.5 sm:text-right">
          <p>Built with {meta.agent_model}. Archived evaluation calls are replayable; live visitor replies are not stored in the deployed cache.</p>
          <p className="t-mono text-[12px] text-faint">
            archived results {meta.generated_at.slice(0, 10)} · evaluation sha {meta.git_sha.slice(0, 9)} · historical cache hit rate {pct(meta.cache_hit_rate)}
          </p>
        </div>
      </footer>
    </PageTransition>
  );
}

function HistoricalLanding() {
  useDocumentTitle("");
  const summary = useAsync(getPublicSummary, []);
  const health = useAsync(getHealth, []);

  if (summary.loading) return <LandingSkeleton />;
  if (summary.error || !summary.data) return <ErrorState error={summary.error} what="the public results" onRetry={summary.reload} />;
  return <Content s={summary.data} health={health.data} />;
}


export default function Landing() {
  useDocumentTitle("");
  const [historical, setHistorical] = useState(false);
  return <>
    <div className="mb-8 flex flex-wrap items-center gap-3 text-sm" aria-label="Evaluation version">
      <button type="button" className={`btn ${!historical ? "btn-primary" : ""}`} aria-pressed={!historical} onClick={() => setHistorical(false)}>Revised benchmark</button>
      <button type="button" className={`btn ${historical ? "btn-primary" : ""}`} aria-pressed={historical} onClick={() => setHistorical(true)}>Historical charts</button>
    </div>
    {historical ? <HistoricalLanding /> : <BenchmarkOverview />}
  </>;
}
