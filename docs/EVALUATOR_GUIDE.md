# Evaluator guide: reproduce and inspect in fifteen minutes

## 1. Read the claim (2 minutes)

Read `REPORT.md`, especially “What is misleading about my headline number?”. Original numbers belong to the archived agent. New labels are AI-reviewed, not human ground truth. There are no human judge-agreement scores. The author explicitly requested AI review instead.

## 2. Recompute archived metrics (3 minutes after dependency install)

```bash
python -m pip install -e ".[dev]"
python -m cadence.cli reproduce
```

This verifies input hashes and 1,771 cached receipts, then recomputes the old results under `results/reproduced/`, without a key or network calls. Expect intent macro-F1 ≈0.82148, escalation recall≈0.93976 and auto-handle rate 0.43. Inspect `meta.threshold_selection`: the original dev recall constraint was not met. The command does not execute today's changed model pipeline.

## 3. Inspect fresh evidence (4 minutes)

- `data/holdout/HOLDOUT.lock.json`: sampling exclusions, seed and hashes.
- `data/holdout/AI_REVIEW.lock.json`: 200 AI labels, 81 escalations, zero human ratings.
- `data/holdout/ai_review_notes.tsv`: individual labels and rationales, written before predictions.
- `results/holdout_final/manifest.json`: exact execution revision, labels, threshold and source fingerprints.
- `results/holdout_final/predictions.jsonl`: 800 predictions, four systems with identical 200 IDs.
- `results/holdout_final/judge_orders.jsonl`: two presentation orders for each agent/baseline pair.
- `docs/FAILURE_ANALYSIS_FRESH.md`: five concrete failure modes and post-audit repair boundaries.
- `results/dev_experiment/comparison.json`: 50-message paired retrieval ablation.
- `results/dev_experiment/draft_judge_comparison.json`: 20-message, both-order comparison of pre-guard drafts; human agreement is explicitly null.

Recompute the revised run's coverage, receipt checks and (only when complete) paired metrics:

```bash
python analysis_tools/reproduce_benchmark.py
```

The default selects the completed frozen benchmark. Expect agent macro-F1 .78886, recall .93827, coverage .35, and five missed escalations. Outputs go to `results/reproduced/benchmark_summary.json`; zero model calls. Selecting `--directory results/holdout` instead reports the preserved initial run as incomplete and withholds its headline metrics.

The final release layer additionally blocks unsupported completed actions, historical numeric capability limits and automatic private handoffs. Reproduce its **retrospective** verification with `python analysis_tools/post_audit_regression.py`. It copies the frozen receipt store to a temporary database, enforces cache-only mode, and writes separate artifacts under `results/post_audit_regression/`. This set was already inspected: these are regression results, never fresh benchmark claims. Original judge scores do not apply to changed replies.

All successful new model calls retain receipts in the respective `calls.sqlite`. Cached metadata stores original request latency; it is not the cost or time of a later replay. Failed requests are discussed in the run record and must not be silently counted as successful benchmark calls.

## 4. Verify implementation (4 minutes)

```bash
python -m pytest -q
python -m ruff check src scripts tests api
cd ui
npm ci
npm run build
```

The offline suite exercises data, retrieval, structured response parsing, deterministic escalation, integrity checks, cached evaluation and both API entrypoints. The UI build checks TypeScript and bundling; it is not browser interaction testing. CI is configured for Windows/Linux Python and Node, but local results are the executed evidence unless a remote CI run is linked.

## 5. Inspect a case (2 minutes)

Trace a message through `src/cadence/agent/pipeline.py`, then compare its evidence, citations, `trace.llm_decision`, integrity flags and final decision. For an unsafe URL fixture, the final reply must become a holding reply and escalate. For sensitive secondary intent, policy must also escalate. A valid citation alone is not proof the reply follows from it.

The existing public demo was not redeployed from this branch. Run locally to inspect revised code; live inference requires confirmed free-tier credentials and sends text to Gemini. No account changes or tweet posting occur. The benchmark runner supports `--ai-reviewed` explicitly; its optional human-label path refuses fabricated human provenance.
