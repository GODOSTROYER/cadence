# Blinded Astra review — balanced confirmation

## Completion

Individually assessed all **240 exact replies** across **80 customer messages**, with 80 replies for each blinded alias A, B and C. The saved ratings are the original completed AI judgments for this review.

- Reviewer: `astra-balanced-confirmation-blind`
- Reviewer type: `ai`
- Model: `gpt-6-astra`
- Reasoning effort: `xhigh`
- Rubric: `support-review-v1`
- Recorded UTC timestamp: `2026-09-18T06:35:53Z`
- Ratings: `blind_astra_ratings.jsonl`
- Original Windows file byte SHA-256 (CRLF): `a849cbe9949af599917e208056b7b1498db43b4d65257701245d58a34158eec7`
- Portable LF content SHA-256 used by the repository verifier: `8c00806fa474e544ff55c164c7563c0de841d23a6f9cc2affb86c54391252073`

This is an AI review, not human review or human verification. It supplements rather than replaces the frozen benchmark.

## Inputs and blinding

Evaluation cases, exact drafts and evidence came exclusively from `results/balanced_confirmation/blind_packet.jsonl`. I also read the permitted schema in `src/cadence/eval/review.py`. The initially supplied `config/judge_rubric.yaml` was absent; after filename-only discovery and explicit authorization from the coordinating task, I read `results/review_study/rubric.md`.

I did not read mappings, predictions, gold labels, study summaries, candidate implementations, development results, other reviewers' ratings or the parent checkpoint/docs. I did not infer system identities or compare results with an automated judge.

I read each customer's text, all three exact replies, their evidence membership and the unique historical evidence for that case. Repeated current-source and policy cards were read in full once and referenced by their identifiers thereafter. The historical conversations were diagnostic context, not authority for current policies, promotions, UI procedures, outages or staff actions.

## Counts

| Verdict | Replies |
| --- | ---: |
| Ship | 82 |
| Edit | 106 |
| Reject | 52 |
| **Total** | **240** |

| Response kind | Replies |
| --- | ---: |
| Resolution | 28 |
| Clarification | 50 |
| Handoff | 150 |
| Other | 12 |

| Flag | Replies |
| --- | ---: |
| Hallucinated link or policy | 12 |
| Asks sensitive information | 12 |
| Wrong issue | 19 |

Flags may overlap. Response kind describes the form of the reply, including unsuccessful resolution attempts; it is not a claim that the issue was actually solved. Social acknowledgments are `other`, and referrals to support or the Ideas board are `handoff`.

## Judgment principles

- I authored the scores, flags, verdict, response kind and individual rationale for every reply. No keyword rules or scoring heuristics generated judgments. Temporary helpers only compacted evidence for reading, serialized the authored entries, bound exact packet metadata and checked completeness.
- A specific necessary clarification could receive `resolves=4` because it creates a useful next step. Broad questions that repeated supplied context were rated lower.
- Supported human handoffs for account access, suspected compromise, paid-plan discrepancies or uncertain offer terms were eligible to ship. They were not penalized simply because the assistant could not complete an account action. A holding reply without a contact route was less useful.
- A valid contact URL alone was insufficient when the reply missed a feature question, prematurely abandoned an ordinary diagnostic question or treated a thank-you as an unresolved problem.
- Current source guidance still had to match the customer's issue. Examples of mismatches included student-verification advice for Hulu connection trouble and Library-saving advice for disappearing offline downloads.
- Historical staff promises, backstage account access, current outage fixes and promotion guarantees were unsupported. Private account-identifier requests were flagged even when phrased as DM requests because the assistant has no DM or account tools.
- Ordinary offers to examine newly supplied public information were not equated with explicit backend access or staff forwarding. This distinction was applied to public song-link and technical clarification requests.
- The link/policy flag marks unsupported current rules, offers or UI procedures. Unsupported actions and status assurances also lowered grounded and safe scores, but did not automatically receive that narrower flag. Historical URLs that actually appeared in evidence were not called invented solely because their current procedure was unverified.
- `ship` means the exact wording was acceptable without a required edit. Some shipped replies received 4 rather than 5 for nonblocking limitations, such as a generic closing or incomplete detail beyond an adequate next step. A social acknowledgment could fully satisfy its message while remaining `other` rather than a technical resolution.

## Validation

The final JSONL was read back and checked against the blinded packet alone:

- Exactly 240 unique `(id, alias)` pairs, covering every expected pair and all 80 messages.
- Exact `id`, `alias`, `run_id`, `reply_hash` and `rubric_version` binding for every row.
- SHA-256 recomputation of all 240 exact packet reply drafts matched their supplied hashes.
- All five score fields are integers from 1 through 5; all three flags are booleans.
- Every row has the required reviewer identity, AI type, model, reasoning effort, UTC timestamp, valid verdict, valid response kind and individual rationale.
- No ratings file was overwritten; the assembler required the destination to be absent before writing the completed review.

## Limitations

This is one AI review with subjective editorial thresholds. It is limited to the supplied customer text and evidence: placeholder URLs, screenshots and missing conversation history could not be reconstructed. Current-source cards were accepted as supplied in the packet and were not independently fetched or audited. No current product facts, live account state, actual support outcome or release status were established beyond that evidence. The reported counts describe this review only and make no claim about hidden system identities, agreement with unseen ratings or human preference.
