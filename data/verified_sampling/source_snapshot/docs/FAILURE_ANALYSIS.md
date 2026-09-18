# Failure analysis — agent system, run 3 (final), test split (n = 200)

Recomputed from `results/predictions.jsonl`, `results/judge_scores.jsonl` and the test rows of
`data/golden/golden_set.jsonl`; matches `eval_summary.json` (macro-F1 0.821; escalation recall 0.94 /
precision 0.68 at threshold 0.9; 5 missed, 36 unnecessary; reason-code accuracy 0.77; judge 4.58; ship
0.895). Runs 1–2: `docs/FAILURE_ANALYSIS_v1.md`, `_v2.md`, `results/v1`, `results/v2`. All 200 agent rows
are cache hits, so every change since run 2 is post-processing or policy; an interim run 3 (judge 4.42)
whose scrub hollowed seven replies was replaced by the phrase-level scrub and re-judged. Verbatim
examples in `results/failure_modes.json`.

## fm1 — Five confident auto-handles: lookup, "Check your DMs", caption, vent, job ask (5, 2.5%)

Run 2's rows minus g_215 (fixed by `enforce_default_decision`). All five sit at 0.90–0.95, no rule
fires, the LLM says `auto_handle`, and the predicted intents default to `auto_handle`, so neither guard
can reach them. g_105's historical reply asks for a DM, but four of its six retrieved threads answer
with a link, so the draft says "try heading to this link?" with no link. g_042, g_088 and g_211 are
`other` rows that took a neighbour thread's intent (fm3); g_151 has no describable issue. Zero-shot
caught 3 of 5.

## fm2 — Replies promise a link they never carry (34) or invent status / a URL (4) (38, 19%)

The scrub is fixed; the defect it was hiding is a data limit. 706 of the 1,195 evidence replies the
model sees contain `<url>`, but only 8 of 150 `link_map.json` entries resolve to a real article (the rest
land on the `open.spotify.com` home page or the DM card), so just 12 evidence items carry a
`resolved_links` entry and 4 of 200 replies contain a URL. The model copies the template's pointer
sentence — "Check out the steps under 'Downloads unexpectedly removed'", "Suggest it in our Community",
"Dutch support via email" — which still promises a resource the reader cannot reach (34 replies; 25
shipped, 6 edit, 3 reject). Four mid-sentence fragments survive (g_027 "More info Let us know", g_105
"heading to this link?", g_200 "Check out this", g_208 "via email over"). Two replies copy a live-status
sentence from an older incident (g_127, g_217) and two paste URLs from model memory (g_215, g_250). The
judge flags 4 of 38, so the 2% rate understates this nine-fold.

## fm3 — `other` captions, vents and presale asks take the nearest thread's intent (14, 7%)

Recall 0.52, precision 1.0; identical rows to run 2. BM25 matches the caption's nouns to a real thread
and the classifier adopts its label (8 feedback, 4 plan, 1 login, 1 metadata). Zero-shot shares 7 and gets
5 right: half retrieval anchoring, half prompt. 10 of 14 are gold escalate; 7 were rescued only by the
guard as `low_confidence`, 3 missed outright.

## fm4 — The 0.9 guard escalates 28 correct auto-handles, 24 at exactly 0.85 (14%)

Of 36 unnecessary escalations: 28 threshold-induced (14 right intent; judge shipped 27 of 28), 7
LLM-chosen `needs_account_lookup`, 1 rule-forced ("$99"), 0 enforced-default. The guard still rescues
6 gold escalations at exactly 0.85 that no rule covers (g_053 racist cover, g_222 lookup, g_012/g_091
captions, g_014/g_167 vents) and relabels 15 true escalations as `low_confidence`. Sweep at 0.85: 11
missed / 12 unnecessary, so the fm1 rules and fm3 prompt must land first.

## fm5 — `playlist_or_library` boundary unchanged over three runs (12, 6%; F1 0.50)

Limits phrased as demands go to feedback or plan (g_044, g_063, g_112, g_141, g_148, g_162); tweets
where "playlist" is merely the object of a bug, download, plan or login problem take the playlist label
(g_004, g_025, g_082, g_194, g_195, g_233). 9 of 12 shared with zero-shot, all 12 identical to run 2: an
`intents.yaml` description problem; 11 of 12 drafts shipped.

## Intent errors by mechanism (37)

| mechanism | n | zero-shot same / right | gold escalate | outcome |
|---|---|---|---|---|
| `other` adopts neighbour intent (fm3) | 14 | 7 / 5 | 10 | 3 missed, 7 guard-rescued, 2 unnecessary |
| `playlist_or_library` boundary (fm5) | 12 | 9 / 2 | 1 | 5 unnecessary (guard) |
| non-English / mixed-language (g_145, g_202 Taglish; g_166 "por favor") | 3 | 1 / 1 | 0 | 3 unnecessary (guard) |
| singletons (g_019 artists' login, g_040 earnings → billing, g_069, g_079, g_100, g_131, g_156, g_159) | 8 | 5 / 3 | 2 | 5 unnecessary, both escalations caught |

22 of 37 shared with zero-shot, 11 zero-shot right, 4 both wrong differently.

## Before / after (runs 1 → 2 → 3)

| metric | run 1 | run 2 | run 3 (final) |
|---|---|---|---|
| missed escalations | 8 | 6 | 5 (g_042, g_088, g_105, g_151, g_211) |
| placeholder / bare links in replies | 46 (29 `<url>`, 16 home page, 1 x.com) | 0 | 0 |
| URLs from model memory (not in evidence) | masked by placeholders | 2 (g_215, g_250) | 2 (same) |
| dangling link clauses (trailing) | 3 | 33 (25 by the stricter regex) | 0 (interim: 10 + 7 hollowed); 4 mid-sentence fragments |
| replies naming a resource with no link | n/a (links were fake) | n/a | 34 |
| guard-induced unnecessary escalations | 29 of 35 | 28 of 36 | 28 of 36 |
| reason-code accuracy (excl. `low_confidence`) | 0.64 | 0.71 (0.90) | 0.77 (0.95) |
| judge signature complaints | 31 | 0 | 0 |
| judge hallucination flags | 10 (6 fake links) | 10 (8 dangling) | 4 (2 status claims, 2 link-less pointers) |
| judge overall | 4.34 | 4.50 | 4.58 (interim 4.42) |
| ship rate | 0.77 | 0.87 | 0.895 |
| intent accuracy / macro-F1 | 0.815 / 0.824 | 0.81 / 0.816 | 0.815 / 0.821 |

Reply integrity on the final run: 0 replies with `<url>`, a bare home page or DM link, over 280
characters, ending in a colon or link introducer, or hollowed to a greeting; shortest body 37 characters
(g_022 "We've just sent you a DM"). Verdicts: 179 ship / 12 edit / 9 reject; 10 of the 21 non-ship
rationales ask for a link. `wrong_issue` (2): g_166 "por favor" tail read as Spanish, g_240 device
questions for a Discover Weekly complaint.

## Confidence calibration (agent, test)

| bin | n | intent accuracy | gold escalate rate |
|---|---|---|---|
| < 0.70 | 13 | 0.85 | 0.92 |
| 0.70–0.79 | 5 | 0.60 | 1.00 |
| 0.80–0.89 | 46 | 0.59 | 0.37 |
| 0.90–0.94 | 37 | 0.76 | 0.35 |
| >= 0.95 | 99 | 0.95 | 0.36 |

Accuracy separates >= 0.95 from everything else; the 0.85/0.9 boundary carries no escalation signal.

## Missed escalations (threshold 0.9)

| id | gold reason | what should have caught it | zero-shot? |
|---|---|---|---|
| g_042 | ambiguous_or_media_only | caption rule: <= 8 words ending in `<url>`, deictic "this issue" | yes |
| g_088 | ambiguous_or_media_only | promote `repeated_contact` ("how many times") when no request verb | no |
| g_105 | needs_account_lookup | DM-consistency rule (historical reply and 1 of 6 evidence replies ask for a DM; 4 answer with a now-dead link) | yes |
| g_151 | ambiguous_or_media_only | rule `^check (your\|my) dms?$` (unchanged since run 1) | yes |
| g_211 | out_of_scope | prompt: hiring/job requests are out_of_scope; rule `hire me` | no |

## Reason-code confusion on the 78 true escalations (accuracy 0.77)

`ambiguous_or_media_only` → `low_confidence` 11 (all guard rescues); `high_frustration_or_churn` →
`needs_account_lookup` 2 (g_083, g_099) and → `low_confidence` 1 (g_186); `out_of_scope`,
`legal_or_safety`, `needs_account_lookup` → `low_confidence` 1 each (g_018, g_053, g_222);
`needs_account_lookup` → `billing_dispute` 1 (g_189 "paying member", the widened money rule's one cost).
Excluding the guard's relabels, 60/63 = 0.95. Raw LLM recall is 61/83; rules add 38 (39 forced, g_198
the one false positive), the enforced default adds g_215, the guard adds 15.

## What I checked and ruled out

- **Retrieval as the cause of low judge scores**: 30 rows have grounded or resolves <= 3; the top hit is
  off-topic in 10 (g_001, g_012, g_018, g_030, g_081, g_161, g_166, g_217, g_240, g_249), 8 of them
  gold `other` with no right thread to find; 10 are link-less pointers on the right thread (fm2).
- **DM-only boilerplate**: top hit asks for a DM in 47/200 rows, 72/248 cited threads; unchanged.
- **LLM over-escalating**: 7 of 36, all `needs_account_lookup`; zero-shot's 0.80 precision comes with 7
  misses.
- **Rule false positives**: 39 rule-forced, 38 gold escalate (only g_198 "$99").
- **Scrub regression**: none left; the interim's four "Hey there!" replies (g_073, g_114, g_179, g_180)
  now keep their first sentence and score 3–5.
- **Judge drift**: 31 rationales mention the signature, all approving; identical replies scored as in run 2.
- **Invented policy**: only the two status-claim rows and two memory URLs; `safe` mean 4.985.
- **Non-English**: 3 errors, all guard-escalated; too few to rank.
