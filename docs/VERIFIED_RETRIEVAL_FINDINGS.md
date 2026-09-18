# Verified retrieval: frozen AI development review

## Findings

For first replies, top-three diagnostic hits were 9/20 for raw text, 9/20 for the request frame, and 6/20 after token reranking. Proposed-action support was 6/20, 6/20, and 3/20, respectively. The frame query shows no gain on these top-three outcomes in this sample; token reranking reduces diagnostic and action-support coverage. Later views must be compared on available matched candidates and include earlier turns, so their ratings do not isolate the usefulness of the final reply.

These are **AI-only descriptive findings on 20 development messages**, not human verification or a promotion decision. The 360 packet rows contain 244 unique substantive contexts; neither count is an independent sample size. Ratings were frozen before the private arm mapping was opened.

## First replies: message-level retrieval hits

A hit means at least one qualifying candidate at rank 1 or within ranks 1–3. Relevance is strictly the same issue (`2`); partly relevant (`1`) is reported separately in the JSON. All first-reply slots were available. Each count below has the same 20-message denominator.

| Arm | Top 1 same issue | Top 3 same issue | Top 1 diagnostic | Top 3 diagnostic | Top 1 action support | Top 3 action support |
|---|---:|---:|---:|---:|---:|---:|
| Raw text | 5/20 | 10/20 | 4/20 | 9/20 | 3/20 | 6/20 |
| Request frame | 6/20 | 9/20 | 2/20 | 9/20 | 2/20 | 6/20 |
| Frame + token rerank | 5/20 | 9/20 | 3/20 | 6/20 | 2/20 | 3/20 |

At the looser threshold of at least partly relevant (`1` or `2`), frame querying increases top-one hits from 11/20 to 18/20, and top-three hits from 16/20 to 20/20. That broader topic overlap does not establish a gain in the top-three same-issue, diagnostic, or action-support outcomes. First-reply top-one same-issue hits do increase slightly, from 5/20 to 6/20.

### Paired top-three differences

Differences are right arm minus left arm, paired by customer message. Intervals resample whole paired messages (20,000 replicates, fixed seed); they are descriptive percentile intervals, not adjusted confirmatory tests. They do not measure AI reviewer error. The small development sample and AI judgment uncertainty limit generalization.

| Comparison | Metric | Gained / lost messages | Difference | Descriptive 95% interval |
|---|---|---:|---:|---:|
| Request frame − Raw text | same issue | 3 / 4 | -5 pp | [-30, +20] pp |
| Request frame − Raw text | useful diagnostic pattern | 2 / 2 | +0 pp | [-20, +20] pp |
| Request frame − Raw text | supports proposed action | 2 / 2 | +0 pp | [-20, +20] pp |
| Frame + token rerank − Request frame | same issue | 1 / 1 | +0 pp | [-15, +15] pp |
| Frame + token rerank − Request frame | useful diagnostic pattern | 0 / 3 | -15 pp | [-30, +0] pp |
| Frame + token rerank − Request frame | supports proposed action | 0 / 3 | -15 pp | [-30, +0] pp |
| Frame + token rerank − Raw text | same issue | 3 / 4 | -5 pp | [-30, +20] pp |
| Frame + token rerank − Raw text | useful diagnostic pattern | 1 / 4 | -15 pp | [-35, +5] pp |
| Frame + token rerank − Raw text | supports proposed action | 1 / 4 | -15 pp | [-35, +5] pp |

Frame querying changes which messages benefit; equal total diagnostic coverage does not mean identical hits. The simple token-overlap reranker has no supported improvement claim here. These results concern retrieval of historical examples for the already-proposed response, not changes to the response itself, current factual accuracy, or downstream support outcomes.

## Later views: coverage and matched comparison

| Arm | Available / absent later slots (top 3) | Messages with any later view | Same-issue hit | Diagnostic hit | Action-support hit |
|---|---:|---:|---:|---:|---:|
| Raw text | 21 / 39 | 13/20 | 4/20 | 7/20 | 4/20 |
| Request frame | 24 / 36 | 15/20 | 6/20 | 7/20 | 4/20 |
| Frame + token rerank | 27 / 33 | 15/20 | 6/20 | 6/20 | 3/20 |

The table uses all selected messages to measure delivered coverage; an absent later reply is not a negative content rating. The JSON also gives positive-candidate rates conditional on availability, available-message hit rates, top-one results, and full yes/no/uncertain distributions.

For a content comparison, keep only the same historical candidates with both views available. The union below counts each `(current message, historical thread)` once across arms.

| Matched set | Candidate pairs | Paired messages | First / later diagnostic candidates | Later-only / first-only candidates | First / later messages with diagnostic hit |
|---|---:|---:|---:|---:|---:|
| Raw text | 21 | 13 | 10 / 11 | 1 / 0 | 6 / 7 |
| Request frame | 24 | 15 | 5 / 10 | 5 / 0 | 4 / 7 |
| Frame + token rerank | 27 | 15 | 5 / 10 | 5 / 0 | 3 / 6 |
| Deduplicated union | 49 | 18 | 15 / 22 | 7 / 0 | 6 / 9 |

In the deduplicated matched union, diagnostic message hits change by +16.7 percentage points (descriptive paired 95% interval [+0.0, +33.3]; 18 eligible message clusters). 2 selected messages have no matched available pair and are excluded from this conditional comparison.

**Interpretation:** the later view is a larger context window and can retain diagnostics from the first reply. A gain therefore reflects usefulness of the supplied view, not the isolated final reply or a resolved customer issue. Availability is selective, and this matched analysis does not remove that bias.

## Provenance and reproduction

- The existing `validate_ratings(..., reviewer_type="ai")` helper validates the frozen packet and all ratings. The analysis additionally checks exact packet/mapping/rating identity coverage, item hashes, alias bindings, the complete message/arm/rank/view grid, and first/later candidate identities.
- Current authority is a separate field: all 360 rows are `unsupported`. Historical action support does not authenticate current URLs, product availability, promotional terms, or a successful outcome.
- The summary binds source files and analysis/validator code with the repository's portable SHA256 helper (CRLF normalized for text). The original packet's raw-byte seals are validated separately. No ratings are edited, no candidate implementation changes are made, and no reserved sample text or gold labels are read.
- Full counts and paired message deltas: [summary.json](../results/verified_retrieval_dev_v2/summary.json). Review process: [AI_REVIEW_NOTES.md](../results/verified_retrieval_dev_v2/AI_REVIEW_NOTES.md).

```powershell
python analysis_tools/summarize_verified_retrieval.py
python analysis_tools/summarize_verified_retrieval.py --check
```
