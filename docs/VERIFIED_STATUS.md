# VerifiedAgent implementation and evidence

**18 September 2026. Experimental candidate; the hosted demo and application default
still use `SupportAgent`.** The completed development and calibration pilots have
useful automatic replies but fail the zero-miss and zero-flagged-reply criteria.
A subsequent patch completed a targeted 18-case regression with no route misses
or flagged automatic replies, but only one useful clarification and seven
unnecessary escalations. It has no new generalization result. Promotion remains
false. New AI labels and reviews do not extend Arnav Bule's
earlier attestations. The 200-case confirmation and 80-case challenge human-label
packets remain untouched and blank.

## Completed pilots before the latest patch

These two studies ran the same combined candidate before the post-pilot policy,
action-scope and knowledge-v3 changes. Their frozen outputs and reviews remain
unchanged. Useful coverage means a successful automatic reply, a policy label
that permits automation, and a qualifying exact-reply rating.

| Measure | Development v4 | Calibration v1 |
|---|---:|---:|
| Messages / successful invocations | 80 / 80 | 100 / 100 |
| Automatic replies | 31/80 | 33/100 |
| Policy-compliant useful replies | 22/80 | 22/100 |
| Useful resolutions / necessary clarifications | 15 / 7 | 12 / 10 |
| Missed required routes | 2/28 | 2/31 |
| Flagged automatic replies | 4/31 | 6/33 |
| Failed invocations | 0 | 0 |
| Retry-inclusive p95 | 5.685 s | 5.281 s |
| Known tokens / request | 4,347 | 4,353 |

Sources: [development summary](../results/verified_dev_v4/summary.json) and
[calibration summary](../results/verified_calibration_v1/summary.json). Labels and
reply reviews are **AI-authored**, not independent human ground truth. Both runs
used fresh requests with no unknown usage recorded. They are single-candidate
pilots, not fresh matched comparisons against all historical systems.

The two development misses are insufficiently specified music requests receiving
a catalog question. Both calibration misses are in the legal/safety category:
all two required routes in that small category were missed. The calibration review
flagged six automatic replies for wrong-issue content; one also had a stale-procedure
flag. Flags overlap, so this is six defective automatic replies, not seven. All
four flagged development replies had wrong-issue defects.

These findings remain failures of the measured candidate. They cannot be removed
by relabeling its known errors or transferred to the later patch. Calibration was
labelled before its inference, but its now-inspected outcomes are development
evidence for any subsequent repair. Neither pilot establishes a safe release or
performance on modern support traffic.

## Implemented

- Preserved exact historical experiment inputs and added archive-aware replay.
- Added prospective policy v2 and a customer-only request/risk extraction stage.
  Established mandatory risks cannot be cleared by a later answer selection.
- Added typed action prerequisites, quote-backed known facts, precise questions,
  bounded social acknowledgment and validated handoffs. Both primary and fallback
  replies must satisfy the same contracts.
- Added current official Spotify claims with snapshots, scope, verification dates
  and expiry. The completed pilots used knowledge v2: 26 claims and 21 snapshots.
  The post-pilot v3 registry has 27 claims from the same 21 snapshots and is evaluated
  separately below. Historical examples do not authorize current procedures.
- Added exact-text assessment of every eligible alternative, bounded reselection,
  a shared request deadline and retry budget, and complete failure/usage accounting.
- Added immutable experiment/review records, matched-message metrics, controlled
  ablations, operational fault injection, reserved-sample exclusions and explicit
  human-label gates. Automated summaries cannot deploy a candidate.

See [design](VERIFIED_DESIGN.md), [policy](POLICY_V2.md),
[evaluation protocol](VERIFIED_EVALUATION.md) and
[the fixed experiment sequence](VERIFIED_EXPERIMENT_SEQUENCE.md).

## Earlier development comparison

The first completed candidate, `results/verified_dev_v2`, generated all 80 outputs
successfully. Fresh blinded AI review used the same prospective policy labels and
rubric across its outputs and the three archived comparators:

| Measure / 80 messages | Reference | Quality | Balanced | Initial Verified |
|---|---:|---:|---:|---:|
| Automatic replies | 28 | 7 | 30 | 27 |
| Policy-compliant useful replies | 8 | 7 | 20 | 22 |
| Missed escalations / 28 required | 2 | 0 | 2 | 3 |
| Flagged automatic replies | 17 | 0 | 7 | 4 |

The initial candidate's useful-coverage difference from Balanced was +2.5
percentage points, with a paired 95% bootstrap interval of approximately
[-6.28, +12.50] points: **inconclusive**. These are inspected development cases,
AI labels and AI reply judgments. Archived comparator outputs were reused;
runtime observations are not a fresh randomized four-system comparison.
The new policy and rubric differ from the earlier published study. Its original
scores remain unchanged and must not be substituted into this table.

The interrupted `verified_dev` and `verified_dev_v3` runs retain their partial
records and unknown in-flight work. They do not support complete-run metrics.
The [routing diagnosis](VERIFIED_ROUTING_DIAGNOSIS.md) explains the first
candidate's defects and the general contract fixes that followed.

### Veto-only controls and reviewer variation

A separate blinded review of the four archived-output controls found 13 useful
replies for unchanged Balanced, 11 after a policy veto, nine after a prerequisite
veto and seven after both. Their missed escalation counts were 2, 0, 1 and 0;
flagged automatic counts were 8, 7, 0 and 0. Adding rejection rules can prevent
errors while losing useful replies. It does not by itself recover missing answers.
See [control quality evidence](../results/verified_ablation_v1/quality_summary.json).

The unchanged Balanced outputs received 20 useful judgments in the earlier common
comparison and 13 in this separate controls review, despite the same 80 customer
texts, replies, evidence and rubric. This exposes material AI reviewer variation.
Use within-study comparisons; do not mix their absolute scores or interpret
message-bootstrap intervals as covering judge uncertainty. Within-study results
remain conditional on that study's reviewer and rubric; blinding does not make
AI ratings error-free or equivalent to human verification.

## Variant comparison

The four variants were rated together in one joint blinded **84-reply** packet:
the same 21 deliberately selected development messages for every arm. Combined,
core and full-context each received three policy-compliant useful judgments;
no-history received four. Required-route misses were respectively 1, 0, 2 and 1.
Full-context also had one failed request and one flagged automatic reply; the other
arms had neither. These findings do not establish a winning variant or a population
gain. No-history's extra useful clarification does not cancel its route miss.

The combined arm's earlier full-run review is preserved separately. Use only the
joint packet for this comparison, rather than combining scores from different
reviewers. See [variant findings](VERIFIED_VARIANT_FINDINGS.md) for matched counts,
tokens, latency, uncertainty and reproduction.

## Retrieval decision

Keep raw-text BM25 for now. On 20 frozen development messages, top-three
diagnostic hits were 9/20 for raw queries, 9/20 for request-frame queries and
6/20 after token reranking. Action-support hits were 6/20, 6/20 and 3/20.
Later conversation views sometimes supplied useful context, but that comparison
does not isolate the final reply or demonstrate a successful resolution.
See the [reviewed retrieval findings](VERIFIED_RETRIEVAL_FINDINGS.md).

## Post-pilot patch: targeted regression complete

The calibration misses and independent contrast tests motivated a separate patch
for harm language, churn/security object scope and action applicability. The
[supplemental policy review](../output/analysis/VERIFIED_POLICY_RESIDUAL_LIMITATIONS.json)
records the earlier over-routing findings. A new explicit
[knowledge v3 registry](../config/knowledge/v3.json) contains 27 claims backed by
21 preserved snapshots; it does not revise the v2 knowledge frozen into the pilots.

The patch completed a new frozen run on **18 selected development cases**: six
previously inspected calibration cases and 12 synthetic contrasts. All labels are
AI-authored. Independent blinded Astra xhigh review rated all 18 exact replies;
the submitted ratings were imported unchanged.

| Targeted regression measure | Result |
|---|---:|
| Successful / failed requests | 18 / 0 |
| Automatic / escalated replies | 4 / 14 |
| Missed required routes | 0/7 |
| Flagged automatic replies | 0/4 |
| Policy-compliant useful replies | **1/18** |
| Useful resolutions / necessary clarifications | **0 / 1** |
| Gold-eligible cases still escalated | **7/11** |
| Known tokens | 73,901 |
| Retry-inclusive p95 | 4.898 s |

Source: [sealed regression summary](../results/verified_postpilot_regression_v1/summary.json),
[AI review seal](../results/verified_postpilot_regression_v1/AI_REVIEW.json) and
[selection/provenance](../data/verified_postpilot_regression/README.md). The four
automatic replies are not four useful replies: only one met the full usefulness
rubric. Seven unnecessary escalations means seven messages whose gold labels
permitted automation still received a handoff; it does not prove that a supported
automatic answer was available for every one.

The selected run demonstrates behavior on these specific boundaries. It does
**not** establish restored useful coverage, generalization, or a better safety/
coverage tradeoff across ordinary traffic. Zero observed errors on seven required
routes and four automatic replies does not establish a zero population error rate.
The earlier full-run failures remain visible above, and the new 200-case human
confirmation and 80-case human-reviewed challenge remain pending.

Independent implementation reviews accepted the bounded
[policy fixes](../output/analysis/VERIFIED_POSTPILOT_POLICY_ACCEPTANCE.json),
[action contracts](../output/analysis/POSTPILOT_ACTION_ACCEPTANCE.json),
[knowledge v3](../output/analysis/KNOWLEDGE_V3_ACCEPTANCE.json) and
[explicit registry selection](../output/analysis/VERIFIED_REGISTRY_SELECTION_ACCEPTANCE.json).
Code acceptance and this regression do not grant candidate release acceptance.
The summary remains ineligible for release review with `promote: false`; deployment
still uses `SupportAgent`.

## Human work and release gates

- The 100-case calibration pilot and its independent **AI** reply review are complete.
  Its labels remain AI-authored and its failures remain recorded.
- The 200 representative cases and 80 challenge cases have prepared, blank
  human annotation packets. No inference has been run on those sets.
- A human must complete their labels before scored inference. Final comparisons
  then require all four systems, blinded reply review and the prespecified human
  reply-rating subset. Existing verification of earlier scores is preserved.
- A zero-error sample still needs uncertainty bounds; none of these studies
  proves reliability for every possible customer request.

The [annotation guide](../data/verified_sampling/README.md) links the actual
packets and validation commands. Form submission remains excluded.

## Verify the saved evidence

These read-only commands reproduce the completed pilots and diagnostic summaries
without model calls. They do not run the post-pilot patch or grant release approval.

```powershell
python analysis_tools/reproduce_verified.py --experiment results/verified_dev_v4 --action verify
python analysis_tools/reproduce_verified.py --experiment results/verified_calibration_v1 --action verify
python analysis_tools/reproduce_verified.py --experiment results/verified_postpilot_regression_v1 --action verify
python analysis_tools/compare_verified_variants.py --check
python analysis_tools/summarize_verified_controls.py --experiment results/verified_ablation_v1 --check
python analysis_tools/summarize_verified_retrieval.py --check
```
