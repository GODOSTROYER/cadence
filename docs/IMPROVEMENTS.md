# Evaluation and routing improvements

## What is implemented

- **One published benchmark:** Overview and Evaluation default to the revised frozen 200-message, four-system comparison. Historical charts remain available explicitly. The report table and public JSON come from the same frozen summary; CI checks both for drift. The live deployment commit and frozen execution commit are shown separately.
- **Identity-bound review:** matched messages across systems, named reviewers, exact reply SHA-256, run and rubric identity, both judge orders, revision handling, per-reviewer/order statistics, human–human comparisons and judge ship decisions on reviewer-unsafe replies. Constant ratings leave κ undefined while retaining raw agreement.
- **Release checks:** regression cases cover invented actions, obsolete numeric limits, unsafe/private handoffs and citation problems. Semantic challenges for wrong-issue replies with valid citations, nonnumeric stale advice, retrieval injection and clarification are listed separately in `tests/fixtures/release_challenges.json`; they are not claims of solved semantic detection.
- **Learned baseline:** TF-IDF plus logistic regression fitted only on designated training messages. Evaluation labels and vocabulary cannot enter fitting. Split checks reject duplicate IDs/threads and near-duplicate train/dev messages.
- **Controlled routing experiment:** the existing agent is compared with customer-message-first routing, then selective retrieval and drafting. Both use the same model, policy and 0.9 threshold. Escalated cases retain their intent and skip retrieval/drafting. Source/input hashes prevent resuming with changed code. The new path is experimental and has not replaced production routing.
- **Operational measurements:** experiment artifacts record paired differences, confidence bins, p50/p95 latency, cache status, token totals and model-call counts. Retrieval review and useful automatic coverage tools require explicit reviewer judgments; useful clarification is counted separately from resolution. Coverage uses all messages as its denominator.

## Astra review: completed, pending author review

At the author's request, **GPT-6 Astra at extra-high reasoning effort** reviewed a seeded sample of 50 frozen messages, each with both agent and keyword-baseline replies: **100 ratings, not 100 independent messages**. System names, judge scores and gold labels were excluded from the review packet. The packet includes the customer message, exact reply and retrieved evidence.

The review produced **6 ship, 35 edit and 59 reject** verdicts. These are **AI-authored provisional ratings**, stored separately from the original benchmark and Arnav Bule's completed approval of the existing 200 examples/scores. They do not establish new independent human–judge agreement. The supplemental report therefore leaves `human_agreement` null until a person supplies ratings. Arnav's later review should be a separate named record; preserve the Astra rows.

Files: `results/review_study/blind_packet.jsonl`, `mapping.json`, `rubric.md`, `astra_ratings.jsonl`, `astra_review_notes.md`, and `astra_summary.json`. The supplemental rubric explicitly treats 2017 advice as historical and distinguishes safe holding replies from resolution. The original judge used its original prompt and normalized reply presentation: this comparison is a rubric audit, not two interchangeable measurements under an identical protocol. Top-level agreement pools rating/order observations; use `per_reviewer_order` for separate estimates.

```sh
python scripts/17_prepare_review_study.py --check
python scripts/14_review_study.py --ratings results/review_study/astra_ratings.jsonl --out results/review_study/astra_summary.json
python scripts/15_publish_benchmark.py --check
```

### Human review workflow

Run the local API and non-static UI, open `/rate`, enter your reviewer name, and score the replies. The revised queue contains the same 20 messages for both systems (40 ratings per reviewer). It is a separate sample from Astra's 50-message study. The hosted static rating screen is a preview. Local records are appended to `data/golden/human_ratings.jsonl` with exact identities and a response kind.

```sh
python scripts/14_review_study.py --api-ratings --ratings data/golden/human_ratings.jsonl --out results/review_study/human_summary.json
```

For the 50-message study, use its blind packet and rubric, with one JSONL rating per `(id, alias)`. Preserve `run_id`, `reply_hash` and `rubric_version` from the mapping. Supply `reviewer_id`, `reviewer_type: human`, an ISO timestamp in `rated_at`, five integer scores, three Boolean flags, verdict, rationale and `response_kind` (`resolution`, `clarification`, `handoff`, `other`). Run script 14 without `--api-ratings`. Later revisions need a later timestamp; ambiguous duplicate revisions are rejected. Do not copy Astra's ratings under a human name before reviewing them.

## Development experiment

`data/routing_dev/` contains 30 new development messages and pre-prediction **AI labels by Astra**. Sampling excludes previously inspected candidate, golden, taxonomy-calibration and final-benchmark messages/threads, and rejects ≥85% fuzzy similarity to those texts and within the sample. This is exploratory development data, not a final generalization benchmark. Historical 250-example labels are now explicitly designated training data for the learned baseline.

```sh
# Offline baseline only; zero model calls
python scripts/16_routing_experiment.py --baseline-only

# Requires authorization to send this batch to Gemini; at most 90 logical model calls,
# with additional transport attempts possible under the existing bounded retry policy.
python scripts/16_routing_experiment.py --live-free-tier
```

**Live experiment status:** pending authorization. Current and selective Gemini variants have not run on this batch, so no comparative improvement is claimed. Credentials and external execution are required to measure them. Failed or interrupted runs retain receipts, partial predictions and status; unchanged inputs can resume. Use a new output directory after changing any frozen source or input.

The offline learned baseline completed all 30 messages: intent accuracy **0.567**, macro-F1 **0.331** across the fixed 12-intent taxonomy, escalation recall **0.286**, and automatic coverage **0.800** (10 missed required escalations). These small-sample results use the disclosed AI labels and are not a replacement for the frozen benchmark. Macro-F1 includes zero-support classes under the fixed taxonomy. Artifacts are in `results/routing_dev/`; source hashes were verified after execution.

After a complete run, review every exact reply and the exported `retrieval_review.csv`. Script 18 accepts the same rating schema; use system IDs as aliases and `routing_dev-` plus the first 12 characters of the manifest's logical-content SHA-256 as `run_id`. It reports AI and human reviewers separately and rejects incomplete reply coverage or mismatched evidence. Retrieval fields accept literal `true`/`false`.

```sh
python scripts/18_review_coverage.py --reply-reviews path/to/reviews.jsonl --retrieval-reviews results/routing_dev/retrieval_review.csv --out results/routing_dev/reviewed_coverage.json
```

Promotion requires reviewed usefulness and a new confirmation set. The frozen benchmark, existing review attribution and deployed routing remain the reference until those measurements exist.
