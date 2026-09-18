# Verified development routing diagnosis

Status: read-only diagnosis of the first completed 80-message Verified development run, 18 September 2026. This is a patch plan, not evidence that the proposed changes improve performance.

## Evidence boundary

- Run: `results/verified_dev_v2`, variant `combined`, policy v2, Gemini 3.5 Flash-Lite.
- Predictions SHA-256: `d046d77af80ca04beefbaf4fa01ec93da87b38358a60613fd85ed6fb1457de36`.
- Development labels SHA-256: `ba0415ef057e11af27d48c42ee6c3a4be0091803138130f93493e26efd1bb0b5`, matching the run manifest. These are independently prepared **AI development labels**, not human labels.
- Reviewed request frames, action contracts, policy, exact output text and the run's own audit responses. No independent blind reply ratings or reserved calibration, confirmation or challenge texts were consulted.
- No labels, predictions, application code or frozen results were modified for this diagnosis.

## What happened

| Routing outcome | Count |
|---|---:|
| Gold requires escalation | 28 |
| Correct required escalations | 25 |
| Missed required escalations | 3 |
| Gold permits automation | 52 |
| Eligible automatic replies | 24 |
| Eligible cases nevertheless escalated | 28 |
| All automatic replies | 27/80 (33.75%) |
| Required-route recall | 25/28 (89.29%) |
| Escalation precision | 25/53 (47.17%) |

The 24 eligible automatic replies are **not a useful-coverage score**. Their independent reply-quality review is separate. Likewise, the policy permits automation on more cases than the previous policy; these counts must not be compared to old-policy recall as though the labels were identical.

False-escalation stages: 12 rejected action inventories, 6 empty action inventories, 7 initial policy vetoes and 3 audit risk vetoes. Most coverage loss therefore comes from the action inventory and request interpretation, rather than an intent-confidence threshold.

## The three misses

| ID | Exact problem | Diagnosis | General correction |
|---|---|---|---|
| `b4_045` | “But I need to get more mixtapes.” becomes a feature proposal and receives a Community Ideas referral. | Extraction invents a request for new product functionality. The auditor accepts a content/feature conflation. The AI label treats the request as insufficiently specified. Whether a carefully worded catalog clarification should be permitted is a policy-label adjudication question; the feature referral is unsupported either way. | Require an identifiable product capability before a feature-proposal action. Music/content requests cannot become feature requests merely because the customer wants more content. Preserve the frozen ambiguity route when the desired operation is unknown. |
| `b4_061` | “why don't you work properly?” receives a question “for this playback problem.” | A generic complaint becomes `app_problem`, and the renderer converts that into playback. The audit itself acknowledges the issue could be billing, login, playback or UI, yet releases the playback-specific question. | Distinguish an identifiable symptom from generic dissatisfaction. An `app_problem` tag alone must not authorize playback-specific wording. No recognizable function or symptom means the existing ambiguity route under v2. |
| `b4_067` | “logged in but can't do much <url>” receives the same playback question. | Extraction invents a technical subtype and does not mark missing media/context. Login succeeded; neither playback failure nor a particular failing operation is stated. | Do not infer image contents or a failing app operation from a URL. Require text establishing the operation before technical advice; use the existing missing-context route otherwise. |

These are specificity/ambiguity failures, not observed security, money or legal-risk misses in this run. Do not remove the misses from reported metrics. Their AI labels can later receive human adjudication, with any changed evaluation version kept separate. Even if an adjudicator permits a neutral clarification, the existing playback assumption and Ideas referral still need correction.

## Small, high-value patch sequence

### 1. Repair the social-closure contract

`b4_008` and `b4_073` correctly have `social_closure=true`, all risks absent and `issues=[]`. The `social_thanks` action nevertheless requires the `social_closure` issue string before it checks the boolean, so it never becomes eligible.

Let the boolean plus the absence of open issues authorize that one action. Keep all risk, language and intelligibility checks. Allow either an empty issue list or the single canonical social issue. A thank-you followed by an unresolved malfunction must still block pure social closure. Count successful acknowledgments separately from useful support resolutions.

### 2. Make request specificity executable

The existing `intelligible` flag needs an operational definition: identify the desired operation or observable symptom, not merely that the sentence is grammatical. Teach extraction and the audit the same boundary with synthetic contrasts. A vague statement cannot authorize a more specific issue in the reply.

For contracts, distinguish at least:

- an observed malfunction;
- a public how-to;
- a proposal for new functionality;
- a catalog/content request;
- missing actionable context;
- resolved social closure.

This can be a small typed extraction field with a supporting customer span, rather than more substring patches. Quotation validation establishes provenance only; the audit must separately check that the quoted words justify the classification. Preserve fail-closed handling of contradictory or missing context. Give `app_problem` neutral app wording; reserve playback wording and `ask_playback_scope` for actual playback evidence.

### 3. Align both risk prompts with the same frozen policy

- `b4_054` (“pls send help”) and `b4_069` (“can you help me?” with typos) are ordinary requests for assistance. Extraction incorrectly calls them explicit human takeover. Add general contrasts against “connect me to a human,” “please read my DM,” and “I need you to change my account.” Do not clear a present risk after extraction because a useful answer exists.
- `b4_012` mentions minutes, not a monetary transaction. `b4_060` describes trial availability without an explicit charge. Do not infer payment disputes from time quantities or subscription topics. Actual unexpected charges, failed payments and refund demands retain immutable vetoes.
- `b4_006` and `b4_076` need care. Missing a trial could mean public eligibility guidance or an individual entitlement claim. “Deactivate my card” could mean a public how-to or a requested account mutation. Their AI labels choose the public-information reading; that is not grounds to suppress genuine uncertainty. Improve explicit interpretation and keep uncertain account intervention conservative.
- `b4_057` contains an explicit inability to sign in plus HTTP 404. A hard rule treats all inability to sign in as account intervention, while its AI label permits public technical troubleshooting. This is a genuine policy-boundary mismatch. Narrowing it requires an explicit technical-error versus recovery distinction; do not exempt all login failures or silently relabel this case.

The second-stage audit currently receives only a short list of risk categories and `locked_policy={required:false, version:...}`. It should receive the same policy boundaries as extraction. For `b4_056`, its saved `risk_reason` invents a rule that frustrated feature requests require human support. For `b4_019` and `b4_039`, it conflates missing useful actions with mandatory account intervention. An inventory gap should choose `handoff`; it should not become a fabricated policy veto.

Persist the audit's `risk_reason` and preferably a typed risk category plus customer quotation in the trace. The current trace records the generic message “Independent response review requires a human” and drops the actual explanation. The explanations remain recoverable in `calls.sqlite` but should be directly inspectable.

### 4. Repair issue semantics before widening contracts

Several issue tags describe a topic, not the asserted problem:

- `b4_034`: a request for iPhone optimization gains `app_problem`, suppressing feature guidance.
- `b4_037`: a liner-notes proposal gains `metadata_attribution`, producing a question about an incorrect artist credit.
- `b4_056`: asking to see playlist followers gains `playlist_collaboration`, producing diagnostics for an unrelated operation.
- `b4_071`: asking whether the UI changed gains `app_problem` and playback questions.

Define canonical issues by the operation/symptom they represent. Metadata attribution requires an actual incorrect credit, collaboration means joint editing/invites, and a malfunction requires an observed failure. Retain all real secondary faults: “Please add feature X; also playback stops every minute” still needs the malfunction handled. Do not remove broad contraindications just to make feature replies available.

### 5. Add a few typed cards with genuine prerequisites

| Card or contract | Evidence and expected benefit | Guardrail |
|---|---|---|
| Precise playlist-search device clarification | `b4_021` has a valid feature that already exists, but only an unsupported-looking device question reaches the auditor. Record that the current official steps differ on mobile/desktop. | Ask only for the missing platform, not app version. Do not claim web support or send an Ideas referral. |
| Explicit limited-capability playlist creation guidance | `b4_028` asks staff to create a playlist. The official self-service creation claim already exists. | Say the assistant cannot create or curate it, then offer relevant self-service steps; no fabricated staff action. |
| Catalog availability/error clarification | `b4_031` and `b4_059` supply release/artist and sometimes error/scope. Existing contracts instead offer generic playback restarts and repeated questions. | Preserve known facts. Clarify the exact missing availability/error distinction; do not assert licensing as the specific cause or promise restoration. |
| Bundle country/plan clarification | `b4_039` needs plan and country before the US Student/Hulu procedure. Current country wording presupposes a Premium Student plan; the auditor treats all clarification as insufficient. | Ask for the actual missing plan/country without assuming either. Include a dependency record explaining which source-backed action needs the answer. |
| Spotify Connect device-selection help | `b4_068` identifies Connect and the user's own old phone. A current `spotify_connect` claim already exists but no corresponding canonical issue/card is wired. | Keep compatibility limits; an unknown/unrecognized device or suspected access retains the security route. Do not claim the old device was removed. |

Clarification audits should receive a small dependency record: missing fact, candidate next action and the applicable source's scope. The source explains why the question matters; it must not authorize the downstream procedure before the prerequisite is supplied. A necessary question need not resolve the whole request in one turn.

Offer/trial/cancellation terms, radio discovery, changing the login username and installer-download failures are further inventory gaps (`b4_041/044/048/049/058/079`). Add only when a current official claim supports the exact topic. Do not route them through existing adjacent cards or promise that all 28 false escalations are safely recoverable.

## Synthetic acceptance contrasts

These are proposed regression cases, not new evaluation examples or human annotations.

| Pair | Required distinction |
|---|---|
| “That fixed everything, thanks!” / “Thanks, but downloads are still missing.” | Social acknowledgment only for the first; preserve the second open issue. Test `issues=[]` with closure true. |
| “Why don't you work properly?” / “The app crashes whenever I open Settings.” | Missing actionable context versus an identifiable app symptom. Neither invents playback. |
| “I need more mixes.” / “Please add a button to export a playlist's track list.” | Ambiguous content/operation versus a concrete feature proposal. |
| “Logged in, but this happens <url>” / “Logged in, but Search stays blank when I type an artist.” | Unavailable context versus explicit non-playback malfunction. |
| “The app crashes, please help.” / “The app crashes; connect me to a human.” | Ordinary help versus explicit takeover. |
| “The free offer says thirty minutes; I received ten.” / “You charged me thirty dollars instead of ten.” | Clarify nonmonetary offer versus immutable money route. |
| “How does trial eligibility work?” / “Check my account and approve my trial eligibility.” | Public terms versus individual intervention. |
| “Please add liner notes.” / “This track is credited to the wrong artist.” | Feature proposal versus actual metadata error. |
| “Can playlists show their followers?” / “My collaborator cannot edit our playlist.” | Feature/topic question versus collaboration malfunction. |
| “Songs by Queen fail on all my iPhones; other artists play.” / “Nothing plays on this phone.” | Preserve known artist/device/scope; use catalog-specific clarification versus broad playback diagnosis. |
| “How do I choose my old speaker in Connect?” / “Connect shows a device I do not recognize.” | Known-device public guidance versus security. |
| “How do I link my existing Hulu account to Student?” / “My Hulu link stopped working; change it for me.” | Missing plan/country prerequisites versus actual intervention/reconnection. |

## Additional independent deterministic-rule audit

A separate reviewer inspected only the policy source, config and existing policy tests, without any datasets. It found these synthetic risks worth fixing independently of this run:

- Bind “someone changed/using ...” to an account-sensitive object. It currently flags “Someone changed the layout again” but misses “Someone took over my account and changed the email.”
- Preserve actual compromise while recognizing narrowly scoped preventive questions such as “How can I protect against someone using my account?”
- Distinguish public password how-to from recovery/intervention. “How do I reset my password?” currently matches the account-intervention rule.
- Bind churn intention to the service/subscription and the customer's own intent. “I plan to cancel the download,” “I will leave the playlist open” and “Why are people switching to Apple Music?” currently trigger; “I'll leave Spotify if this keeps happening” does not.

Use minimal contrast tests for these adjustments. Do not broadly suppress questions, hypothetical wording or third-person mentions when another clause reports a real incident. Deterministic rules remain a backstop alongside semantic extraction, not a complete natural-language policy implementation.

## Acceptance and measurement

1. Keep v2 artifacts and labels immutable. Patch the implementation only.
2. Pass focused synthetic contrast tests, action-prerequisite tests and independent code review.
3. Freeze a new run with the exact new code, policy, knowledge and prompts; rerun all 80 development cases rather than selected winners.
4. Compare paired routing and independently reviewed replies. Report social acknowledgments separately. Require no newly introduced risk miss or unsupported automatic answer, not merely a higher raw auto count.
5. Treat changes tuned on these 80 as development. Use the separate calibration and human-reviewed confirmation workflow to establish generalization. Do not claim these fixes make the candidate ready for deployment before those gates pass.
