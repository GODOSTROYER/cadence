# Comparing Verified with archived alternatives

This helper performs a **development content comparison** on the 80 previously inspected `b4_*` messages. It joins a completed Verified run to the original reference, Quality and Balanced replies without rerunning or changing them. All four arms receive new AI ratings under the same `verified-support-review-v1` rubric and the same current official source snapshots.

This comparison cannot establish an unseen improvement, independent human agreement, or a controlled latency/cost gain. The old agents ran under policy v0; measuring their saved decisions against new AI-authored v2 labels does not show how a rewritten old agent would behave. Their historical v0 results remain unchanged and separately linked.

See [Verified empirical status](VERIFIED_STATUS.md) for the latest measured results and remaining evidence. VerifiedAgent and policy v2 are not deployed or promoted; the reference `SupportAgent` remains the default. New ratings do not inherit historical human attestations.

## Verify the existing comparison

The retained comparison is already prepared, rated and summarized. Verify it without model calls or new review artifacts:

```powershell
python analysis_tools/compare_verified_development.py verify --out results/verified_development_comparison
```

## Workflow

For a new study, run from the repository root after the candidate's full 80-message execution is sealed. `results/verified_dev_v2` is a completed source run; the example output name below must be unused. Pick another unused name on subsequent studies, and select a later completed candidate run when that is the intended comparison.

```powershell
$Comparison = "results/verified_development_comparison_example_20260918_01"
python analysis_tools/compare_verified_development.py prepare --candidate-dir results/verified_dev_v2 --out $Comparison
```

Preparation verifies both source studies through their existing offline validators and freezes labels, source provenance, exact replies, runtime records, rubric, policy, taxonomy, current source snapshots, and evaluator versions. It refuses partial runs and mismatched customer context. Existing comparison directories cannot be overwritten. Hashes use the repository's LF-normalized text convention, so Windows/Linux checkouts reproduce identically.

Give an independent reviewer only `REVIEW_INSTRUCTIONS.json`, `rubric.json`, `blind_packet.jsonl`, and `context/config/knowledge/`. Do not give the reviewer labels, mappings, previous ratings, source run summaries or agent implementation. Aliases are randomized separately for each message; reply style and evidence may still reveal architecture. Each produced reply, including a safe fallback from a failed invocation, needs a new rating. Failure status remains in metrics regardless of how its visible text is rated.

Reviewers provide one JSONL object per exact packet item, retaining `id`, `alias`, `run_id`, `reply_hash`, and `rubric_version`, and adding:

- `reviewer_type: "ai"`, explicit `reviewer_id`, and timezone-aware `rated_at`.
- Integer scores 1–5 for `grounded`, `resolves`, `tone`, `safe`, and `overall`.
- Explicit booleans for all seven rubric flags.
- `verdict`, `response_kind`, `severity`, and a substantive `rationale`.

Separate batches may be reviewed independently. Import all batches together; the validator requires exactly one rating per produced reply and rejects old rubric versions, incomplete flags, changed reply hashes, missing ratings, duplicates, or human attribution.

```powershell
python analysis_tools/compare_verified_development.py import --out $Comparison --ratings path/to/batch1.jsonl path/to/batch2.jsonl
python analysis_tools/compare_verified_development.py summarize --out $Comparison
python analysis_tools/compare_verified_development.py verify --out $Comparison
```

Every command is offline. No previous reply scores or flags are converted into new ratings. Original external submissions are retained alongside the mapped AI ratings. Imports and summaries are immutable; later adjudication needs a separately named study.

## Reading the result

The primary metric counts replies that are automatic, useful under the new rubric, and eligible under policy v2. It excludes useful-sounding answers on mandatory-human requests. Failures stay in the full message denominator and count as missed required routes where applicable. Paired uncertainty resamples the same messages across systems.

`runtime.verified_new_run` and `runtime.archived_original_runs` retain their separate measurement schemas. The new run records retry-inclusive observations, cache status and unknown provider usage; the archives recorded successful-call totals with earlier instrumentation. A new run is not necessarily fully fresh. Do not compute a causal speed or token improvement from these fields. `historical_v0` points to the unchanged original results.

`human_agreement` remains null, `human_review_pending` remains true, and `promote` is always false. These new ratings are AI review even when earlier studies had a separate human attestation. Final release evidence belongs in the prospective, human-labelled confirmation workflow described in `VERIFIED_EVALUATION.md`.
