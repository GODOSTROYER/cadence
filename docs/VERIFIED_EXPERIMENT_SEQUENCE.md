# Frozen experiment sequence and completed pilots

The original sequence below was recorded on 18 September 2026, after independent
code acceptance and before the revised 80-case run completed or calibration
inference began. Steps 1–3 are now complete. Their pre-patch evidence remains
frozen; the subsequent patch is a separate development step.

## Original sequence

1. `results/verified_dev_v4`: all 80 inspected development messages, combined
   candidate, unchanged policy-v2 AI labels. Independently review every exact reply.
2. On the 21 inspected IDs recorded in
   `data/verified_dev/V3_REGRESSION_SELECTION.json`, run `core`, `full_context` and
   `no_history` with the same accepted source, policy and knowledge. The matching
   combined outputs come from step 1. These deliberately difficult cases diagnose
   action coverage and evidence costs; they do not estimate population performance.
3. `results/verified_calibration_v1`: the combined candidate on all 100 reserved
   real messages, using independently frozen AI labels. Independently review all
   exact replies. Combined is selected for this pilot before variant ratings are
   available; no variant is promoted based on a small favorable slice.
4. Keep the new 200-case representative sample and 80-case challenge suite unused
   for inference until the required human labels have been entered and validated.
   Their final comparisons require all four systems and the planned human reply
   review. The pilot cannot substitute for those gates.

The initial complete candidate is `verified_dev_v2`. `verified_dev` records an
interrupted network failure; `verified_dev_v3` was deliberately stopped after
independent code review identified additional contract defects. Each interruption
record preserves attempted work and any unknown in-flight completion/usage.
Neither partial run supports an aggregate quality result.

All live study runs use separate caches, fixed source dates, reserved-sample
retrieval exclusions, bounded requests and saved provider receipts. The original
sequence required unchanged runtime sources across these candidate runs. Newly
discovered defects remain failures of that measured candidate; material fixes
require a new frozen study rather than rewriting its results.

## Completed outcomes before the post-pilot patch

| Study | Successful requests | Automatic | Policy-compliant useful | Missed required routes | Flagged automatic |
|---|---:|---:|---:|---:|---:|
| Development v4 | 80/80 | 31 | 22 (15 resolution / 7 clarification) | 2/28 | 4 |
| Calibration v1 | 100/100 | 33 | 22 (12 resolution / 10 clarification) | 2/31 | 6 |

Calibration's misses were both legal/safety cases. Its six flagged automatic
replies all had wrong-issue defects; one also had a stale-procedure flag. Both
studies fail the zero-miss and zero-flagged-automatic criteria. They are AI-labelled,
AI-reviewed single-candidate pilots, not final matched human confirmation.

The variants were compared in one joint blinded 84-reply packet on the 21 selected
messages: combined/core/full-context each had three useful replies; no-history
had four. No variant is established as superior by that selected diagnostic.
Separate AI reviews also assigned different useful counts to identical Balanced
outputs, so absolute scores from different studies must not be mixed. See
[status](VERIFIED_STATUS.md), [variant findings](VERIFIED_VARIANT_FINDINGS.md) and
[retrieval findings](VERIFIED_RETRIEVAL_FINDINGS.md) for full evidence and limitations.

## Post-pilot patch and regression

The completed pilot exposed harm-language misses and action-scope defects;
independent contrast checks also exposed churn/security over-routing. A separate
patch addresses those boundaries and introduces explicit knowledge v3 with 27
claims backed by 21 preserved snapshots. The completed studies retain their
original code and knowledge-v2 inputs.

The patch's frozen [18-case regression](../results/verified_postpilot_regression_v1/summary.json)
is complete: 18 successful requests, four automatic replies, zero missed routes
among seven required, and zero flagged automatic replies. Independent blinded AI
review of all 18 exact outputs found **one useful clarification, no useful
resolution, and seven gold-eligible cases still escalated**. Known usage was
73,901 tokens and retry-inclusive p95 was 4.898 seconds.

Its six reused calibration cases and 12 synthetic contrasts were deliberately
selected. The result supports specific boundary checks, not restored useful
coverage or fresh generalization. It cannot replace the unchanged full-run
failures or the untouched 200-case confirmation and 80-case challenge. Those
human-label packets remain blank and neither set has been used for inference.
Implementation acceptance does not imply release acceptance; promotion remains false.

New labels and reviews are AI work. Arnav Bule's earlier verification remains
attached only to the earlier artifacts he reviewed. No deployment promotion or
form submission is authorized by an automatic study summary.

## Reproduce the sealed sequence

Use `python analysis_tools/verify_portable_summaries.py verified --experiment results/verified_dev_v4`
for step 1; use the same command with `results/verified_calibration_v1` or
`results/verified_postpilot_regression_v1` for the other completed candidate runs.
Use `python analysis_tools/verify_portable_summaries.py variants` for the joint
variant comparison. The [complete command list](VERIFIED_STATUS.md#verify-the-saved-evidence)
also covers the earlier development comparison and controls.

This read-only wrapper leaves frozen evidence unchanged. It allows only finite
float-to-float summary differences up to `1e-12` absolute, with no relative
tolerance; counts, types, keys, provenance and artifact hashes remain exact.
