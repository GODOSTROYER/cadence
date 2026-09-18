# Quality repairs, confirmation and acceptance

## Outcome

All implementation, AI review and fresh-confirmation work is complete. **Keep the deployed reference. Candidate promotion gates are not all met.** Completing an evaluation does not require promoting a candidate that fails its gates. The hosted demo continues with the existing reference agent. Form submission is intentionally untouched.

## What changed

The candidate routes from customer text before retrieval. It selects from a finite set of approved response actions, rendered by the server with fixed wording and source IDs, rather than copying arbitrary historical prose. Current official Spotify sources authorize narrow playback procedures and the support-contact route. A separate call using the same Gemini model reviews the exact finalized text for relevance, support, operational claims and a useful next step. Rules, primary/secondary safety defaults and the 0.90 threshold retain precedence.

This addresses unsupported action promises and stale procedure copying structurally. It reduces, but cannot prove elimination of, wrong-issue action selection and unnecessary handoffs. Historical conversations remain context for relevant diagnostic patterns; they are not present-day policy authority. Current-source checks are dated 17 September 2026: [playback](https://support.spotify.com/us/article/spotify-not-playing/), [reinstall](https://support.spotify.com/us/article/reinstall-spotify/), [contact](https://support.spotify.com/us/article/contact-us/).

## Controlled results

| Sample | System | Escalation recall | Misses | Automatic | Useful automatic | Tokens | p95 |
|---|---|---:|---:|---:|---:|---:|---:|
| Development (30) | agent | 85.7% | 2 | 9/30 | 2/30 | 77,277 | 1.85s |
| Development (30) | quality | 100.0% | 0 | 1/30 | 1/30 | 71,633 | 6.36s |
| Confirmation (60) | agent | 87.9% | 4 | 22/60 | 3/60 | 154,379 | 3.53s |
| Confirmation (60) | quality | 100.0% | 0 | 4/60 | 4/60 | 150,347 | 6.33s |

Useful automatic coverage requires `ship`, safety/grounding/resolves scores >=4, no flags, and a resolution or necessary clarification. All messages are the denominator. A useful question is reported separately from completed resolution; a handoff is never counted as automatic resolution. New labels and quality reviews are AI-authored. Timings are local successful-prediction observations including waits/retries within a completed invocation, not a production SLA. The interrupted v2 development run separately documents omitted time from its aborted invocation.

The earlier routing-only experiment also has completed review of all 90 replies and 276 evidence rows: useful automatic coverage was **2/30 for the reference, 1/30 for selective routing, and 2/30 for the trained baseline**. Its routing improvement did not translate to better useful coverage.

## Fresh confirmation and provenance

Sixty cases were sampled using a fixed seed, excluding all prior candidate, golden, taxonomy, frozen-benchmark and development cases, overlapping conversations and >=85% fuzzy matches. GPT-6 Astra at extra-high reasoning labelled customer text before inference: 33 required escalation. Source fields, labels, corpus, policy, threshold and code are hash-bound. The final candidate was frozen before any confirmation predictions; confirmation findings were not used to tune it.

All 120 confirmation replies were reviewed by a separate GPT-6 Astra extra-high reviewer with system names, decisions, labels and previous scores hidden. Evidence content may reveal implementation clues, so blinding is not absolute. Exact reply hashes bind ratings to outputs. The original 100 Astra ratings verified unchanged by Arnav Bule remain complete and unchanged; **that human verification does not extend to these newly generated replies or labels**.

## Acceptance decision

- **PASS**: `no_more_missed_escalations`
- **PASS**: `strictly_better_useful_coverage`
- **PASS**: `no_reviewer_flagged_unsafe_automatic`
- **PASS**: `candidate_p95_under_15_seconds`
- **NOT MET**: `new_reply_reviews_verified_by_human`

Implementation acceptance independently verified all approved actions, final-text checking, routing precedence, input locks and review preservation: 24 unit tests and 12 additional reviewer checks. Report/content acceptance is recorded in `results/acceptance/release.json`. Promotion requires every frozen gate; AI review cannot satisfy the new-human-verification gate.

Development iterations remain available: `quality_dev` was rejected for zero automatic coverage caused by omitted optional citations; `quality_dev_v2` was rejected after an unsupported operational paraphrase passed its model check; `quality_dev_v3` replaces free wording with approved actions. V1/v2 were not fully quality-rated, and are not represented as such. Their results and exact Python source snapshots remain archived. A confirmation preflight for v1 was stopped before any calls; its manifest remains preserved.

## Reproduce and inspect

```sh
python analysis_tools/reproduce_routing_comparison.py
python analysis_tools/reproduce_quality.py
python scripts/15_publish_benchmark.py --check
python analysis_tools/publish_quality.py --check
```

These are offline evidence checks with zero model calls. Receipt keys, prediction/token totals, paired comparisons, exact review identities and acceptance decisions are recomputed. Current source is in `src/cadence/agent/quality.py`; frozen source snapshots sit beside each run. Artifacts: `results/routing_dev/astra_*`, `results/quality_dev_v3/`, and `results/quality_confirmation/`.

The six-page report is `output/pdf/Cadence-Arnav-Bule-Report.pdf`. Rebuild with `python analysis_tools/build_submission_report.py` after installing optional `reportlab` and `fonttools`. Fonts and artwork provenance are in `docs/report_assets/README.md`. The report is visually checked page by page; submission through the Hiver form remains the author's action.
