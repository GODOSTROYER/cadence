import { ArrowRight, Check, SearchX, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";

import { Chip } from "@/components/Chip";
import { DataTable, type Column } from "@/components/DataTable";
import { DecisionPill } from "@/components/DecisionPill";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { judgedSystem } from "@/components/eval/systemKeys";
import { GoldenDrawer } from "@/components/golden/GoldenDrawer";
import { GoldenFilters } from "@/components/golden/GoldenFilters";
import { compareRow, DEFAULT_QUERY, matchesQuery, parseQuery, summarize, SYSTEM_ORDER, writeQuery, type Comparison, type GoldenQuery } from "@/components/golden/query";
import { ScoreMark } from "@/components/golden/ScoreMark";
import { IntentBadge } from "@/components/IntentBadge";
import { Kbd } from "@/components/Kbd";
import { PageHeader } from "@/components/PageHeader";
import { PageTransition } from "@/components/PageTransition";
import { Skeleton } from "@/components/Skeleton";
import { useAsync } from "@/hooks/useAsync";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { getGolden, getResults } from "@/lib/api";
import { cx } from "@/lib/cx";
import { int } from "@/lib/format";
import { INTENT_IDS } from "@/lib/intents";
import { systemShort } from "@/lib/labels";
import type { MergedGoldenExample, SystemId } from "@/lib/types";

interface Entry {
  row: MergedGoldenExample;
  cmp: Comparison;
}

const ROW_ATTR = "data-golden-id";

function judgeOverall(row: MergedGoldenExample, system: SystemId): number | null {
  const judged = judgedSystem(system);
  const score = judged ? row.judge[judged]?.scores.overall : undefined;
  return typeof score === "number" ? score : null;
}

/** Table columns for the compared system. Cells carry no extra tab stops; details live in the drawer. */
function buildColumns(system: SystemId): Column<Entry>[] {
  return [
    {
      id: "id",
      header: "id",
      width: 76,
      mono: true,
      align: "left",
      cell: ({ row }) => (
        <span {...{ [ROW_ATTR]: row.id }} className="text-muted">
          {row.id}
        </span>
      ),
      sortValue: ({ row }) => row.id,
    },
    {
      id: "text",
      header: "Message",
      cell: ({ row }) => (
        <span className="truncate-2 block max-w-[56ch] min-w-[220px] text-[13px] leading-snug text-text" title={row.text}>
          {row.text}
        </span>
      ),
    },
    {
      id: "gold",
      header: "Gold intent",
      cell: ({ row }) => <IntentBadge id={row.gold.intent} size="sm" compact showId={false} className="whitespace-nowrap" />,
      sortValue: ({ row }) => row.gold.intent,
    },
    {
      id: "pred",
      header: `Predicted · ${systemShort(system)}`,
      cell: ({ cmp }) =>
        cmp.pred ? (
          <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
            {cmp.intentCorrect ? <Check className="size-3.5 shrink-0 text-green" aria-label="correct" /> : <X className="size-3.5 shrink-0 text-rose" aria-label="wrong" />}
            <IntentBadge id={cmp.pred.intent} size="sm" compact showId={false} wrong={!cmp.intentCorrect} />
          </span>
        ) : (
          <span className="text-faint">—</span>
        ),
      sortValue: ({ cmp }) => (cmp.intentCorrect === null ? null : cmp.intentCorrect ? 1 : 0),
    },
    {
      id: "decision",
      header: "Decision · gold → predicted",
      hideOnMobile: true,
      cell: ({ cmp }) => (
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <DecisionPill size="sm" quiet decision={cmp.goldDecision} />
          <ArrowRight className="size-3 shrink-0 text-faint" aria-hidden="true" />
          {cmp.pred ? <DecisionPill size="sm" quiet decision={cmp.pred.decision} /> : <span className="text-faint">—</span>}
          {cmp.decisionError && <span className={cx("tag", cmp.decisionError === "missed" ? "border-rose/40 text-rose" : "border-amber/40 text-amber")}>{cmp.decisionError}</span>}
        </span>
      ),
      sortValue: ({ cmp }) => (cmp.decisionError === "missed" ? 0 : cmp.decisionError === "unnecessary" ? 1 : 2),
    },
    {
      id: "judge",
      header: "Judge",
      align: "right",
      hideOnMobile: true,
      cell: ({ row }) => <ScoreMark value={judgeOverall(row, system)} label={`${systemShort(system)} overall`} />,
      sortValue: ({ row }) => judgeOverall(row, system),
    },
    {
      id: "split",
      header: "Split",
      hideOnMobile: true,
      width: 72,
      cell: ({ row }) => (
        <Chip size="sm" mono tone={row.split === "dev" ? "violet" : "neutral"}>
          {row.split}
        </Chip>
      ),
      sortValue: ({ row }) => row.split,
    },
  ];
}

function ExplorerSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading golden set">
      <Skeleton height={124} radius={8} />
      <Skeleton height={14} width={320} />
      <DataTable columns={buildColumns("agent")} rows={[]} rowKey={() => ""} loading skeletonRows={10} caption="Loading" />
    </div>
  );
}

/**
 * Every labelled tweet with gold labels, the compared system's prediction and the judge's overall score.
 * Filters, search, the compared system and the open row all live in the URL query string.
 */
export default function GoldenExplorer() {
  useDocumentTitle("Golden set");
  const golden = useAsync(getGolden, []);
  const results = useAsync(getResults, []);
  const [params, setParams] = useSearchParams();
  const searchRef = useRef<HTMLInputElement | null>(null);
  const tableRef = useRef<HTMLDivElement | null>(null);

  const rows = golden.data ?? [];
  const systems = useMemo<SystemId[]>(() => {
    const present = SYSTEM_ORDER.filter((s) => rows.some((r) => r.predictions[s]));
    return present.length ? present : ["agent"];
  }, [rows]);
  const intents = useMemo(() => {
    const present = new Set(rows.map((r) => r.gold.intent));
    const known = INTENT_IDS.filter((id) => present.has(id));
    const unknown = [...present].filter((id) => !INTENT_IDS.includes(id)).sort();
    return [...known, ...unknown];
  }, [rows]);

  const query = useMemo(() => parseQuery(params, systems), [params, systems]);

  const update = useCallback(
    (patch: Partial<GoldenQuery>) => {
      setParams((prev) => writeQuery(prev, { ...parseQuery(prev, systems), ...patch }), { replace: true });
    },
    [setParams, systems],
  );

  // Decisions are re-derived at the evaluated threshold so the table agrees with the Evaluation page.
  const threshold = results.data?.meta.threshold;
  const entries = useMemo<Entry[]>(() => rows.map((row) => ({ row, cmp: compareRow(row, query.system, threshold) })), [rows, query.system, threshold]);
  const filtered = useMemo(() => entries.filter(({ row, cmp }) => matchesQuery(row, query, cmp)), [entries, query]);
  const stats = useMemo(() => summarize(filtered), [filtered]);
  const columns = useMemo(() => buildColumns(query.system), [query.system]);

  const selected = query.id ? rows.find((r) => r.id === query.id) ?? null : null;

  /** Ids in the table's current visual (sorted) order, read from the DOM because DataTable owns its sort state. */
  const visibleIds = useCallback((): string[] => {
    const nodes = tableRef.current?.querySelectorAll<HTMLElement>(`[${ROW_ATTR}]`) ?? [];
    return Array.from(nodes, (el) => el.getAttribute(ROW_ATTR) ?? "").filter(Boolean);
  }, []);

  const focusRow = useCallback((id: string | null) => {
    if (!id) return;
    const cell = tableRef.current?.querySelector<HTMLElement>(`[${ROW_ATTR}="${id}"]`);
    cell?.closest("tr")?.focus();
  }, []);

  const openRow = useCallback((entry: Entry) => update({ id: entry.row.id }), [update]);

  const close = useCallback(() => {
    const id = query.id;
    update({ id: null });
    window.setTimeout(() => focusRow(id), 60);
  }, [query.id, update, focusRow]);

  const step = useCallback(
    (delta: 1 | -1) => {
      const ids = visibleIds();
      const i = query.id ? ids.indexOf(query.id) : -1;
      const next = ids[i + delta];
      if (next) update({ id: next });
    },
    [visibleIds, query.id, update],
  );

  const position = useMemo(() => {
    if (!query.id) return null;
    const ids = visibleIds();
    const index = ids.indexOf(query.id);
    return index === -1 ? null : { index, total: ids.length };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the DOM order changes with the filtered rows
  }, [query.id, filtered, visibleIds]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const nDev = rows.filter((r) => r.split === "dev").length;
  const eyebrow = golden.data ? `golden set · ${int(rows.length)} hand-labelled tweets · ${int(nDev)} dev / ${int(rows.length - nDev)} test` : "golden set · hand-labelled tweets";

  return (
    <PageTransition>
      <PageHeader eyebrow={eyebrow} title="Golden explorer" description="Every labelled tweet with its gold labels, each system's prediction and the judge's verdict. Click a row, or arrow through the table and press Enter, for the full record." />

      {golden.loading && <ExplorerSkeleton />}
      {!golden.loading && (golden.error || !golden.data) && <ErrorState error={golden.error} what="the golden set" onRetry={golden.reload} />}

      {golden.data && (
        <div className="flex flex-col gap-4">
          <GoldenFilters
            ref={searchRef}
            query={query}
            onChange={update}
            onReset={() => update({ ...DEFAULT_QUERY, system: query.system, id: query.id })}
            intents={intents}
            systems={systems}
            stats={stats}
            total={rows.length}
            onSearchArrowDown={() => focusRow(visibleIds()[0] ?? null)}
          />

          <div ref={tableRef}>
            <DataTable
              columns={columns}
              rows={filtered}
              rowKey={(e) => e.row.id}
              onRowClick={openRow}
              selectedKey={query.id}
              initialSort={{ id: "id", dir: "asc" }}
              density="compact"
              maxHeight="min(68vh, 780px)"
              caption={`Golden examples compared against ${systemShort(query.system)}: ${int(filtered.length)} of ${int(rows.length)} shown`}
              empty={
                <EmptyState
                  compact
                  icon={<SearchX />}
                  title="No tweets match"
                  description="Loosen a filter or clear the search."
                  action={
                    <button type="button" className="btn" onClick={() => update({ ...DEFAULT_QUERY, system: query.system })}>
                      Reset filters
                    </button>
                  }
                />
              }
            />
          </div>

          <p className="hidden flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-faint sm:flex">
            <span className="flex items-center gap-1">
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> move between rows
            </span>
            <span className="flex items-center gap-1">
              <Kbd>⏎</Kbd> open
            </span>
            <span className="flex items-center gap-1">
              <Kbd>esc</Kbd> close
            </span>
            <span className="ml-auto">
              Predicted intent and decision are {systemShort(query.system)}'s{typeof threshold === "number" ? `, with the decision re-derived at the evaluated ${threshold.toFixed(2)} confidence guard` : ""}; switch the compared system above.
            </span>
          </p>

          <GoldenDrawer row={selected} requestedId={query.id} onClose={close} onStep={step} position={position} system={query.system} threshold={results.data?.meta.threshold} />
        </div>
      )}
    </PageTransition>
  );
}
