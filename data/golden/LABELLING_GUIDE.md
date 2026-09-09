# Golden-set labelling guide (Cadence / @SpotifyCares)

You are labelling customer tweets sent to @SpotifyCares in 2017. Every candidate in `data/golden/candidates.jsonl`
carries the cleaned customer text (`text`), the raw text (`text_raw`), the first brand reply and the full public
thread. **Label from the customer text alone.** Use the thread only to confirm a reading the text already supports;
if the text carries no describable issue, the label is `other` even when the thread reveals what it was about — the
agent under evaluation only sees the text.

Reference documents: `config/intents.yaml` (definitions + three real examples per intent), `docs/TAXONOMY.md` §3
(boundary rules), `config/escalation.yaml` and CONTRACT §5 (escalation policy), `docs/BRAND_VOICE.md` (what the
brand historically did with each intent).

## 1. Fields (one JSON object per candidate, schema CONTRACT §7 `gold` / `annotations`)

| field | type | rule |
|---|---|---|
| `intent` | one of the 12 ids in `config/intents.yaml` | the single primary intent (decision tree in §2) |
| `secondary_intent` | id or `null` | a second, clearly stated issue in the same tweet; also the underlying topic of a `non_english` tweet when you can read it. `null` otherwise — do not invent one |
| `should_escalate` | bool | `true` when a human must take the case (§3); `false` when a fully grounded public reply can go out unreviewed |
| `escalation_reason_code` | one of the 8 codes or `null` | exactly one primary code when `should_escalate` is `true`, `null` otherwise. Precedence in §3 |
| `sentiment` | `positive` · `neutral` · `frustrated` · `angry` | rubric in §4 |
| `media_only` | bool | `true` when the tweet has no describable content beyond a link/screenshot token, a greeting, emoji or a bare "help/explain this" (§5) |
| `notes` | short free text | the cue you used, especially for borderline calls ("charged full price after student lapse → billing"; "two issues, login first") |

## 2. Intent decision tree (walk top to bottom, stop at the first match)

1. **Is the tweet written in a language other than English** (a full sentence, not just a song/artist name or
   hashtag)? → `non_english`; put the underlying topic in `secondary_intent` if you can read it.
2. **Is there a third party in the account?** "hacked", "hijacked", a device/phone/city they do not recognise,
   playlists or saved music that are not theirs, email or password changed by someone else, strangers on their
   plan → `account_hacked_or_security` (even if they also cannot log in).
3. **Is money involved?** An amount charged (unexpected, double, after cancelling, full price after a
   Student/Family discount lapsed, wrong currency/amount), paid but still Free / no Premium, payment or
   payment-details failing, refund requests, gift card/checkout failing → `billing_or_charge`. This wins even when
   the root cause is a plan problem. A missing Premium status **without** any payment mentioned is not money → go on.
4. **Is it about getting into the account?** Cannot log in or sign up for any reason (wrong password, reset mail
   never arrives, CSRF/"offline" error, deleted or unwanted Facebook link), forgot username/email, logged out
   repeatedly, two accounts to merge or one to close, username questions → `login_or_password`. Playlists **and**
   Premium both gone after re-logging in → `login_or_password` (wrong-account pattern).
5. **Does the customer mention downloads, offline mode, "it says I'm offline", storage/SD card/cache or mobile
   data?** → `download_or_offline`, even if songs are "greyed out".
6. **Is content present but wrong** (credited to the wrong artist, misspelled artist/song, wrong cover, wrong
   version plays, wrong lyrics, duplicate/merged artist pages), **or is the writer an artist/label/podcaster asking
   about their own release, profile, verification or Spotify for Artists?** → `metadata_or_artist_issue`.
7. **Is it about the customer's own playlists or library, or a personalised playlist?** Playlists/saved songs gone
   or changed, playlist how-tos (reorder, cover, followers, collaborative), Discover Weekly / Daily Mix / Release
   Radar / Wrapped / Time Capsule / radio questions, recommendation quality → `playlist_or_library`. (A playlist that
   will not *play* is step 9.)
8. **Is content missing from the catalogue** — artist/album/song/podcast not on Spotify, greyed out, "not
   available", removed, region-locked, "put X on Spotify", "when do you launch in <country>"? →
   `content_or_availability`.
9. **Is something broken?** Crashes, freezes, won't play / skips / pauses, error messages, no sound or volume
   problems, Bluetooth/Spotify Connect/speaker/car/console/TV problems, web player or desktop client not working,
   search or sharing broken, an update that broke things, "fix your app" → `playback_or_app_bug`.
10. **Is it a plan question or a Free-tier limit?** Premium/Student/Family/trial/bundle questions, eligibility and
    verification (student status, family address), family invites failing, upgrade/downgrade/cancel how-tos, offers
    and pricing, account country, too many ads, shuffle-only, Suggested Tracks in my playlist, skip limits →
    `subscription_or_plan`.
11. **Does the customer want something changed although nothing is broken?** Feature ideas, UI/design complaints,
    platform requests (iPhone X layout, Apple Watch, Siri, Nintendo Switch), "bring back the old version", ad
    *content* complaints, editorial/curation suggestions → `feature_request_or_feedback`.
12. **Otherwise** → `other`: thanks/praise, "check your DMs", screenshot/link only, bare "help", venting or churn
    threats with no described issue, complaints about the support process itself (phone number, chat, response
    time), presale codes, jobs, sponsorship, off-topic.

Two issues in one tweet: money wins (step 3); otherwise the first-stated issue is primary and the second goes to
`secondary_intent`. When you hesitate between two intents for more than a few seconds, pick the one whose
historical resolution (see `docs/BRAND_VOICE.md` §6) would actually help the customer and write the alternative in
`notes`.

## 3. Escalation (CONTRACT §5)

`should_escalate = false` ("auto_handle") only when a reply that is **fully grounded in historical brand practice**
(a self-serve step, a help-article link, an acknowledgement, the language redirect) can be posted without a human
looking at the account, moving money, making a policy exception or taking legal/PR exposure. Everything else is
`true` with exactly one primary reason code, chosen in this order of precedence:

1. `legal_or_safety` — legal threats, lawyers, GDPR/data requests, harassment, self-harm, discrimination, press.
2. `account_security` — any `account_hacked_or_security` tweet; also credentials or card details posted publicly.
3. `billing_dispute` — any `billing_or_charge` tweet (charges, refunds, payment failures, price disputes).
4. `high_frustration_or_churn` — an explicit churn threat ("cancelling if…", "switching to Apple Music"), profanity
   aimed at the brand, repeated contact ("third time", "still no reply"), a request for a human/phone, or a
   PR-risk complaint — when none of 1–3 applies. A merely irritated tone is **not** enough.
5. `needs_account_lookup` — the fix requires looking at the account "backstage": login recovery without generic
   steps, a family invite that fails for this customer, Premium not applied, missing purchase, eligibility for this
   person, "how long have I been a member".
6. `ambiguous_or_media_only` — nothing actionable in the text: screenshot/link only, "help", "explain this",
   "check your DMs", truncated tweets.
7. `out_of_scope` — not something the brand can act on: politics, spam, other companies' products, jokes with no
   request.
8. `low_confidence` — **never assigned by annotators**; it is reserved for the model's confidence threshold.

Default decisions per intent (`config/intents.yaml`) are a starting point, not the answer: `login_or_password` is
`auto_handle` when generic reset steps suffice; `subscription_or_plan` and `playlist_or_library` escalate when the
problem is specific to this account; any intent escalates when a rule above fires.

### Worked examples (real candidate texts)

| # | text | intent | escalate · reason | sentiment | why |
|---|---|---|---|---|---|
| 1 | "I cancelled in January, yet I have still been charged £9.99 per month since then. 😳😳" | billing_or_charge | true · billing_dispute | frustrated | continued charge after cancelling; money → human with account access |
| 2 | "My account has been hacked, email changed and I'm locked out. Can you help?" | account_hacked_or_security | true · account_security | frustrated | third party changed the email; security beats login (step 2 before step 4) |
| 3 | "why have all my downloaded albums suddenly been removed??? Version 8.4.23.784. Android 7." | download_or_offline | false · null | frustrated | the historical reply is the self-serve "Downloads unexpectedly removed" steps; no account access needed |
| 4 | "please release GOT7 \"7 for 7\" album" | content_or_availability | false · null | neutral | grounded template ("fingers crossed … info about Spotify content here") |
| 5 | "Help, please? <url>" | other (`media_only: true`) | true · ambiguous_or_media_only | neutral | the only content is a screenshot; a human must look |
| 6 | "Check your DMs" | other (`media_only: false`) | true · ambiguous_or_media_only | neutral | text but no describable issue; the agent cannot read DMs |
| 7 | "hello! I'm subscribed to student premium but somehow it's charging me without the discount? (Its been 2 months)" | billing_or_charge (secondary: subscription_or_plan) | true · billing_dispute | neutral | disputes an amount charged even though the cause is a lapsed discount — money wins |
| 8 | "I cannot add additional member to my family premium sunscription account. Any resolution?" | subscription_or_plan | true · needs_account_lookup | neutral | a failure specific to this account (historically: "DM us the accounts' email addresses"). Contrast the generic question "how do I add my sister to the family plan if she lives at another address?" → subscription_or_plan, `false` (same-address rule is public information) |
| 9 | "Hi guys. Lost all my album downloads again. Must be 4th time. I'm on the verge of cancelling premium unless this is sorted" | download_or_offline | true · high_frustration_or_churn | frustrated | the fix is self-serve, but the explicit churn threat plus repeated contact forces a human; note "downloads steps would otherwise auto-handle" |
| 10 | "I deleted my Facebook account without realising my Spotify account was connected. Now I can't access my Spotify account, How can I change this as it is a premium account." | login_or_password | true · needs_account_lookup | neutral | no email/password to reset with; recovery needs the account team |
| 11 | "im trying to rest my password but it keeps saying code is invalid" | login_or_password | false · null | neutral | the generic-steps exception: historically answered with "try incognito mode / clear cache and cookies"; no account lookup needed |
| 12 | "Someone has hijacked my Spotify Premium account, and I am unable to login. Can I please get some assistance to get this fixed?" | account_hacked_or_security (secondary: login_or_password) | true · account_security | frustrated | both a security and an access problem; security has precedence for both intent and reason code |

Further precedence cases: "Wow, . It's actually bullshit that you automatically reactivated my long-since deleted
Facebook account without my consent." → login_or_password, `true · high_frustration_or_churn`, angry (profanity aimed
at the brand). "you guys need better customer service. This will be the third time I've talked to you without anyone
helping me." → other, `true · high_frustration_or_churn`, frustrated (repeated contact). "hola, no puedo iniciar sesión
en mi cuenta de spotify premium" → non_english (secondary login_or_password), `false` — the language redirect is the
grounded reply; the human follow-up happens in the language channel.

## 4. Sentiment rubric

| label | cues | examples |
|---|---|---|
| `positive` | thanks, praise, joy, playful excitement, hearts | "they actually care. thanks xoxo", "love the service! wanted to make a suggestion…" |
| `neutral` | a plain question or report, polite or matter-of-fact, mild emoji (🙂, 😅), a single "?" or "!" | "how do I switch my Premium account to a Family Account!?", "Is Taylor Swift's Reputation album going to be available at midnight?" |
| `frustrated` | irritation without hostility: "again", "still", "ugh", "seriously", "why is it so hard", multiple ?!?!, 😩😭🙄, mild profanity not aimed at the brand ("wtf is going on"), a conditional churn threat | "My downloads were dumped, 2nd time this week, 4th time this month. 😡", "I cancelled in January, yet I have still been charged" |
| `angry` | hostility aimed at the brand: insults, profanity at "you/Spotify", ALL-CAPS rants, "worst", "scam", "pathetic", accusations of theft, threats | "fuck u for telling me i get 30mins of ad free music…", "Are you trying to rob us?", "IS THE ABSOLUTE WORST !!" |

Label the tone of the text, not the severity of the problem: a hacked account reported calmly is `neutral`; a
misspelled song title reported with insults is `angry`. Sarcasm ("Great work!", "thanks for ruining my day :-)") is
`frustrated`.

## 5. Special cases

- **Media-only / screenshot-only.** `text` is empty, only `<url>` tokens, only emoji, or a bare "help", "explain",
  "this", "wtf is this <url>", "@user <url>" → intent `other`, `media_only: true`, escalate `ambiguous_or_media_only`.
  If the text names the issue and *also* attaches a screenshot ("web player stuck in a commercial <url>") the
  screenshot is supporting material: `media_only: false`, label the issue normally.
- **Truncated tweets** ("…", "1/2", cut mid-sentence, "-- Lucas" device follow-ups): label what is inferable from
  the visible text; if nothing is, `other` + `ambiguous_or_media_only`. Note "truncated" in `notes`.
- **Non-English.** Intent `non_english` for any sentence-level non-English text (Tagalog/Taglish and Indonesian mixed
  with English words count; check `text_raw` when in doubt). Put the topic in `secondary_intent`. Sentiment is still
  labelled. A foreign song title or hashtag inside English is not `non_english`.
- **Continuations and replies to the brand** ("Sent you a DM", "resolved thank you", "Ok will do") → `other`;
  thanks are `positive`, `should_escalate: false`.
- **Credentials or card details in the tweet** (`__email__` tokens, "my password is …") → escalate
  `account_security` and note "private info posted".
- **Legal/press language** → `legal_or_safety` regardless of intent.
- **Campaign tweets** ("UPDATE FOR IPHONE X", "where is #reputation") are ordinary feature/content tweets; label
  them normally even though they repeat across the set.

## 6. Sampling (how the candidates were drawn)

Candidates come from `python scripts/03_sample_candidates.py --per-bucket 25 --min-random-share 0.28`
(`cadence.data.sample`, `SEED = 42`), run after the v1 taxonomy was frozen. Full procedure in
`docs/SAMPLING_NOTE.md`; the numbers of that run:

| step | rows |
|---|---:|
| SpotifyCares openers (`spotify_openers.parquet`) | 27,627 |
| `language == "en"` and at least one brand reply | 27,056 |
| exact-duplicate `customer_text` removed (earliest tweet kept) | 26,877 |
| of which `short_or_media` (`n_words <= 3` or bare `<url>`) | 435 |

Every pooled message belongs to at most one keyword bucket `kw:<intent_id>` (the intent with the most v1 keyword hits;
ties → earlier intent; no hit → reachable only through `random`). Pool sizes with the v1 keywords: no keyword hit
4,038 · subscription_or_plan 4,010 · content_or_availability 3,497 · billing_or_charge 2,715 · playback_or_app_bug
2,648 · playlist_or_library 2,334 · login_or_password 2,325 · feature_request_or_feedback 2,076 · other 1,058 ·
download_or_offline 992 · account_hacked_or_security 591 · metadata_or_artist_issue 543 · non_english 50 (the pool is
English-flagged, so this bucket holds mixed-language Tagalog/Indonesian/Spanish tweets; the 571 openers flagged
`language == "other"` are outside the pool and can be added separately if `non_english` needs more support).

Draw order: 15 `short_or_media` (probes for `ambiguous_or_media_only`), then up to 25 per keyword bucket in YAML order,
then a uniform `random` slice sized so that at least 28 % of all candidates are unstratified. Within each pass the draw
round-robins over calendar months and rejects near-duplicates (`rapidfuzz.fuzz.ratio > 92`), so templated campaign
tweets appear once. The final list is shuffled and given ids `c_001`… so annotators never see bucket runs.

Result: **438 candidates from 438 distinct threads** — `random` 123 (28.1 %), 25 in each of the 12 `kw:` buckets
(5.7 % each), `short_or_media` 15 (3.4 %). 19 calendar months (Aug 2015 – Dec 2017): 115 / 116 / 103 candidates in
Oct / Nov / Dec 2017, 48 in Sep 2017. 12.1 % contain a link (openers overall 14.6 %); 36.1 % come from multi-turn
threads (overall 28.1 %). `sampling_bucket` is a stratum, **not** a label — label every candidate from scratch. The
`random` slice is the unbiased sample for estimating the true intent distribution; the keyword strata guarantee ≥ 25
examples of every intent for per-class metrics.

## 7. Process

Two annotators (`annotations_a.jsonl`, `annotations_b.jsonl`) label independently; disagreements on `intent` or
`should_escalate` are resolved in `adjudication.jsonl` with a one-line rationale, and the resolved row becomes
`gold`. Aim for 150–250 golden examples; drop candidates that are exact re-tweets of an already-labelled text. Record
agreement (raw and Cohen's κ) for `intent` and `should_escalate` in `results/eval_summary.json → annotator_agreement`.
