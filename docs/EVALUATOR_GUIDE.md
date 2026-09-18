# Evaluator guide: reproduce and inspect in fifteen minutes

## 1. Read the claim (2 minutes)

Read `REPORT.md`, especially “What is misleading about my headline number?”. Original numbers belong to the archived agent. All 200 revised benchmark examples and their existing scores were reviewed and approved by Arnav Bule. See [review record](HUMAN_REVIEW.md).

## 2. Recompute archived metrics (3 minutes after dependency install)

```bash
python -m pip install -e ".[dev]"
python -m cadence.cli reproduce
```

This verifies input hashes and 1,771 cached receipts, then recomputes the old results under `results/reproduced/`, without a key or network calls. Expect intent macro-F1 ≈0.82148, escalation recall≈0.93976 and auto-handle rate 0.43. Inspect `meta.threshold_selection`: the original dev recall constraint was not met. The command does not execute today's changed model pipeline.

## 3. Inspect fresh evidence (4 minutes)

- `data/holdout/HOLDOUT.lock.json`: sampling exclusions, seed and hashes.
- `data/holdout/AI_REVIEW.lock.json`: original pre-inference label lock: 200 examples, 81 escalations. Completed review and approval by Arnav Bule is recorded in `data/holdout/HUMAN_REVIEW.json`.
- `data/holdout/ai_review_notes.tsv`: individual labels and rationales, written before predictions.
- `results/holdout_final/manifest.json`: exact execution revision, labels, threshold and source fingerprints.
- `results/holdout_final/predictions.jsonl`: 800 predictions, four systems with identical 200 IDs.
- `results/holdout_final/judge_orders.jsonl`: two presentation orders for each agent/baseline pair.
- `docs/FAILURE_ANALYSIS_FRESH.md`: five concrete failure modes and post-audit repair boundaries.
- `results/dev_experiment/comparison.json`: 50-message paired retrieval ablation.
- `results/dev_experiment/draft_judge_comparison.json`: 20-message, both-order comparison of pre-guard drafts.

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

The offline suite exercises data, retrieval, structured response parsing, deterministic escalation, integrity checks, cached evaluation and both API entrypoints. The UI build checks TypeScript and bundling; it is not browser interaction testing. [Remote CI](https://github.com/GODOSTROYER/cadence/actions/runs/35033646086) passed on implementation commit `3efe5bb`: Linux Python 74 seconds, Windows Python 164 seconds, and Node/UI 20 seconds, including dependency installation. Both Python jobs also reproduced frozen metrics and cached guard regressions.

## 5. Inspect a case (2 minutes)

Trace a message through `src/cadence/agent/pipeline.py`, then compare its evidence, citations, `trace.llm_decision`, integrity flags and final decision. For an unsafe URL fixture, the final reply must become a holding reply and escalate. For sensitive secondary intent, policy must also escalate. A valid citation alone is not proof the reply follows from it.

See [deployment verification](DEPLOYMENT.md) for the current public release. The dashboard defaults to the revised frozen benchmark; historical charts are available through the version switch. Supplemental review and development experiments are documented in [improvements](IMPROVEMENTS.md). Run locally to reproduce the code; live inference requires confirmed free-tier credentials and sends text to Gemini. No account changes or tweet posting occur. The benchmark runner supports `--ai-reviewed` explicitly; its optional human-label path validates the supplied label records.

## Completed supplemental review and development comparison

On 17 September 2026, Arnav Bule verified all 100 scores from the initial GPT-6 Astra extra-high review unchanged. See `results/review_study/HUMAN_VERIFICATION.json` and `arnav_verified_summary.json` for the two-stage provenance and human-verified agreement. The authorized 30-message Gemini comparison is complete under `results/routing_dev/`; reproduce its saved predictions and 71 receipts with `python analysis_tools/reproduce_routing_comparison.py`. This remains development evidence; production routing is unchanged.

## Final submission artifacts

Start with the [six-page PDF](../output/pdf/Cadence-Arnav-Bule-Report.pdf), then [balanced acceptance](BALANCED_ACCEPTANCE.md) and the earlier [quality acceptance](QUALITY_ACCEPTANCE.md). `python analysis_tools/reproduce_quality.py` checks the quality development and confirmation runs without model calls. All new quality ratings are AI-authored; the completed Arnav verification remains scoped to the earlier 100 ratings. The demo remains on the reference agent.

For the earlier Balanced coverage/safety follow-up, read [balanced acceptance](BALANCED_ACCEPTANCE.md) and run `python analysis_tools/reproduce_balanced.py`. This validates the 80-case comparison, full blind-review context, per-call cache observations and every promotion gate. Pass `--experiment results/balanced_dev`, `balanced_dev_v2` or `balanced_dev_v3` with the full `results/` prefix to inspect retained development runs. `python analysis_tools/publish_balanced.py --check` ensures the report and dashboard use the same results. The new labels and ratings are AI-authored.

## Latest experimental follow-up: VerifiedAgent

Start with [Verified empirical status](VERIFIED_STATUS.md) for the latest completed runs, their measured results and unfinished evidence. [Design](VERIFIED_DESIGN.md) describes the implemented request-first risk decision, executable action prerequisites, expiring current sources and bounded execution. Those mechanisms and their tests do not by themselves establish useful coverage or safety.

The completed development v4 and calibration v1 pilots found 22/80 and 22/100 policy-compliant useful automatic replies, respectively. Each missed two required routes; four development and six calibration automatic replies were flagged. Calibration's two misses were legal/safety routes. Labels and exact-reply reviews are AI-authored. These pre-patch results fail the safety criteria and must not be attributed to the subsequent policy/action-scope patch or knowledge v3.

The later patch completed an 18-case selected regression with 18 successful requests, four automatic replies, no missed required routes and no flagged automatic replies. Its independent blinded AI review found **only one useful clarification and seven unnecessary escalations**. Treat it as evidence on specific repaired boundaries, not restored useful coverage or generalization. See the [sealed regression summary](../results/verified_postpilot_regression_v1/summary.json); final human confirmation remains pending.

The [variant findings](VERIFIED_VARIANT_FINDINGS.md) use one joint 84-reply review on 21 selected messages. [Controls](VERIFIED_ABLATIONS.md) and [retrieval findings](VERIFIED_RETRIEVAL_FINDINGS.md) are development diagnostics. AI reviewers assigned different scores to identical outputs in separate studies; compare within a matched review study and retain that reviewer limitation.

The new 200-message representative confirmation and 80-case synthetic challenge still have untouched, blank human-label packets; neither has completed independent human labeling or inference. Previous human attestations apply only to their named historical artifacts. Development, calibration and selected regression observations cannot replace final confirmation or blinded human reply review.

Use the [evaluation workflow](VERIFIED_EVALUATION.md) for fresh run names and required reserved-sample flags, and [ablation guide](VERIFIED_ABLATIONS.md) for offline diagnostic controls. Read-only verification of an existing sealed run uses `python analysis_tools/reproduce_verified.py --experiment PATH_TO_RUN --action verify`; use the path and any matching-source requirements recorded in [Verified status](VERIFIED_STATUS.md). Preparing a new run or review packet is a separate operation.

VerifiedAgent and prospective policy v2 remain experimental. The reference `SupportAgent` is still the application default and hosted demo agent. No promotion or submission-form action follows from these tools.
