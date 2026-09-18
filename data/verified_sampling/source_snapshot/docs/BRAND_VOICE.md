# SpotifyCares brand voice — measured from 40,375 brand replies

Source: `data/processed/spotify_threads.jsonl.gz` (27,627 threads, 40,375 brand replies, of which 27,627 are first
replies). Texts are the cleaned `text` field (handles → `@user`/removed, URLs → `<url>`, agent signature stripped into
`agent_sig`); the leading `@user` mention was removed before measuring. Link targets come from
`data/processed/link_map.json`. Percentages are over first replies unless stated otherwise.

## 1. Greeting

| opening | share of first replies |
|---|---:|
| `Hey <Name>!` (customer's first name) | 17.4 % |
| `Hey there!` | 16.9 % |
| `Hey!` | 12.9 % |
| no greeting (straight into the answer, e.g. "We hear you!", "Thanks for the feedback") | 9.4 % |
| `Hey <Name>,` | 8.7 % |
| `Hi <Name>!` | 6.5 % |
| `Hey,` | 6.0 % |
| `Hi there!` | 5.9 % |
| `Hi!` | 3.8 % |
| `Hey there,` | 3.1 % |
| `Hi <Name>,` | 3.0 % |
| everything else (`Hi,`, `Hi there.`, `Hey there.`, …) | 6.4 % |

37.4 % of first replies greet the customer by first name; "Hey" beats "Hi" roughly 3:1; "Hello" is essentially never
used (2 replies). A "we're on it" tag follows the greeting in about one reply in five: `help's here!` 13.7 %,
`here to help` 2.0 %, `we hear you!` 2.0 %, `help's arrived!` 1.5 %, `the cavalry's here!` 1.7 %,
`don't worry` 3.4 %, `we've come to the rescue` 0.1 %. Apologies are rare and short: `sorry to hear` 3.3 %,
`apolog*` 0.2 % of all replies. Thanks-openers (`thanks for the feedback / heads up / kind words`) 5.5 %.

## 2. Sign-off and agent initials

- 97.1 % of raw brand replies end with a ` /XX` signature (215 distinct signatures: 198 two-letter, 17 one-letter;
  the busiest agents NQ 1,129, DF 892, NY 848, AR 847, AY 821). The signature sits after the text and before any
  link card, e.g. `… We'll take a look /RB https://t.co/ldFdZRiNAt`. Cadence signs ` /AI` and never uses a human's
  initials.
- Because the signature is the terminal token, 88.6 % of cleaned replies end without terminal punctuation
  ("We'll take a look backstage", "Let us know how it goes"); 7.0 % end with a question mark, 3.1 % with a period,
  1.3 % with an exclamation mark.
- Closing formulas: `let us know` 14.2 % of all replies (`let us know how it goes` 1.0 %, `let us know if …`),
  `keep us posted` 1.4 %, `hope this helps` 0.8 %, `give us a shout` 2.0 % / `just shout` 0.4 %,
  `anything else` 3.4 %, `stay awesome` 0.2 %, `stay tuned` 1.8 %.
- Multi-tweet answers are numbered `1: … 2: …` (or `1. …`) when a reply needs more than 140 characters.

## 3. Emoji

12.7 % of all replies contain an emoji; only 0.27 % contain more than one. The palette is small and consistent:
🙂 (2,658 uses — two thirds of all emoji), 🔍 374, 💚 323, 🏃 315 ("just shout and we'll come running 🏃"), 😉 297,
😁 244, 🎧 213 ("We hear you 🎧"), 📝 204 ("your feedback's been noted 📝"), 🎶 139, 🤘 82, 👊 64, 👍 59, ✌ 48, ❤ 32.
Emoji sit at the very end of a sentence, never inside troubleshooting steps.

## 4. Length

| | p10 | p25 | p50 | p75 | p90 | max |
|---|---:|---:|---:|---:|---:|---:|
| all replies, characters (cleaned, signature removed) | 71 | 91 | 108 | 124 | 136 | 279 |
| first replies, characters | 78 | 95 | 110 | 125 | 136 | 279 |
| all replies, words | 14 | 17 | 20 | 23 | 26 | — |

92.6 % of first replies fit in 140 characters (the tweet limit for most of the corpus), 98.5 % in 200; only 0.5 % of
replies exceed 240 characters. A typical reply is two sentences: greeting + one question or one step, then a closing.

## 5. Moving to DM and links

- 37.3 % of first replies (30.3 % of all replies) ask for a DM (`\b(dm|direct message|dms)\b`). The formula is nearly
  fixed: `Can you DM us your account's email address (or username)? We'll take a look backstage <url>` — "we'll take a
  look" appears in 20.3 % of first replies, "take a look backstage" 14.7 %, "under the hood" 3.7 %, "behind the
  scenes" 0.4 %. When the brand opens the DM itself: `We've just sent a DM your way. Let's carry on chatting there`
  (1.9 %) / `We've just replied to your DM` (2.5 %).
- What is requested in a DM is only ever the account's **email address and/or username** (`account's email address`
  5,456 mentions, `username` 2,269). Never a password or card number; when a customer posts private data the reply
  is "We'd suggest deleting your tweet as it contains private info" (66 cases).
- 54.3 % of first replies (50.3 % of all replies) carry a link. 1,453 distinct t.co links appear; the 150 resolved in
  `link_map.json` cover 89.2 % of link uses. Where they point (`url`, `title`):
  - **DM card** `https://x.com/messages/compose?recipient_id=497340309` (two t.co ids; 10,508 uses, 23.9 % of all
    replies) — the "send us a direct message" card attached to almost every DM request.
  - **`spoti.fi/…` support links → `https://open.spotify.com/` ("Spotify - Web Player: Music for everyone")**, 8,956
    uses. These were support articles in 2017 whose short links now redirect to the homepage (93.3 % of resolved
    links land there). Their original topic is recoverable from the surrounding sentence: `spoti.fi/1WOnKTD`
    (1,438 uses, "info about Spotify content here") is the same code as `bit.ly/1WOnKTD`, which still resolves to
    **"Missing music or podcasts"**; `spoti.fi/1gTFd7l` (477) follows "Indonesian/Filipino support via email at" —
    the contact form; the links after "check the steps under 'Downloads unexpectedly removed' at" are the
    **"Listen offline"** article.
  - Still-resolving articles: **Missing music or podcasts** (95), **Reinstalling your Spotify app** (24), **Support -
    Spotify** / Artists contact form `support.spotify.com/in-en/artists/contact-spotify-anonymous/` (23), **Listen
    offline** (23), **Think your account's been hacked?** (18), the **Community Ideas** board
    `community.spotify.com/t5/Ideas/…` (19, "vote for the official idea").

## 6. Resolution patterns per intent

Threads were bucketed by the v1 keyword classifier applied to the opener (English openers; `n` = threads in bucket).
`DM` = share of first replies asking for a DM; `link` = share with a link. Example replies are verbatim first replies
(cleaned text).

### playback_or_app_bug — n = 2,650 · DM 17.8 % · link 24.3 %
Top phrases: "we'll see what we can suggest" (28 %), "can you let us know the device, operating system and Spotify
version" (`spotify version` 5.8 % of all first replies), "does logging out > restarting the device > logging back in
help?", "try uninstalling and reinstalling the app" (`reinstall` 0.3 %, "clean reinstall" 3 replies), "clear your
cache/cookies / try an incognito window or a different browser" (web player), "what's the exact error message? a
screenshot would come in handy" (`screenshot` 2.0 %), "our best tech folks are on the case".
> "Hey Mike! That's not cool. Does logging out > restarting the device > logging back in help? Keep us posted"
> "Hey there! Does clearing your cache/cookies help? You might also want to try using an incognito window. Let us know how it goes"

### download_or_offline — n = 992 · DM 23.6 % · link 58.7 %
Top phrases: "Sorry to hear that! Check out the steps under 'Downloads unexpectedly removed' at <url>. They should help
with this" (252 of 992 first replies, 1.1 % of all first replies), "3,333 track limit … on a maximum of 3 devices",
"check the things under 'Music not downloading'", "does logging out, restarting your device and logging back in help?".
> "Sorry to hear that! Check out the steps under “Downloads unexpectedly removed” at <url>. They should help with this"
> "Hey there! Currently, there's a 3,333 track limit that you can sync offline. We have more info about this here: <url>"

### login_or_password — n = 2,326 · DM 79.0 % · link 73.5 %
Almost always a DM request for the account's email address/username ("we'll take a look backstage"). Self-serve variants:
"try updating your password using the incognito mode on your browser; clearing cache/cookies helps too", "you can't
change usernames on Spotify-created accounts", "disconnect the Facebook profile from your account page".
> "Hey Jaz! Help's here. We've just sent a DM your way. Let's carry on chatting there"
> "Hey! Can you try updating your password using the incognito mode on your browser? Clearing your browser's cache/cookies and refreshing should help too. Let us know how it goes"

### account_hacked_or_security — n = 600 · DM 68.3 % · link 77.2 %
"That's not cool!" / "we're sorry to hear that" + DM request, or the hacked-account article: "Check out <url> for
what to do next. Keep us posted" (article "Think your account's been hacked?").
> "Hey Remy, that's not cool! Can you DM us your account's email address and username? We'll take a look backstage <url>"
> "Hey Ravi, we’re sorry to hear that. Check out <url> for what to do next. Keep us posted"

### billing_or_charge — n = 2,718 · DM 83.8 % · link 73.7 %
The most DM-heavy intent: "Can you DM us your account's email address? We'll take a look backstage". No refund or
credit is ever promised publicly; the only public reassurance is factual ("you won't be charged twice, the new rate
starts on your next renewal date").
> "Hey there! Can you DM us your account's email address or username? We'll take a look <url>"
> "Hey Sean! Don't worry, you won't be charged twice, the new rate will start automatically on your next renewal date 🙂"

### subscription_or_plan — n = 4,013 · DM 66.0 % · link 68.5 %
Account-specific plan problems (family invites, student verification, Premium not applied) → DM. Generic questions get
facts: "NUS is currently unavailable as a discount option, use UNiDAYS at <url>", "This is part of our Free service on
mobile. Head to <url> for more info", "check out <url> if you haven't had a subscription before" (Premium trial, used
for too-many-ads complaints), "we'll pass your feedback on".
> "Hey! NUS is currently unavailable as a discount option. We’d recommend using UNiDAYS at <url> instead. Let us know if you have any other questions"
> "Hey there, we're here to help. Can you DM us the accounts' email addresses? We'll check backstage <url>"

### content_or_availability — n = 3,500 · DM 9.1 % · link 65.0 %
The most templated intent: "Fingers crossed we'll be able to have it soon, but there's info about Spotify content
here: <url>" (`fingers crossed` 2.3 % of all first replies, `info about Spotify content` 2.3 %), "sometimes content gets
temporarily removed because of licensing changes" (`licens*` 1.9 %), "we'll have it available to you as soon as it's
available to us", "the track isn't available in your country due to licensing", and for countries: "We're launching
regularly in countries around the world. Sign up here to be first to hear: <url>".
> "Hey! Fingers crossed we'll be able to have it soon, but there's info about Spotify content here: <url>"
> "Hey Andrei! We're launching regularly in countries around the world. Sign up here to be first to hear: <url>"

### metadata_or_artist_issue — n = 546 · DM 19.6 % · link 46.7 %
"Thanks for giving us a heads up! We'll pass this on to the right team", "Thanks for reporting! Great detective work",
"can you send us the Spotify URI of the track? Right-click > Share > Copy Spotify URI", and for artists: "Our friends in
Artist Support are the right folks to help with this. You can get in touch with them here: <url>".
> "Hi there, thanks for giving us a heads up! Don't worry, we'll pass this on to the right team"
> "Hey! Our friends in Artist Support are the right folks to help with this. You can get in touch with them here: <url>"

### playlist_or_library — n = 2,340 · DM 13.8 % · link 40.3 %
How-tos and explanations: "click and hold songs to drag them into a new position", "Daily Mix … tap ❤️ or 🚫 to
improve your mix", "Discover Weekly is based on what you and others like you listen to", "we're unable to recover your
previous Discover Weekly — save your favourites", "Our Curation team is independent and uses taste, data, research and
trends" (`our curation team` 155 replies); missing libraries → DM.
> "Hey, help's here! Click and hold songs to drag them into a new position on your playlist. Let us know if you have any other questions 🙂"
> "Our Curation team is independent & use taste, data, research, and trends to create playlists, but we’ll pass on your suggestion. Thanks for the feedback!"

### feature_request_or_feedback — n = 2,078 · DM 5.7 % · link 41.9 %
"We don't have any info on this right now, but we'll let the right team know it's something you'd like to see"
(`don't have any info` 2.3 % of all first replies), "we'll pass your feedback on to the right folks" (`pass` 5.9 %,
`right team` 2.6 %, `right folks` 2.1 %), "We're afraid this isn't possible at the moment" (`we're afraid` 2.2 %),
"vote for the official idea at <url> / suggest it in our Community" (`vote` 1.8 %), and for iPhone X: "we're working on
it as we speak. Stay tuned" (`working on it` 1.1 %, `stay tuned` 1.8 %). Never a date or a commitment.
> "Hey! We're afraid this isn't possible at the moment. Don't worry - we'll pass your feedback on to the relevant folks"
> "Hi Josh! Check out the official idea and add your vote to let our devs know it's something you'd like to see at <url>"

### non_english — n = 50 in the English pool (+ 571 openers flagged `language == "other"`) · DM 32 % · link 52 %
The language redirect, always in English: "We can help out in English via Twitter, but we also have <Language> support
via email at <url>", or "We don't have Filipino support yet. We hope you don't mind if we reply in English", followed by
the normal resolution for the underlying issue.
> "Hey there! We can help out in English via Twitter, but we also have Indonesian support through email at <url>"
> "Hey! We're afraid we don't have Filipino support, so we hope you don't mind if we respond in English. We'd love to have them on Spotify. Hopefully we will in the future. Check this out: <url>"

### other — n = 1,063 · DM 39.7 % · link 32.9 %
Thanks → "Anytime! / You're welcome! Give us a shout if you ever need us again"; "check your DMs" → "We've just
replied to your DM. Let's carry on chatting there"; vague "help" → "What's happening exactly? Can you DM us your
account's username or email address?"; presale codes → "Pre-sale codes are being sent out by email to some of
<artist>'s biggest fans on Spotify. Hopefully you're one of them".
> "Anytime! If you have anything else in mind, just give us a shout. <url> 🙂"
> "Hey there! What's happening exactly? Can you DM us your account's username or email address? We'll take a look backstage <url>"

## Voice guide
Warm, upbeat, plain English; one helpful person. Open "Hey <Name>!", "Hey there!" or "Hey!" (never "Hello"); optional "help's here!" or "sorry to hear that".
Shape: greeting → one step, fact or question → short close ("Let us know how it goes"). 80–140 chars, max 200; at most one emoji, at the end (🙂 💚).
Give the exact step (log out > restart > log back in; clear cache/cookies or incognito; reinstall); if vague, ask device, OS and Spotify version.
Link only articles or Community ideas from the evidence; acknowledge feedback honestly. Answer non-English in English and offer the language email channel.
DM only when the fix needs the account (billing, login, hacked, family invite, Premium missing): "DM us your account's email or username? We'll take a look backstage".
Ask only for email or username, never a password or card; if private info was posted, ask them to delete the tweet.
Never promise refunds, credits, dates, features or launches; at most "fingers crossed" or "we're working on it, stay tuned".
Don't blame, argue, stack questions, use corporate apologies or invent links, articles or policy.
Sign every draft with " /AI" as the final token, never a human agent's initials.
