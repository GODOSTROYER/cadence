import { useRef, type KeyboardEvent } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ThresholdChart } from "@/components/ThresholdChart";
import { cx } from "@/lib/cx";
import { ciPct, fixed, int, pct } from "@/lib/format";
import { systemLabelFor, systemShortFor } from "@/lib/labels";
import type { EscalationSystemMetrics, EvalSummary, MergedGoldenExample } from "@/lib/types";

import { ExampleList } from "./ExampleList";
import { ciOf, extra, fmtMaybe, isNum, type Maybe } from "./maybe";
import { orderSystems, predictionSystem, resolveSystem } from "./systemKeys";

export interface EscalationTabProps {
  summary: EvalSummary;
  golden: MergedGoldenExample[] | null;
  system: string | null;
  onSystemChange: (system: string) => void;
}

interface StatProps {
  label: string;
  value: Maybe<number>;
  format: (v: number) => string;
  sub?: string;
  tone?: "neutral" | "rose" | "amber" | "green";
}

const STAT_TONE = { neutral: "text-text", rose: "text-rose", amber: "text-amber", green: "text-green" } as const;

function Stat({ label, value, format, sub, tone = "neutral" }: StatProps) {
  return (
    <div className="min-w-0">
      <dt className="eyebrow text-[11px] normal-case">{label}</dt>
      <dd className={cx("numeral mt-1 text-[24px]", isNum(value) ? STAT_TONE[tone] : "text-faint")}>{fmtMaybe(value, format)}</dd>
      {sub && <dd className="t-mono mt-0.5 truncate text-[11px] text-faint">{sub}</dd>}
    </div>
  );
}

interface TileProps {
  systemKey: string;
  metrics: EscalationSystemMetrics;
  selected: boolean;
  onSelect: () => void;
  tabIndex: number;
  register: (el: HTMLButtonElement | null) => void;
}

/** One system's escalation numbers; the group behaves like a radio group that picks which error lists show. */
function SystemTile({ systemKey, metrics, selected, onSelect, tabIndex, register }: TileProps) {
  const agent = systemKey === "agent";
  const recallCi = ciOf(metrics.ci95?.recall);
  const autoCi = ciOf(metrics.ci95?.auto_handle_rate);
  return (
    <button
      ref={register}
      type="button"
      role="radio"
      aria-checked={selected}
      tabIndex={tabIndex}
      onClick={onSelect}
      className={cx(
        "region flex min-w-0 flex-col gap-4 px-5 py-4 text-left transition-colors duration-[120ms] hover:bg-surface-2",
        selected ? "border-border-strong bg-surface-2" : "border-border",
        agent && "relative overflow-hidden",
      )}
    >
      {agent && <span aria-hidden="true" className="absolute top-4 bottom-4 left-0 w-px bg-green" />}
      <header className="flex items-baseline justify-between gap-2">
        <span className={cx("truncate text-[14px] font-medium", agent ? "text-text" : "text-muted")} title={systemLabelFor("escalation", systemKey)}>
          {systemShortFor("escalation", systemKey)}
        </span>
        <span className="t-mono shrink-0 text-[11px] text-faint">F1 {fmtMaybe(metrics.f1, (v) => fixed(v, 2))}</span>
      </header>
      <dl className="grid grid-cols-3 gap-x-3 gap-y-3">
        <Stat label="recall" value={metrics.recall} format={(v) => pct(v)} sub={recallCi ? ciPct(recallCi) : undefined} tone={agent ? "green" : "neutral"} />
        <Stat label="precision" value={metrics.precision} format={(v) => pct(v)} />
        <Stat label="auto-handle" value={metrics.auto_handle_rate} format={(v) => pct(v)} sub={autoCi ? ciPct(autoCi) : undefined} />
        <Stat label="missed" value={metrics.missed_escalations} format={(v) => int(v)} tone={isNum(metrics.missed_escalations) && metrics.missed_escalations > 0 ? "rose" : "neutral"} />
        <Stat label="unnecessary" value={metrics.unnecessary_escalations} format={(v) => int(v)} tone={isNum(metrics.unnecessary_escalations) && metrics.unnecessary_escalations > 0 ? "amber" : "neutral"} />
        <Stat label="reason acc." value={metrics.reason_code_accuracy} format={(v) => pct(v)} />
      </dl>
    </button>
  );
}

function dedupeByConfusion(keys: string[], systems: Record<string, EscalationSystemMetrics>): string[] {
  const seen = new Set<string>();
  return keys.filter((k) => {
    const c = systems[k]?.confusion;
    if (!c) return false;
    const sig = `${c.tp}/${c.fp}/${c.fn}/${c.tn}`;
    if (seen.has(sig)) return false;
    seen.add(sig);
    return true;
  });
}

/** Per-system tiles, the threshold sweep with the chosen threshold, and the missed / unnecessary escalation lists. */
export function EscalationTab({ summary, golden, system, onSystemChange }: EscalationTabProps) {
  const block = summary.escalation;
  // The eval module writes both the §15.1 ids and the computed baselines; when two keys carry the same
  // confusion counts (simple = simple_keyword, trivial = trivial_always_escalate) show only the first.
  const keys = dedupeByConfusion(orderSystems(Object.keys(block.systems)), block.systems);
  const key = resolveSystem(keys, system);
  const metrics = key ? block.systems[key] : undefined;
  const threshold = extra<number>(block, "threshold") ?? summary.meta.threshold;
  const chosenOn = extra<string>(block, "threshold_chosen_on") ?? "dev";
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const onGroupKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = key ? keys.indexOf(key) : 0;
    let next = i;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (i + 1) % keys.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (i - 1 + keys.length) % keys.length;
    else return;
    e.preventDefault();
    const target = keys[next];
    if (!target) return;
    onSystemChange(target);
    refs.current[next]?.focus();
  };

  if (!key || !metrics) {
    return <p className="text-[13px] text-muted">No escalation metrics in this summary.</p>;
  }

  const predSystem = predictionSystem(key);
  const unnecessary = extra<string[]>(metrics, "unnecessary_examples");
  const c = metrics.confusion;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="eyebrow">
          escalate is the positive class · {int(c.tp + c.fn)} of {int(c.tp + c.fn + c.fp + c.tn)} test tweets need a human · threshold {fixed(threshold, 2)} chosen on {chosenOn}
        </p>
        <p className="text-[12px] text-faint">Select a system to see its errors below.</p>
      </div>

      <div role="radiogroup" aria-label="Escalation system" onKeyDown={onGroupKey} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {keys.map((k, i) => {
          const m = block.systems[k];
          if (!m) return null;
          return (
            <SystemTile
              key={k}
              systemKey={k}
              metrics={m}
              selected={k === key}
              onSelect={() => onSystemChange(k)}
              tabIndex={k === key ? 0 : -1}
              register={(el) => {
                refs.current[i] = el;
              }}
            />
          );
        })}
      </div>

      <section className="region px-5 py-5" aria-label="Threshold sweep">
        {block.threshold_sweep.length > 0 ? (
          <ThresholdChart
            sweep={block.threshold_sweep}
            chosen={threshold}
            title="Recall against auto-handle rate as the confidence threshold moves"
            subtitle={`Agent only. Intent confidence below the threshold forces an escalation (low_confidence); the marked value was picked on the ${chosenOn} split and never touched again. The curve is flat on the left because the model almost never reports low confidence, then recall climbs steeply once the guard reaches the narrow band where most of its confidences sit, and auto-handle collapses with it.`}
          />
        ) : (
          <EmptyState compact title="No threshold sweep" description="The agent produced no dev-split predictions, so the sweep was not computed." />
        )}
      </section>

      <div className="grid gap-8 xl:grid-cols-2">
        <ExampleList
          ids={metrics.missed_examples}
          golden={golden}
          systemKey={key}
          predictionSystem={predSystem}
          tone="rose"
          title="Missed escalations"
          description="Gold says a human must take it; the system auto-handled. The costly error."
        />
        {unnecessary ? (
          <ExampleList ids={unnecessary} golden={golden} systemKey={key} predictionSystem={predSystem} tone="amber" title="Unnecessary escalations" description="Gold says it could be self-served; the system sent it to a human." />
        ) : (
          <section className="flex flex-col gap-3" aria-label="Unnecessary escalations">
            <h3 className="t-display-20 text-text">
              Unnecessary escalations <span className="t-mono text-[16px] text-amber">{fmtMaybe(metrics.unnecessary_escalations, (v) => int(v))}</span>
            </h3>
            <p className="text-[13px] text-muted">This export lists counts only; the per-example ids arrive with the eval module's `unnecessary_examples` field.</p>
          </section>
        )}
      </div>

      <dl className="region-plain grid gap-x-8 gap-y-3 px-5 py-4 text-[13px] sm:grid-cols-2 lg:grid-cols-4" aria-label={`Confusion counts for ${systemLabelFor("escalation", key)}`}>
        <div>
          <dt className="text-faint">True positives</dt>
          <dd className="t-mono text-text">{int(c.tp)} escalated, needed it</dd>
        </div>
        <div>
          <dt className="text-faint">False negatives</dt>
          <dd className="t-mono text-rose">{int(c.fn)} missed</dd>
        </div>
        <div>
          <dt className="text-faint">False positives</dt>
          <dd className="t-mono text-amber">{int(c.fp)} unnecessary</dd>
        </div>
        <div>
          <dt className="text-faint">True negatives</dt>
          <dd className="t-mono text-text">{int(c.tn)} self-served, rightly</dd>
        </div>
      </dl>
    </div>
  );
}
