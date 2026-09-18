# Verified variants: selected development diagnostics

## Findings

On the 21 inspected development cases, combined, core and full-context each produced **3 policy-compliant useful automatic replies**; no-history produced **4**, with one additional useful clarification. Core delivered all five required routes but escalated more cases without a gold-required route. Full-context had one failed request and one flagged automatic reply. These observations do not establish a winning variant or a population gain.

The comparison uses `combined` predictions from the completed 80-message candidate run and `core`, `full_context`, and `no_history` predictions for the same 21 IDs in `V3_REGRESSION_SELECTION.json`. Counts, tokens and latency all use those same 21 requests per arm. Failures remain in the denominator. The subset was selected for development regression diagnosis; it is neither random nor unseen. Human review remains pending. No promotion is authorized.

All compared quality scores come from one joint blinded review of the 84 exact matched replies. Each original run/reply identity is preserved; the combined arm's earlier separate 80-message ratings remain unchanged. This avoids mixing the combined arm's full-run reviewer with a different reviewer for the three variants. The joint review packet was expanded from 63 to 84 replies before variant ratings were completed or revealed; the original packet and seal are retained.

## Quality and routing

The frozen AI labels require escalation for 5 cases and do not require it for 16. Useful coverage requires a successful automatic reply, no gold-required escalation, and a qualifying exact-reply rating. Handoffs and social replies do not count as useful resolution or clarification coverage. Routing failures can occur even when the reply has no content flag.

| Variant | Useful / 21 | Useful resolutions | Useful clarifications | Required-route misses / 5 | Flagged / automatic replies | Failed requests / 21 |
|---|---:|---:|---:|---:|---:|---:|
| Combined | 3 (14.3%) | 1 | 2 | 1 | 0 / 9 | 0 |
| Core | 3 (14.3%) | 1 | 2 | 0 | 0 / 5 | 0 |
| Full context | 3 (14.3%) | 1 | 2 | 2 | 1 / 8 | 1 |
| No history | 4 (19.0%) | 1 | 3 | 1 | 0 / 10 | 0 |

Core escalated 11 of the 16 cases without a gold-required route, compared with 8 for combined, 9 for full-context and 7 for no-history. This counts routing against the labels; it does not establish that every such case had a supported automatic answer available. Full-context's two required-route misses include its failed request. Its one flagged automatic reply received both `wrong_issue` and `repeated_known_question` flags.

### Paired useful-coverage differences

Differences are **combined minus the named variant**. The first two rows have identical useful/not-useful outcomes on every selected case. The intervals resample matched messages 2,000 times with seed `2026091812`.

| Comparison | Combined-only / other-only useful cases | Difference | Descriptive 95% interval |
|---|---:|---:|---:|
| Combined − Core | 0 / 0 | 0.0 pp | [0.0, 0.0] pp |
| Combined − Full context | 0 / 0 | 0.0 pp | [0.0, 0.0] pp |
| Combined − No history | 0 / 1 | −4.8 pp | [−14.3, 0.0] pp |

These intervals condition on the selected cases and exclude AI judgment uncertainty. A zero-width interval reflects identical observed binary outcomes; it does not prove population equivalence. No-history's one additional useful clarification does not establish superiority or remove its required-route miss.

## Tokens and latency on the same 21 requests

| Variant | Known tokens | Known tokens / request | Known tokens / useful reply | P50 / P95 request latency | All calls observed uncached / 21 |
|---|---:|---:|---:|---:|---:|
| Combined | 101,815 | 4,848.3 | 33,938.3 | 3.928 / 5.156 s | 21 |
| Core | 94,694 | 4,509.2 | 31,564.7 | 4.064 / 6.052 s | 21 |
| Full context | 107,539 | 5,120.9 | 35,846.3 | 3.863 / 6.420 s | 21 |
| No history | 94,996 | 4,523.6 | 23,749.0 | 3.826 / 6.194 s | 21 |

Core used 7.0% fewer known tokens than combined on these requests; no-history used 6.7% fewer, while full-context used 5.6% more. Combined had the lowest observed P95 latency. The runs were separate, so provider conditions and generation variability limit causal speed or efficiency claims. Tokens per useful reply also depend strongly on the small AI-rated useful counts.

All four arms have zero observed cached calls, zero unknown cache statuses and zero calls with unknown usage. The uncached column uses `requests_with_all_calls_observed_uncached`; missing cache status and requests with no observed model calls would not establish freshness. Full-context's failed request and all known attempt usage remain included. The JSON preserves input/output token totals, model-call and network-attempt counts, and unknown-usage fields. No currency-cost claim is made.

## Reproduction and boundaries

```powershell
python analysis_tools/compare_verified_variants.py
python analysis_tools/compare_verified_variants.py --check
```

The helper uses `reproduce_verified.py` to validate sealed execution artifacts, exact blinded packets, original AI submissions and unchanged mapped ratings. It requires matching exact customer text and gold labels, source/config and other execution dependency hashes, model, policy, source date, retrieval settings and resource limits. Each 21-message variant also reserves the original unchanged 80-message development file, preserving the combined arm's retrieval exclusions; the helper checks that dependency, the other reserved references and the sealed excluded-thread count. All four runs excluded the same **402 retrieval threads**. The planned generation total is checked per request because the original run sizes differ (80 versus 21). Runtime is recomputed from the selected observations, including caches, retries and failures.

The helper also verifies `BLIND_REVIEW_V2.lock.json` and the joint `AI_REVIEW.json`, requires the complete joint packet to equal the selected original packets, and validates each rating against its original run/reply mapping. One explicit AI reviewer must cover all 84 replies. The saved summary binds its source artifacts, joint review, selection data, helper and evaluator hashes. `--check` repeats verification and requires exact saved-summary equality. No customer/reply text is written into the comparison summary. Reserved samples remain excluded; the existing reproduction validator checks their frozen dependency hashes without interpreting their contents. No model calls, new ratings or promotion occur here.

Generation and `--check` both passed on the sealed actual artifacts. The helper and tests also passed independent code acceptance, 37 focused tests and Ruff. Full reproducible results: [summary.json](../results/verified_variant_comparison_v1/summary.json). Joint review seal: [AI_REVIEW.json](../results/verified_variant_comparison_v1/AI_REVIEW.json).
