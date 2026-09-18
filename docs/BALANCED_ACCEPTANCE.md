# Balanced candidate: measured coverage and safety

The previous quality candidate reduced missed escalations but sacrificed automatic coverage. This follow-up compares the unchanged reference, QualityAgent and BalancedAgent on the same messages.

## Fresh confirmation

80 new messages, labelled by an independent GPT-6 Astra extra-high reviewer before inference. All three replies per message received a separate, blinded Astra review. These are AI assessments; small samples do not establish general safety.

| System | Automatic | Useful automatic | Resolution-style replies | Missed escalations | Flagged auto | p95 | Tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| Reference | 28/80 | 6/80 | 0 | 4 | 15 | 4.06 s | 205,542 |
| Quality candidate | 7/80 | 6/80 | 1 | 0 | 0 | 4.53 s | 199,047 |
| Balanced candidate | 30/80 | 13/80 | 11 | 4 | 4 | 3.86 s | 386,582 |

**Useful automatic** requires ship, grounding/safety/next-step scores of at least 4, no review flags, and a resolution or necessary clarification. Handoffs and social acknowledgments are excluded. Reviewer-rated resolution-style replies are reported separately from clarifications; these are not observed ticket closures. Missed escalations are measured against the independently frozen routing labels, even if the reply itself looks harmless.

Latency covers successful end-to-end predictions. Every recorded model call for these predictions was fresh. The run stopped after 194 predictions and resumed for 46 more; receipt dates are 2026-09-17, 2026-09-18 (UTC). Failed or aborted attempts and interruption time are excluded; this is not a production traffic or availability benchmark. Tokens include every recorded successful model call.

| System | Intent accuracy | Intent macro-F1 | Escalation recall |
|---|---:|---:|---:|
| Reference | 0.787 | 0.751 | 0.895 |
| Quality candidate | 0.775 | 0.715 | 1.000 |
| Balanced candidate | 0.812 | 0.762 | 0.895 |

Paired bootstrap intervals and disagreement tests for routing/classification are retained in the full `summary.json`. Counts and point estimates here are descriptive, not proof of a population-wide gain.

## Fixed acceptance gates

| Gate | Result |
|---|---|
| no more misses than either | FAIL |
| strictly better useful coverage than both | PASS |
| minimum automatic coverage | PASS |
| bounded coverage loss vs reference | PASS |
| no fewer useful resolutions than reference | PASS |
| no reviewer flagged unsafe automatic | FAIL |
| latency within frozen limit | PASS |
| latency observations fully fresh | PASS |
| new reply reviews verified by human | FAIL |

Keep the deployed reference; not all promotion gates are met.

New labels and reply ratings are AI-authored. Arnav Bule verified the earlier 100 ratings; that verification does not cover these new outputs.

## Development history

| Run | Reference auto / useful / misses | Quality auto / useful / misses | Balanced auto / useful / misses | Technical gates |
|---|---|---|---|---|
| balanced_dev (n=30) | 10 / 2 / 2 | 1 / 1 / 0 | 7 / 5 / 3 | FAIL |
| balanced_dev_v2 (n=30) | 13 / 3 / 3 | 1 / 1 / 0 | 8 / 7 / 2 | FAIL |
| balanced_dev_v3 (n=30) | 10 / 2 / 2 | 1 / 1 / 0 | 8 / 8 / 0 | PASS |

Development examples were inspected and used to revise the candidate. Their scores are regression evidence. The confirmation sample excluded previous sampled cases, overlapping conversations and near-duplicates; the chosen code was frozen before confirmation inference. No tuning follows those results.

See [design and current-source references](BALANCED_DESIGN.md), the exact [confirmation acceptance](../results/balanced_confirmation/ACCEPTANCE.json), and [prior quality experiment](QUALITY_ACCEPTANCE.md).

## Reproduce without API calls

```bash
python analysis_tools/reproduce_balanced.py --experiment results/balanced_dev
python analysis_tools/reproduce_balanced.py --experiment results/balanced_dev_v2
python analysis_tools/reproduce_balanced.py --experiment results/balanced_dev_v3
python analysis_tools/reproduce_balanced.py --experiment results/balanced_confirmation
python analysis_tools/publish_balanced.py --check
```

The verifier binds source snapshots, labels, receipts, paired metrics, runtime, complete blind review context, scores and acceptance gates. Offline verification makes zero model calls.
