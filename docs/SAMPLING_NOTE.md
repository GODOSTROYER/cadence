# Golden-set candidate sampling (`data/golden/candidates.jsonl`)

Produced by `python scripts/03_sample_candidates.py` (`cadence.data.sample`), deterministic with `SEED = 42`.
Candidates are the pre-label pool from which the 150–250 example golden set is annotated (CONTRACT §7).
Re-run the script after editing `keywords` in `config/intents.yaml`; the buckets are read at runtime.

## Pool

| step | rows |
|---|---|
| SpotifyCares openers (`spotify_openers.parquet`) | 27,627 |
| `language == "en"` and `n_brand_replies >= 1` | 27,056 |
| exact-duplicate `customer_text` removed (keep earliest tweet) | 26,877 |
| of which `short_or_media` (`n_words <= 3` or bare `<url>`) | 435 |

Every pooled message is assigned to at most one keyword bucket `kw:<intent_id>`: the intent whose
`keywords` list produces the most hits in the lower-cased cleaned text (ties -> the earlier intent in the
YAML; no hit -> no keyword bucket, the message is only reachable through the `random` bucket). Keywords of
four characters or fewer are matched on word boundaries (`(?<!\w)app(?!\w)`), longer keywords as plain
substrings; keywords without word characters (`$`, `£`, `€`) are always substrings. Pool sizes per bucket
with the v0 keywords:

| keyword bucket | pool size |
|---|---|
| (no keyword hit) | 4,422 |
| kw:subscription_or_plan | 4,047 |
| kw:content_or_availability | 3,992 |
| kw:other | 3,328 |
| kw:playback_or_app_bug | 2,648 |
| kw:billing_or_charge | 2,458 |
| kw:playlist_or_library | 1,927 |
| kw:login_or_password | 1,772 |
| kw:feature_request_or_feedback | 979 |
| kw:download_or_offline | 939 |
| kw:account_hacked_or_security | 294 |
| kw:non_english | 71 |

## Draw procedure

1. **`short_or_media`** – 15 messages with `n_words <= 3` or consisting only of `<url>` tokens. They
   deliberately probe the `ambiguous_or_media_only` escalation policy.
2. **Keyword buckets** – up to 30 messages per `kw:<intent_id>` bucket, in YAML order.
3. **`random`** – a uniform draw from the whole pool sized `max(target - drawn, ceil(0.30 * drawn / 0.70))`
   so that at least 30 % of all candidates are unstratified. This is the unbiased slice for estimating the
   real intent distribution and for catching messages the keywords miss.

Inside every pass the candidates are visited in a **month round-robin** (rows shuffled within each
calendar month, months rotated) so each bucket spreads over time instead of concentrating in Oct/Nov 2017,
and a message is skipped when (a) it was already drawn or (b) its text is a **near-duplicate**
(`rapidfuzz.fuzz.ratio > 92`) of any previously accepted candidate — templated tweets such as the
"UPDATE IPHONE X" campaign therefore appear once. Finally the list is shuffled with `SEED` and ids
`c_001`… are assigned in that order, so annotators never see bucket runs. Each row carries the cleaned
`text`, `text_raw`, the first brand reply (`historical_brand_reply`) and the full public thread
(`historical_thread`) for context.

## Result (v1 keywords, final run: `--per-bucket 25 --min-random-share 0.28`)

The v0 run (30 per bucket, 11 intents) produced 493 candidates; after the taxonomy pass added a twelfth
intent and rewrote the keywords, the script was re-run with 25 per bucket to land near the contract's ~420:
**438 candidates from 438 distinct threads.**

| bucket | count | share |
|---|---:|---:|
| random | 123 | 28.1 % |
| kw:\<intent\> × 12 (account_hacked_or_security, billing_or_charge, content_or_availability, download_or_offline, feature_request_or_feedback, login_or_password, metadata_or_artist_issue, non_english, other, playback_or_app_bug, playlist_or_library, subscription_or_plan) | 25 each = 300 | 5.7 % each |
| short_or_media | 15 | 3.4 % |

Spread: 19 calendar months; 115 / 116 / 103 candidates in Oct / Nov / Dec 2017, 48 in Sep 2017, 56 earlier.
12.1 % of candidates contain a link (openers overall: 14.6 %); 45 % come from threads with more than one
public exchange (a deliberate side effect of the usefulness of multi-turn threads for context).

## Labelling subset (`scripts/make_label_chunks.py --n 250 --chunks 5 --non-english 10`)

Two annotators cannot label 438 messages in the time available, and the assignment caps the golden set at
250, so a stratified subset was drawn from the candidates with the same seed: every bucket keeps a floor of
12 and the rest is proportional, giving **13 per keyword bucket (156), 72 random (30 %), 12 short_or_media**
= 240, plus **10 genuinely non-English openers** (`language == "other"`, ≥ 3 words, with a brand reply) that
the English-only sampler could not reach, so that the `non_english` intent and the language-redirect policy
have real support. The 250 rows were shuffled and cut into five chunks of 50; each chunk was labelled
independently by two annotators and adjudicated (see `LABELLING_GUIDE.md` §7 and `golden_stats.json`).

## Known caveats

- The pool is English-only by design (the stopword heuristic classifies 97.9 % of openers as English), so
  the `kw:non_english` bucket holds mixed-language tweets (Taglish, Indonesian, Spanish fragments). The
  v0 `conta`/"contact" substring bug was fixed in the v1 keywords; the 10 `language == "other"` rows above
  are the genuinely non-English support.
- Keyword buckets are sampling strata, not labels. Annotators label every candidate from scratch; the
  `sampling_bucket` field is kept only so the report can describe the stratification.
- Exact-duplicate removal keeps the earliest tweet, so campaign tweets ("UPDATE IPHONE X") survive once.
- Because rare intents are over-sampled, the golden set's intent distribution is **not** the natural
  distribution; the `random` slice (30 %) is the unbiased estimate of it (see `docs/TAXONOMY.md` §4).

## September 2026 audit addendum: separate AI-reviewed benchmark

The original250 labels were produced by AI passes, not humans. Historical references to hand-labeling should not be interpreted as human annotation. The original200test examples were inspected repeatedly across runs and now serve as a regression set.

A new200-example sample is locked under `data/holdout/`. Script08 excludes original candidates, taxonomy IDs/texts, old golden rows, shared tweet components and near duplicates before sampling with seed2026. Within-sample duplicate rejection changes sampling weights; the sample is not a uniform traffic estimate. Review was performed on customer text before benchmark predictions, with the existing taxonomy/labeling guide available. No labels were changed after prediction.

At the author's request, Codex reviewed every new message and wrote its rationale in `ai_review_notes.tsv`. `AI_REVIEW.lock.json` records provenance and hashes; `ai_reviewed_set.jsonl` has `label_source: ai` on every row. The same assistant also developed code. Arnav Bule subsequently completed human review of all 200 examples, confirmed on 16 September 2026; see [review record](HUMAN_REVIEW.md). This author review is recorded separately from the original frozen labels and blank annotation worksheet. Measured judge–human agreement remains unavailable.
