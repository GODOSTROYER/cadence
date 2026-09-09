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

## Result (v0 keywords, 2026-09 run)

493 candidates from 493 distinct threads (the 30-per-bucket rule fills every bucket, and the 30 % floor
then lifts the random slice from 75 to 148; `--per-bucket 25` yields exactly 420).

| bucket | count | share |
|---|---:|---:|
| random | 148 | 30.0 % |
| kw:account_hacked_or_security | 30 | 6.1 % |
| kw:billing_or_charge | 30 | 6.1 % |
| kw:content_or_availability | 30 | 6.1 % |
| kw:download_or_offline | 30 | 6.1 % |
| kw:feature_request_or_feedback | 30 | 6.1 % |
| kw:login_or_password | 30 | 6.1 % |
| kw:non_english | 30 | 6.1 % |
| kw:other | 30 | 6.1 % |
| kw:playback_or_app_bug | 30 | 6.1 % |
| kw:playlist_or_library | 30 | 6.1 % |
| kw:subscription_or_plan | 30 | 6.1 % |
| short_or_media | 15 | 3.0 % |

Spread: 19 calendar months (Aug 2015 – Dec 2017); 135 / 133 / 120 candidates in Oct / Nov / Dec 2017, 49 in
Sep 2017, 56 earlier. 14.0 % of candidates contain a link (openers overall: 14.6 %); 33.7 % come from
multi-turn threads (overall: 28.1 %).

## Known caveats

- The pool is English-only by design; the `kw:non_english` bucket is therefore filled with English texts
  that happen to contain a foreign keyword — 22 of its 30 draws match `conta` (Portuguese) as a substring
  of "contact". Improving the keyword (e.g. `minha conta`) in `config/intents.yaml` and re-running the
  script fixes this; genuinely non-English openers (571, 2.1 %) are labelled `language == "other"` in the
  parquet and can be added to the golden set separately if the `non_english` intent needs support.
- Keyword buckets are sampling strata, not labels. Annotators label every candidate from scratch; the
  `sampling_bucket` field is kept only so the report can describe the stratification.
- Exact-duplicate removal keeps the earliest tweet, so campaign tweets ("UPDATE IPHONE X") survive once.
