# Independent blinded AI review notes

## Reviewer and scope

Reviewer: GPT-6 Astra xhigh independent postpilot regression review.
Reviewer type: AI. Method: independent_blind. This is not a human review.
All 18 customer/reply/evidence rows were read and assessed individually for present-day assistance under verified-support-review-v1. Identity fields were copied unchanged from the blind packet. Each row records an actual UTC rating timestamp.

## Sources inspected

- results/verified_postpilot_regression_v1/blind_packet.jsonl, including exact customer text, reply text, and supplied evidence.
- results/verified_postpilot_regression_v1/rubric.json.
- docs/BRAND_VOICE.md, used as a voice guide rather than authority for historical procedures.
- All 21 text snapshots in config/knowledge/snapshots/2026-09-18/: autoplay; collaborative-playlists; contact-us; create-playlists; explicit-content; family-plan; faulty-inaccurate-metadata; hulu-premium-bundle; listen-offline; missing-music-or-podcasts; reinstall-spotify; shuffle-play; sort-and-filter; spotify-connect; spotify-not-playing; spotify-wrapped; student-verification-not-working; suggest-feature; updating-spotify; username-and-display-name; where-spotify-is-available.
- src/cadence/eval/verified.py for rubric/schema shape. Provenance limitation: an initial first-75-lines read also exposed imports and small generic utility definitions, and a schema-field search returned generic metric/validation code lines beyond schema constants. These were not used as rating evidence. No system response-generation implementation, run-level predictions, mapping, labels, other ratings, aggregate results, or wider evaluation text sets were read.

The initial combined display truncated portions of the packet and snapshots. The first three packet rows and the two affected snapshots (missing-music-or-podcasts and reinstall-spotify) were then read separately to complete the visible source inspection. No network browsing was performed, and no current feature knowledge outside the allowed snapshots was used to supply product facts.

## Method and limits

Ratings concern the exact visible reply, not an inferred route or a predicted system identity. All seven flags were checked on every row. A valid official contact link does not alone make a reply resolve the customer's primary issue. Conversely, a scoped handoff for account takeover or a damage complaint is not automatically a wrong destination or a false claim that staff were contacted.

Wrong_issue includes material omission of an actionable question; each positive flag has its reason and major severity stated in the row rationale. Tone-only and limited clarification defects are recorded separately without inventing a factual or safety flag. Safe scores assess the visible claims and requests, not assumed routing correctness. No reply is credited with a performed action.

Social acknowledgments and handoffs are explicitly separate from useful resolution coverage even when their scoped quality is good. Clarification is credited only for relevant missing nonprivate context; known device details and literal versus figurative harm wording were considered. The two-device Family case needs a more targeted separate-account check before its exact clarification should ship.

The evidence is a frozen, supplied source set, not an exhaustive audit of every present-day Spotify feature. Historical brand examples and retrieved historical replies were not treated as current procedural authority. The frozen Connect snapshot supports a scoped lossless discussion, but not universal plan/device availability. There is no inference of routing gold from content safety, and no human attribution.

## Input integrity

SHA-256:
- blind_packet.jsonl: 9397b1570b442f16ea75153f11fa157b9d9c0cc1b190fb7412477c461e5d72f9
- rubric.json: 61ecdac91bfc872a370a83e46ba3fdd6a9881f150c7ea5bcadd44df0a2b94e0c
- docs/BRAND_VOICE.md: 407985aa09f67829e687d0663a897b59bf57f871b2789de0468bfa6677a44b74

## Freeze

The ratings and these notes were finalized before unblinding. Subsequent checks are limited to identity, JSON/schema shape, exact reply hashes, and output file hashes. No source code was edited. Stop before any unblinding or comparison with predictions, labels, mappings, summaries, or another reviewer.
