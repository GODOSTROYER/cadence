# Cadence intent taxonomy (v1) — method, evidence and decision rules

This document explains how `config/intents.yaml` v1 was derived from the SpotifyCares corpus and how to apply it.
The companion files are `docs/taxonomy_calibration.jsonl` (150 hand-labelled openers), `docs/BRAND_VOICE.md`
(reply style per intent) and `data/golden/LABELLING_GUIDE.md` (annotator instructions).

## 1. Method

Data: `data/processed/spotify_openers.parquet` (27,627 openers; 27,056 flagged `language == "en"` with at least
one brand reply). Everything below is deterministic with `SEED = 42`.

1. **Keyword-bucket census with the v0 keywords** (`cadence.data.sample.assign_bucket`, the same code the sampler
   and the `simple_keyword` baseline use). Result on the 27,056 English openers: no hit 16.5 %,
   subscription_or_plan 15.0 %, content_or_availability 14.8 %, other 12.7 %, playback_or_app_bug 9.8 %,
   billing_or_charge 9.1 %, playlist_or_library 7.1 %, login_or_password 6.6 %, feature_request_or_feedback 3.6 %,
   download_or_offline 3.5 %, account_hacked_or_security 1.1 %, non_english 0.3 %. The v0 `other` bucket was
   inflated by greeting words (`hi`, `help`, `<url>`), and 22 of the 30 `non_english` draws in the first sampling run
   matched `conta` inside "contact" (see `docs/SAMPLING_NOTE.md`).
2. **Clustering.** TF-IDF (1–2 grams, `min_df=5`, `max_df=0.5`, `sublinear_tf=True`, English stop words plus
   `url/user/spotify/hey/hi/hello/just/guys/please/pls/plz`, 7,923 features) over the 27,056 openers, then k-means
   with k = 25 and `random_state=42`. *Deviation from the plan:* `MiniBatchKMeans(k=25, random_state=42)` collapsed
   to one cluster holding 99.5 % of the rows on this sparse matrix (also with `batch_size=4096`, `n_init=10`,
   `reassignment_ratio=0.05`), so full-batch `KMeans(n_clusters=25, random_state=42, n_init=3)` on the identical
   features was used instead. Top-12 terms and 8 random members of every cluster were read (table in §2).
3. **Reading.** 200 uniformly random English openers (`DataFrame.sample(200, random_state=42)`) were read end to end.
4. **Hand labelling.** 250 uniformly random English openers were labelled by the taxonomy author with the final
   decision rules: a **dev** set of 100 (the first 100 of the 200 above) used to tune the keywords, and a held-out
   **calibration/test** set of 150 (`DataFrame.sample(150, random_state=43)`, written to
   `docs/taxonomy_calibration.jsonl` as `{thread_id, text, intent}`). Labels were assigned from the customer text
   alone; the historical thread was only used to confirm, never to add information the text does not carry.
5. **Keyword tuning.** Keywords were edited against the dev set and against per-keyword precision audits on the whole
   pool (random samples of the messages each keyword matches), then frozen and scored once on the 150 held-out rows.
   Two systematic fixes: tweets use curly apostrophes (`isn’t`) as often as straight ones, so every apostrophe keyword
   exists in both forms; and a few deliberately overlapping keywords (`download` + `downloads`, `charg` + `charged`,
   `suggested` + `suggested tracks`) act as weights so that decisive phrases beat generic co-occurring words.

## 2. Cluster table (k-means, k = 25, ordered by size)

| cluster | share | top terms (TF-IDF centroid) | mapped intent(s) |
|---|---:|---|---|
| 12 | 31.4 % | song, like, playlists, fix, add, albums, want, does, love, thank, need, really | catch-all: content, feature, playlist, other |
| 16 | 7.4 % | premium, charged, student, account, premium account, subscription, month, card, hulu | billing_or_charge, subscription_or_plan |
| 2 | 6.9 % | songs, playlist, song, songs playlist, add, shuffle, downloaded, playing, download | playlist_or_library, playback_or_app_bug, download_or_offline |
| 1 | 6.1 % | help, account, log, facebook, can't, hacked, login, can't log, facebook account, password | login_or_password, account_hacked_or_security |
| 21 | 6.0 % | app, iphone, android, ios, desktop app, phone, ios app, android app, fix, updated | playback_or_app_bug (+ iPhone X → feature_request_or_feedback) |
| 0 | 5.4 % | music, apple music, apple, playing, play, downloaded, playing music, listening | mixed: playback, feature (Apple Watch), download |
| 9 | 4.1 % | family, plan, family plan, premium, premium family, family account, invite, members | subscription_or_plan |
| 20 | 3.2 % | available, play, song, can't play, play song, available india, won't | content_or_availability (+ playback) |
| 8 | 3.1 % | album, new album, new, available, taylor, album available, isn't | content_or_availability |
| 18 | 2.9 % | email, account, password, email address, changed, reset, hacked, reset password, changed email | login_or_password, account_hacked_or_security |
| 17 | 2.6 % | listen, listen music, can't listen, want listen, songs, trying listen | content_or_availability, playback_or_app_bug |
| 10 | 2.5 % | update, iphone, update app, update iphone, support, iphone update, update payment | feature_request_or_feedback (iPhone X), playback (update broke it) |
| 15 | 2.4 % | free, premium, account, trial, ad, free trial, ad free, free account, says, paid, says free | billing_or_charge (paid but Free), subscription_or_plan (ads, trial) |
| 7 | 2.2 % | thanks, presale, code, presale code, help, help thanks, dear | other |
| 3 | 2.0 % | getting, error, getting error, message, trying, error message, i'm getting | playback_or_app_bug (+ plan/billing errors) |
| 14 | 2.0 % | having, issues, having trouble, trouble, having issues, having problems, logging | generic "having issues" — every intent |
| 24 | 1.9 % | artist, artist page, page, profile, song, wrong artist, artist profile, wrong, artist account | **metadata_or_artist_issue** (+ feature: block an artist) |
| 4 | 1.5 % | need, need help, help, account, help account, dm, asap, talk | other (ambiguous) |
| 5 | 1.2 % | discount, student discount, student, charged, premium, month, hulu, card, price, school | billing_or_charge, subscription_or_plan |
| 11 | 1.1 % | dm, sent dm, sent, check, check dm, reply dm, reply, answer | other |
| 22 | 1.0 % | reputation, reputation available, available, reputation album, taylor, coming, waiting | content_or_availability |
| 6 | 0.9 % | player, web player, web, play, work, working, chrome, firefox | playback_or_app_bug |
| 19 | 0.9 % | discover, discover weekly, weekly, weekly playlist, playlist, week, songs, stop | playlist_or_library |
| 23 | 0.7 % | customer, customer service, service, number, service number, great customer, worst customer | other (support-process praise/complaints) |
| 13 | 0.6 % | watch, apple watch, apple, watch app, app apple, apple music, support, release | feature_request_or_feedback |

Reading: the clusters recover every draft intent (billing/plan, login/hacked, app bugs, family plan, content, downloads,
Discover Weekly, feedback/platform requests, thanks/DM/other) and surface one theme the draft had no home for:
cluster 24 — content that exists but is **wrong** (wrong artist page, misspelled names, wrong version) together with
artists asking about their own catalogue. In the 200 random openers this theme occurs 8–10 times (4–5 %) and in the
150 calibration rows 4 times (2.7 %); its historical resolution ("thanks for the heads up, we'll pass it to the right
team" / Artist Support form) differs from the "missing content" resolution ("licensing … fingers crossed … info about
Spotify content here"), so it became the twelfth intent.

## 3. Final taxonomy (12 intents) and boundary rules

Ids are unchanged from the CONTRACT draft except for the added `metadata_or_artist_issue`. No id was renamed or
merged: every draft intent is ≥ 2 % in the hand labels except `account_hacked_or_security` (4.0 % in the hand labels,
2.2 % by keywords — rarer but escalation-critical) and `non_english` (0 % inside the English pool by construction,
2.1 % of all openers via the `language` flag).

| # | id | default decision | one-line definition |
|---|---|---|---|
| 1 | non_english | auto_handle (language redirect) | message not in English (Spanish, Portuguese, Indonesian, Tagalog, French, German, Dutch, …) |
| 2 | account_hacked_or_security | escalate · account_security | third party in the account: unknown device, foreign playlists, email/password changed by someone else |
| 3 | billing_or_charge | escalate · billing_dispute | money moved or failed: unexpected/double/continued charge, paid-but-Free, payment failing, refund, wrong price |
| 4 | login_or_password | escalate · needs_account_lookup | cannot log in/sign up, forgot password/username, Facebook login, logged out repeatedly, account merge/close, username |
| 5 | download_or_offline | auto_handle | downloads vanish/won't download, offline mode, download limit, storage/SD/cache, app uses mobile data |
| 6 | metadata_or_artist_issue | auto_handle | content present but wrong (artist, title, cover, version, lyrics, duplicates) or an artist about their own catalogue/profile |
| 7 | playlist_or_library | auto_handle | own playlists/saved music gone or changed, playlist how-tos, Discover Weekly/Daily Mix/Release Radar/Wrapped/radio, recommendations |
| 8 | content_or_availability | auto_handle | artist/album/song/podcast missing, greyed out, "not available", region blocked, "put X on Spotify", country launch |
| 9 | playback_or_app_bug | auto_handle (troubleshoot) | crashes, won't play/skips/pauses, errors, no sound, devices (Connect, Bluetooth, consoles, TV), update broke it, "fix your app" |
| 10 | subscription_or_plan | auto_handle (info) | Premium/Student/Family/trial/bundle questions, eligibility & verification, invites, upgrade/cancel, offers, account country, Free-tier limits |
| 11 | feature_request_or_feedback | auto_handle (acknowledge) | suggestions and opinions where nothing is broken: features, UI, platform requests (iPhone X, Apple Watch, Siri), ad content, curation |
| 12 | other | escalate · ambiguous_or_media_only | thanks/praise, "check your DMs", screenshot-only, generic "help", venting with no issue, support-process complaints, presale codes, jobs, off-topic |

The YAML order above is deliberate: the `simple_keyword` baseline resolves ties towards the *earlier* intent, so
escalation-critical and specific intents come first and `other` last (it only wins when nothing else matches).

### Boundary rules (apply in this order)

1. **Not English** → `non_english`, whatever the topic (record the topic in `secondary_intent`). A foreign song title,
   artist name or hashtag inside an English sentence does not count.
2. **Any third party in the account** ("hacked", device I don't own, playlists that aren't mine, email changed by
   someone) → `account_hacked_or_security`, even when the customer also cannot log in.
3. **Money** — an amount charged, charged after cancelling, charged full price after a Student/Family discount lapsed,
   double charge, paid but still Free/no Premium, payment or payment-details failing, refund → `billing_or_charge`,
   even when the root cause is a plan or eligibility problem. *"charged but no Premium" → billing_or_charge.*
   Premium status missing with **no** payment mentioned → `subscription_or_plan`.
4. **Access** — cannot log in or sign up for any reason (wrong password, reset mail missing, CSRF/"offline" error,
   deleted Facebook), forgot username/email, logged out repeatedly, merge/close an account, username questions →
   `login_or_password`. *"can't log in after deleting Facebook" → login_or_password.* Playlists **and** Premium both
   "vanished" after re-logging in is the wrong-account pattern → `login_or_password`; playlists gone alone →
   `playlist_or_library`.
5. **Downloads/offline** — if the customer mentions downloads, offline mode, "says I'm offline", storage or data
   usage → `download_or_offline`, even when songs are described as greyed out. *"songs greyed out" →
   content_or_availability unless the customer talks about downloads.*
6. **Wrong vs missing content** — content that is present but wrong (credited to the wrong artist, misspelled, wrong
   cover/version/lyrics, duplicate artist pages) or an artist/label/podcaster asking about their own release, profile,
   verification or Spotify for Artists → `metadata_or_artist_issue`. Missing, greyed out, "not available", removed,
   region-locked, "put X on Spotify", "when do you launch in <country>" → `content_or_availability`.
   *"Spotify in my country" → content_or_availability.* Editorial placement wishes ("put X in the Pop playlist",
   "categorise New Releases") → `feature_request_or_feedback`.
7. **Own library vs catalogue** — songs missing from *my* playlist/library, Discover Weekly/Daily Mix/Release Radar
   /Wrapped/radio behaviour, recommendation quality, playlist how-tos → `playlist_or_library`. A playlist that will not
   *play* → `playback_or_app_bug`.
8. **Free-tier limits** — shuffle-only, too many ads, Suggested Tracks in my playlist, skip limits →
   `subscription_or_plan` (the historical reply explains the Free service and links the Premium trial). *"shuffle only
   / too many ads" → subscription_or_plan.* A complaint about an ad's *content* (offensive, wrong language) →
   `feature_request_or_feedback`; an ad playing on a Premium account → `billing_or_charge` if a payment is mentioned,
   else `subscription_or_plan`.
9. **Broken vs wanted** — something malfunctions (crash, error, no audio, won't play, device won't connect, search or
   sharing broken, "fix your app") → `playback_or_app_bug`; nothing is broken but the customer wants a change
   (feature, layout, platform, "bring back the old version", "your Roku app is bad") → `feature_request_or_feedback`.
   iPhone X screen support and Apple Watch app requests are feature requests; "the update broke X" is a bug.
10. **Plan questions** — how to upgrade/downgrade/cancel, Student/Family eligibility and verification, family invites
    failing, Hulu/telco bundles, offers and pricing, changing the account country → `subscription_or_plan`.
11. **Nothing inferable** — screenshot/link only, "help", "explain this", "check your DMs", thanks, venting or churn
    threats with no described issue, complaints about the support process itself, presale codes, jobs, sponsorship →
    `other`. Label from the customer text alone; if the text carries no describable issue, it is `other` even when the
    historical thread reveals what it was about.
12. **Two issues in one tweet** — the primary intent is the issue the customer asks to have solved; when the message
    disputes money, money wins (rule 3); otherwise the first-stated issue wins and the second goes to `secondary_intent`.

## 4. Estimated distribution

Keyword heuristic = final v1 keywords over the 26,877 exact-deduplicated English openers (the sampling pool).
Hand-labelled = the 150 held-out calibration rows (uniform sample); the 100 dev rows are shown for context.

| intent | keyword bucket (pool) | hand-labelled 150 | dev 100 | 250 combined |
|---|---:|---:|---:|---:|
| playback_or_app_bug | 9.9 % | 15.3 % (23) | 14 | 14.8 % |
| feature_request_or_feedback | 7.7 % | 12.7 % (19) | 14 | 13.2 % |
| content_or_availability | 13.0 % | 12.0 % (18) | 13 | 12.4 % |
| subscription_or_plan | 14.9 % | 12.7 % (19) | 10 | 11.6 % |
| other | 3.9 % (+15.0 % no keyword hit) | 13.3 % (20) | 9 | 11.6 % |
| billing_or_charge | 10.1 % | 6.7 % (10) | 18 | 11.2 % |
| login_or_password | 8.7 % | 7.3 % (11) | 11 | 8.8 % |
| download_or_offline | 3.7 % | 8.0 % (12) | 1 | 5.2 % |
| playlist_or_library | 8.7 % | 4.7 % (7) | 3 | 4.0 % |
| account_hacked_or_security | 2.2 % | 4.7 % (7) | 3 | 4.0 % |
| metadata_or_artist_issue | 2.0 % | 2.7 % (4) | 4 | 3.2 % |
| non_english | 0.2 % of the English pool | 0 | 0 | 0 (2.1 % of all openers carry `language == "other"`) |

Where the two columns disagree the keyword census is the biased one: `playlist_or_library` and `subscription_or_plan`
absorb generic words ("playlist", "premium") that appear as context in other complaints, while vague bug reports and
"other" messages contain no keywords at all (the 14.9 % no-hit slice is mostly playback bugs, feedback and other).

## 5. Keyword baseline (`simple_keyword`, CONTRACT §15.1)

Classifier: intent with the most keyword hits; keywords shorter than five characters match on word boundaries, longer
ones as substrings; ties → earlier intent in the YAML; no hit → `other` (implementation:
`cadence.data.sample.assign_bucket`). 1,203 keywords over 12 intents. Descriptions are kept under 200 characters and
the first example under 80 because `cadence.agent.prompts.taxonomy_block` embeds them verbatim in the system prompt;
the full boundary rules live in §3 above.

| set | n | accuracy | macro-F1 (labels present) | macro-F1 (all 12 ids) |
|---|---:|---:|---:|---:|
| dev (tuned on) | 100 | 0.820 | 0.806 | 0.739 |
| **held-out calibration** | **150** | **0.833** | **0.839** | 0.769 |

`non_english` has zero support and zero predictions in both sets, which is why the 12-id macro-F1 is lower (sklearn
scores an absent class as 0). Per-class F1 on the 150 held-out rows: account_hacked_or_security 1.00,
subscription_or_plan 0.88, download_or_offline 0.87, content_or_availability 0.86, login_or_password 0.86,
metadata_or_artist_issue 0.86, other 0.86, playback_or_app_bug 0.82, playlist_or_library 0.82, billing_or_charge 0.73,
feature_request_or_feedback 0.67. The remaining errors are mostly two-issue tweets ("can't log in and my card is
charged"), feature requests phrased like bug reports, and one-word cues ("ad", "$") that fire in the wrong context —
exactly the cases the LLM agent should win on. These numbers are the expected `simple_keyword` baseline; the golden set
is a stratified (not uniform) sample, so its numbers will differ.

## 6. Deliberately left out

- **A separate `family_plan` intent** (cluster 9, 4 %): its resolution is the same as other plan problems (explain the
  same-address rule or DM for an account lookup), so it stays inside `subscription_or_plan`.
- **`student_discount`**: splits cleanly into eligibility (`subscription_or_plan`) and being charged full price
  (`billing_or_charge`); a third bucket would only re-encode that boundary.
- **`ads`**: too small alone and already covered by rule 8.
- **`campaign` intents (iPhone X, Apple Watch, Taylor Swift's reputation, "Spotify in India")** — they are big in
  Oct–Dec 2017 (≈ 1 % each) but transient; they live in `feature_request_or_feedback` and `content_or_availability`
  and are only encoded as keywords.
- **`praise_or_thanks` and `check_dm`** as intents: both are `other`; splitting them would help the classifier but
  not the agent, whose behaviour (acknowledge / escalate as ambiguous) is already fixed by the escalation policy.
- **`support_process_complaint`** ("worst customer service", "give me a phone number", 0.7 %): kept in `other`
  because the right action is the `high_frustration_or_churn` / `asks_for_human` escalation, not a distinct reply.
- **`spam_or_off_topic`** and **`legal`**: too rare to estimate (< 0.5 %); handled by the `out_of_scope` and
  `legal_or_safety` reason codes inside `other`.
- **Sentiment and escalation** are separate fields of the golden schema, not intents.
