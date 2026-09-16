# Failure analysis — agent system, test split (n = 200)

Recomputed from `results/predictions.jsonl`, `results/judge_scores.jsonl` and the test rows of
`data/golden/golden_set.jsonl`; matches `eval_summary.json` (intent accuracy 0.815; escalation
recall 0.90 / precision 0.68 at threshold 0.9; 8 missed, 35 unnecessary; ship rate 0.77). Ordered by
count x cost. Verbatim examples are in `results/failure_modes.json`.

## fm1 — Churn threats, profanity and account-specific asks auto-handled (8 missed, 4%)

The LLM alone auto-handled 28 of 83 gold-escalate rows (raw recall 0.66). The 0.9 guard rescued 19;
the 8 survivors score 0.9–0.95 and no rule covers them. Four are `high_frustration_or_churn`: the
`churn_or_abuse` regex matches only `switch(ing) to (apple music|tidal|...)` and
`fuck(ing) (you|spotify|this)`, so "Switching to @user" (g_104, handle scrubbed), "move to Apple
Music" (g_159), "change to AM" (g_240) and "fucking atrocious" (g_199) pass. Three are
`needs_account_lookup` (g_105, g_222, and g_164 saved only by the guard): every historical reply asks
for a DM, but the agent drafted generic steps. Zero-shot escalated 7 of 8, so the bias comes from
evidence full of self-serve replies, not from the model.

## fm2 — Fake links and "engineers are on the case" (20 replies, 10%)

Retrieved brand replies carry `<url>` where the link was scrubbed. In 16 replies the agent
substituted the literal `https://open.spotify.com/`; once (g_228) an x.com DM-compose link; 29 more
emitted `<url>` verbatim. The judge flagged 6 of the 16 (5 rejects) and shipped the other 7
unchecked. Three replies (g_019, g_131, g_217) copied a live-status sentence ("our tech folks are
investigating this as we speak") from a cited thread about a different incident. In 18 of 20 cases
the evidence was topically right: a post-processing gap, not retrieval.

## fm3 — The 0.9 guard escalates 29 correct auto-handles (14.5%)

`config/escalation.yaml` says 0.60; the reported run uses 0.90 because the LLM alone reaches 0.66
recall. Confidence is a 5-value ordinal in practice (0.85/0.9/0.95/0.99 cover 168/200 rows) and
intent accuracy is 0.67 at 0.85 vs 0.74 at 0.90, so the cut catches under-escalations only because
vague or venting tweets land at 0.85. Cost: 29 of 35 unnecessary escalations (23 at exactly 0.85; 17
with correct intent; 10 plain playback troubleshooting such as g_070, g_028). It also corrupts the
reason code: 15 of 24 gold `ambiguous_or_media_only` rows are reported as `low_confidence` (reason
accuracy 0.64). Only 5 of the 35 were LLM-chosen `needs_account_lookup`; 1 was rule-forced ("$99",
g_198).

## fm4 — `other` recall 0.55: captions and chit-chat take the nearest thread's intent (13, 6.5%)

The retriever matches on the caption's nouns and the classifier adopts that thread's intent:
"Andorra != Switzerland :) <url>" (g_012) becomes `content_or_availability`; "They all have
different names. <url>" (g_091) becomes `metadata_or_artist_issue`; two presale-code tweets (g_130,
g_182) become `subscription_or_plan`; "hire me to make playlists" (g_211) becomes
`feature_request_or_feedback`. Zero-shot got 8 of 13 right, so this is retrieval-induced. 9 of the
13 are gold escalate, so the invented intent yields a specific reply to an issue that exists only in
a screenshot.

## fm5 — `playlist_or_library` F1 0.52 (11, 5.5%)

7 of 11 errors are shared with zero-shot, so the boundary is unclear in the prompt. (a) Five
library/download-limit rows phrased as demands (g_044, g_063, g_141, g_148, g_162) go to
`feature_request_or_feedback` or `download_or_offline`; in g_141 the reply quoted the 3,333 download
limit instead of the 10k library limit — the run's only `wrong_issue` flag — although the top
retrieved thread had the right answer. (b) Five rows where "playlist" is only the object of a bug or
plan question (g_004, g_025, g_082, g_194, g_195) get `playlist_or_library` on the noun alone.

## Confidence calibration (agent, test)

| bin | n | intent accuracy | gold escalate rate |
|---|---|---|---|
| < 0.70 | 12 | 1.00 | 1.00 |
| 0.70–0.79 | 6 | 0.33 | 0.50 |
| 0.80–0.89 | 49 | 0.63 | 0.45 |
| 0.90–0.94 | 42 | 0.74 | 0.29 |
| >= 0.95 | 91 | 0.96 | 0.37 |

The < 0.70 bin is all rule-forced short messages labelled `other`. Confidence separates >= 0.95 from
the rest; it does not separate 0.85 from 0.90, which is where the threshold sits.

## Missed escalations at threshold 0.9

| id | gold reason | should have been caught by | zero-shot? |
|---|---|---|---|
| g_104 | high_frustration_or_churn | churn rule: "Switching to @user" | yes |
| g_105 | needs_account_lookup | DM-consistency rule (historical reply asks for email) | yes |
| g_151 | ambiguous_or_media_only | "Check your DMs" rule (3 words pass `min_words`) | yes |
| g_159 | high_frustration_or_churn | churn rule: "move to Apple Music" | yes |
| g_199 | high_frustration_or_churn | profanity-at-brand rule: "fucking atrocious" | yes |
| g_211 | out_of_scope | prompt: job requests are out_of_scope | no |
| g_222 | needs_account_lookup | DM-consistency rule ("sent a DM your way") | yes |
| g_240 | high_frustration_or_churn | churn rule: "change to AM" | yes |

## Checked and ruled out

- **LLM over-asks for lookups**: no — 5 of 35 unnecessary escalations; the LLM under-escalates.
- **Rule false positives**: 31 rule-forced, 30 gold escalate. Rules are precise but narrow.
- **Retrieval ranking**: top hit is DM-only boilerplate in 46/200 rows (70/243 cited threads), but
  only ~9 of the 28 low-judged rows had an off-topic top hit (g_019, g_051, g_053, g_081, g_150,
  g_217). Reply failures are post-processing (fm2).
- **Judge tone**: 36 rationales complain about the contract-mandated `/AI` signature; 25 of 36
  `edit` verdicts are those rows. Ship rate 0.77 is deflated by the judge prompt, not reply content.
- **Taxonomy vs retrieval**: of 37 intent errors, 18 shared with zero-shot, 12 zero-shot-right, 7
  both wrong differently. Agent was right on 11 of zero-shot's 36 errors.
- **Non-English**: 3 errors (g_145, g_202 Taglish; g_166 "por favor" tail); too few to rank.

## Data problems

- `predictions.jsonl` decisions are at threshold 0.60 (27 FN / 6 FP); `eval_summary` re-thresholds
  at 0.90. `pred_decision` in `failure_modes.json` uses the reported 0.9 decision, so 29 rows read
  `escalate` while the raw `decision` says `auto_handle` with `escalation: null`.
- `config/escalation.yaml` (`confidence_threshold: 0.60`) disagrees with the reported run (0.90).
- fm2's flag counts rest on one judge that missed 10 of 16 fake links. For the revised benchmark's completed review by Arnav Bule, see [review record](HUMAN_REVIEW.md).
