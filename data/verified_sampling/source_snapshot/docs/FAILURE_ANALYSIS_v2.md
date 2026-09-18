# Failure analysis — agent system, v2 (final run), test split (n = 200)

Recomputed from `results/predictions.jsonl`, `results/judge_scores.jsonl` and the test rows of
`data/golden/golden_set.jsonl`; matches `eval_summary.json` (intent accuracy 0.81 / macro-F1 0.816;
escalation recall 0.93 / precision 0.68 at the dev-chosen threshold 0.9; 6 missed, 36 unnecessary;
reason-code accuracy 0.71; ship rate 0.87). `predictions.jsonl` decisions agree with the summary
(113 escalate, 77 TP / 36 FP / 6 FN). v1 is `docs/FAILURE_ANALYSIS_v1.md`. Modes are ordered by
count x cost; verbatim examples are in `results/failure_modes.json`.

## fm1 — Six confident auto-handles of security, lookup and no-issue tweets (6, 3%)

All six sit at confidence 0.90–0.98, above the guard, and no rule fires. The worst is new: g_215
("someone who broke into my spotify … another user was on") is classified
`account_hacked_or_security` at 0.98, whose `default_decision` is `escalate`, yet the LLM said
`auto_handle`, the trace records `policy_conflict: true`, and the pipeline only logs the conflict.
The reply pastes `support.spotify.com/article/hacked-account`, a URL that appears in no evidence
entry (v1 escalated this row). g_105 (`needs_account_lookup`) and g_151 ("Check your DMs") are the
same misses as v1; g_211 (job request) is still `out_of_scope` misread as feedback; g_042 and
g_088 are `other` rows that took a neighbour's intent (fm3). Zero-shot caught 4 of 6. All 17 gold
`needs_account_lookup` histories ask for a DM; the LLM escalated 14, the guard 1, one was missed.

## fm2 — URL scrub leaves dangling "more info here:" with no link (33, 16.5%)

The v1 fix removed `<url>` and home-page links from the evidence the model sees, but not the clause
that introduces them. The model copies the template verbatim, so 33 replies end "More info here: /AI", "at. Let us know" or "this link:?". 30 of
the 33 rows had a placeholder or fake link in v1: the defect moved rather than disappeared. The
judge flagged 8 as `hallucinated_link_or_policy` (all rejects), edited 3, and shipped 22 with
grounded >= 4, so the 5% flag rate understates the problem three-fold. 28 of the 33 were
auto-handled. Two other replies carry URLs found in no evidence (g_215, g_250) and two promise
that "developers are looking into this" (g_127, g_217) — the only genuine policy hallucinations.

## fm3 — `other` captions and chit-chat take the nearest thread's intent (14, 7%; recall 0.52)

BM25 matches the caption's nouns to a thread with a real issue and the classifier adopts its intent
(8 to `feature_request_or_feedback`, 4 to `subscription_or_plan`). Six are screenshot captions ending
in `<url>` ("Andorra != Switzerland :)", "They all have different names."), five are chit-chat or
venting, two presale codes, one job ask. Zero-shot shares 7 and gets 5 right: half retrieval, half
prompt gap. Cost: 10 of 14 are gold escalate; 7 were rescued only by the guard and recorded as
`low_confidence`, which is why 11 of 21 `ambiguous_or_media_only` true escalations carry the wrong
reason code; g_042, g_088, g_211 were missed outright.

## fm4 — The 0.9 guard escalates 28 correct auto-handles, 24 at exactly 0.85 (14%)

Of 36 unnecessary escalations, 28 are threshold-induced (14 with the right intent, e.g. g_045
"your website isn't working", g_051 Browse won't load, g_205 EQ crackle — the judge shipped 34 of
the 36 drafts), 7 LLM-chosen `needs_account_lookup`, 1 rule-forced ("$99"). Confidence is a
five-value ordinal; 0.85 means "vague or venting", not "unsure of intent". The guard cannot simply
be lowered: the seven rows it rescues over 0.85 include a `legal_or_safety` case (g_053, racist
album cover) and a `billing_dispute` (g_023, "pay") that no rule covers, plus four captions and
one lookup. Rules for those patterns must land first; then the dev threshold should re-tune to 0.85
(sweep: 13 missed / 12 unnecessary).

## fm5 — `playlist_or_library` boundary unchanged (12, 6%; F1 0.50)

Limits phrased as demands (g_044, g_063, g_112, g_148, g_162, g_141) go to feedback or plan; tweets
where "playlist" is the object of a bug, plan or login problem (g_004, g_082, g_194, g_195, g_233,
g_025) get the playlist label on the noun. 9 of 12 shared with zero-shot, 10 of 12 identical to v1:
a description problem in `config/intents.yaml`, not retrieval. Low cost: 8 were still auto-handled
correctly.

## Before / after (v1 -> v2)

| v1 mode | v1 | v2 | what happened |
|---|---|---|---|
| fm1 churn/lookup misses | 8 missed; 4 churn regex gaps | 6 missed; 0 churn | g_104, g_159, g_199, g_240 now rule-forced `churn_or_abuse`; g_222 caught by the guard; g_105, g_151, g_211 remain; g_042, g_088, g_215 are new |
| fm2 fake links | 29 `<url>` + 16 `open.spotify.com` + 1 x.com replies | 0 / 0 / 0 | placeholders gone, but 33 dangling "here:" sentences and 2 URLs from memory appeared |
| fm2 "engineers on it" | 3 | 2 (g_127, g_217) | unchanged mechanism |
| fm3 guard-induced unnecessary | 29 of 35 | 28 of 36 | unchanged; the guard still rescues 7 rows |
| fm3 reason-code accuracy | 0.64 (15 ambiguous -> low_confidence) | 0.71 (11) | small gain from fewer guard rescues |
| fm4 `other` recall | 0.55 (13 errors) | 0.52 (14) | unchanged |
| fm5 `playlist_or_library` F1 | 0.52 (11) | 0.50 (12) | unchanged |
| judge signature complaints | 31 negative rationales, 22 edits | 0 | judge prompt fix worked; tone 4.40 -> 4.77, ship 0.77 -> 0.87 |
| judge hallucination flags | 10 (6 fake links) | 10 (8 dangling links) | same rate, different defect |
| intent accuracy / macro-F1 | 0.815 / 0.824 | 0.81 / 0.816 | 34 of 38 errors are the same rows |

## Confidence calibration (agent, test)

| bin | n | intent accuracy | gold escalate rate |
|---|---|---|---|
| < 0.70 | 13 | 0.85 | 0.92 |
| 0.70–0.79 | 5 | 0.60 | 1.00 |
| 0.80–0.89 | 47 | 0.57 | 0.38 |
| 0.90–0.94 | 36 | 0.75 | 0.33 |
| >= 0.95 | 99 | 0.95 | 0.36 |

Values used: 0.95 (59), 0.85 (38), 0.9 (36), 0.99 (29), 0.8 (9), 1.0 (9). Accuracy separates
>= 0.95 from the rest; the 0.85/0.9 boundary under the threshold is the noisiest region.

## Missed escalations (threshold 0.9)

| id | gold reason | what should have caught it | zero-shot? |
|---|---|---|---|
| g_042 | ambiguous_or_media_only | caption rule: <=8 words ending in `<url>`, deictic "this issue" | yes |
| g_088 | ambiguous_or_media_only | promote `repeated_contact` ("how many times do I have to tell you") + no-request prompt rule | no |
| g_105 | needs_account_lookup | DM-consistency rule (both cited replies ask for a DM) | yes |
| g_151 | ambiguous_or_media_only | rule `check (your\|my) dms?` (unchanged since v1) | yes |
| g_211 | out_of_scope | prompt: hiring/job requests are out_of_scope (unchanged since v1) | no |
| g_215 | account_security | enforce `default_decision` on `policy_conflict`; security regex `broke into\|hijack` | yes |

## Reason-code confusion on the 77 true escalations (accuracy 0.71)

`ambiguous_or_media_only` -> `low_confidence` 11; `billing_dispute` -> `needs_account_lookup` 3
(g_007, g_072, g_170: "paid", "payment" are not in the money regex, which lists "payment failed"
only); `high_frustration_or_churn` -> `needs_account_lookup` 2; five other singletons to
`low_confidence`. Excluding the guard's relabels, accuracy is 0.90 (55/61).

## What I checked and ruled out

- **Retrieval as the cause of low judge scores**: 31 rows have grounded or resolves <= 3. Top hit
  was topically wrong in 8 (g_012, g_081, g_091, g_166, g_194, g_217, g_240, g_249 — all `other` or
  boundary rows); 16 of the 31 are dangling- or missing-link replies on the right thread.
- **DM-only boilerplate**: top hit is a DM ask in 46/200 rows, 73/246 cited threads (v1: 46, 70); unchanged.
- **LLM over-escalating**: 7 of 36 unnecessary are LLM-chosen; zero-shot's precision (0.80) beats
  the agent's (0.68) only because it has no guard (7 misses vs 6).
- **Rule false positives**: 1 ("$99"). Rules remain precise and narrow.
- **Taxonomy vs retrieval on the 38 intent errors**: 23 shared with zero-shot, 11 zero-shot right,
  4 both wrong differently; agent right on 11 of zero-shot's 38 errors. `subscription_or_plan` and `feature_request_or_feedback` precision (0.65) is the `other` spill-over.
- **"the help article" phrasing**: 8 replies, 7 shipped; the judge no longer penalises it.
- **Judge tone bias**: 33 rationales mention the signature, none negatively.
- **Invented policy**: only the two "developers are on it" rows; `safe` mean 4.99.
- **Non-English**: 3 errors (g_145, g_202 Taglish; g_166 "por favor" tail, now a `wrong_issue`
  reject); too few to rank.
