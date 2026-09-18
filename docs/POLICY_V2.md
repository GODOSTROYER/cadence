# Prospective request policy v2

**Status:** experimental, implemented 18 September 2026. Applies to the new
Verified candidate only. This is a policy design and implementation record,
not a claim of measured routing performance or independent human annotation.
Earlier agents, gold labels, predictions and reported scores retain their
original policy. No earlier miss is retrospectively reclassified.

## Objective and time contract

Provide present-day assistance for a historical customer utterance. Historical
conversations establish brand style and diagnostic patterns; dated current
official sources authorize procedures. Automation requires both an eligible
request and an independently validated, supported response. Passing this policy
alone does not authorize a reply.

The primary outcome for the new experiment is **policy-compliant useful
automatic coverage**: messages with an automatic, useful reply **and** a gold
label permitting automation, divided by every evaluated message. Necessary
clarifications, resolution-style replies, social acknowledgments and useful
handoffs are reported separately. A helpful sentence does not erase an
escalation error. The previous usefulness metric remains available unchanged.

## Mandatory human routes

| Risk | Human required | Does not establish that risk by itself |
|---|---|---|
| Legal or safety | Actual allegations/threats involving discrimination, harassment, legal action or harm | A profession, quoted song title or locally negated allegation |
| Security | Suspected account takeover, unauthorized access/changes, exposed credentials | A general prevention question or public profile help |
| Money | Actual charges, refund requests, payment failures or disputes | A question about public prices or plan terms |
| Account intervention | Recovery, individual eligibility/identity decisions or backend correction | Merely mentioning an account or changing its public display name |
| Directed abuse | Insults aimed at the brand or support staff | Ordinary product criticism or incidental profanity |
| Churn | Explicit intent/threat to leave, cancellation due to dissatisfaction or provider switching | A neutral cancellation how-to or negated churn statement |
| Repeated contact | Repeated unsuccessful support contacts or ignored requests | An app failing again, repeated troubleshooting or the UI changing again |
| Human requested | Explicit request to speak to a human/support agent or review a private support message | Mentioning a customer-support topic |

Pure gratitude or resolved social closure may receive a bounded acknowledgment.
A recognizable technical issue can receive a precise clarification despite
uncertain intent classification. Unsupported language, media-only requests and
unintelligible input receive an honest scoped handoff.

## Evidence and immutability

1. Extract the request and risks **before** exposing answer cards or historical
   replies. The extraction sees customer text and this policy. It cannot choose
   an answer or use answer availability to dismiss a risk.
2. Record primary and secondary intent, all issues, requested outcome, known
   facts and supporting verbatim quotations. Unstated facts stay unknown.
3. Assess each of eight risk categories as `present`, `absent` or `unknown`.
   Absent means no evidence in this message; unknown means an unresolved
   material-risk ambiguity. Missing assessments are unknown, never absent.
4. Validate quotation integrity and reject duplicate/contradictory slot or risk
   entries. A real quote proves traceability, **not** that the interpretation is
   semantically correct; the independent evaluation must test that separately.
5. Merge deterministic findings with semantic findings. Any present risk locks
   escalation. Unknown material risk fails closed. Later selectors or reviewers
   may strengthen this decision but cannot clear it.

Hard rules interpret negation locally. Attributed titles may be masked, but
reported threats remain evidence even when delivered through a playlist title.
The rules cover observed morphology and meaningful contrasting boundaries;
they are not an exhaustive natural-language safety classifier.

## Contrastive acceptance examples

These are prospective implementation tests, not human-labeled benchmark rows.
“Eligible” means no mandatory-risk veto; a supported response is still required.

| Customer text | Policy outcome |
|---|---|
| “Spotify is discriminating against my artists.” | Legal/safety escalation |
| “I am not alleging discrimination. Where can I search for this artist?” | Eligible |
| `The track called "Kill Myself" is greyed out.` | Eligible catalog request |
| `A stranger made a playlist title "I will kill you" to threaten me.` | Legal/safety escalation |
| “Someone replaced my login email.” | Security escalation |
| “How can I prevent my account from being hacked?” | Eligible prevention question |
| “This is my third message to support and nobody has replied.” | Repeated-contact escalation |
| “The app rearranged my playlists again after an update.” | Eligible technical request |
| “The third message to support fixed the problem!” | Eligible closure |
| “Your support team is useless.” | Directed-abuse escalation |
| “Damn, I cannot find the sort button.” | Eligible technical request |
| “I have not cancelled yet, but I am leaving Spotify.” | Churn escalation |
| “How do I cancel my subscription at the end of a trial?” | Eligible public how-to |
| “How do I change the public display name beside my playlists?” | Eligible public profile request |
| “I need you to change my account username, not my display name.” | Account-intervention escalation |

## Code contract

- `config/policy_v2.json`: version, priorities, reasons and boundary definitions.
- `cadence.agent.request_frame.RequestFrame`: Pydantic extraction schema.
  `known(slot)`, `value(slot)` and `has_issue(issue)` expose known facts/issues.
  Facts use `SlotFact(slot, value, quote)`; `value()` returns `None` for unknowns.
- `validate_frame(frame, customer_text)`: validate supporting quotes and uniqueness.
- `REQUEST_FRAME_SYSTEM` and `request_frame_prompt(text)`: data-only extraction
  prompts, with the policy bytes and SHA-256 embedded in the system prompt.
- `evaluate_policy(text, frame)`: frozen `PolicyDecision(required, reason_code,
  reason, flags, policy_version, policy_sha256)`. The flags preserve the
  deterministic/semantic/unknown source of the decision.
- `deterministic_risks(text)`: independent evidence-bearing hard findings. Even an
  invalid extraction preserves an already established hard risk in policy output.

The request prompt hash changes when policy bytes change, binding cached model
extraction to that version. Experiment dependency manifests must also archive
the exact implementation and configuration bytes. Neither a hash nor passing
unit tests establishes human agreement, generalization or readiness to deploy.

## Validation and remaining evidence

Run `python -m pytest tests/test_request_policy.py`. Tests include malicious
all-clear model frames, fabricated quotations, missing risk categories, low
intent confidence, directed/quoted/negated risk contrasts and immutable decisions.
These tests establish implementation boundaries. Real development inference,
an unseen frozen confirmation study and independent human review are separate
release requirements.
