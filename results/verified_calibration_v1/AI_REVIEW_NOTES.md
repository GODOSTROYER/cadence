# Independent blind AI calibration review

- Reviewer: GPT-6 Astra xhigh independent calibration review.
- Reviewer type: AI. This is an AI-authored review, with no human review or human verification claimed.
- Method: independent_blind. One reviewer assessed all 100 exact replies; no delegated reviewers.
- Completed at UTC: 2026-09-18T12:35:54.216532+00:00.
- Rubric: verified-support-review-v1.
- Reviewed packet: blind_packet.jsonl, 100 records.
- Packet SHA-256: c53f055bd57772f17d3b6c1e9d28d349b013d840c0a298386ef3ec43e81f2580.
- Frozen ratings SHA-256: 2f84eee9266ba91cf023a7b3cdb500aa2acddf2b6a12bc1a19db8ef88e8858e7.

## Blind boundary and evidence

Read only the supplied blind packet, its rubric, config/knowledge/v2.json, all 21 official text snapshots referenced by that knowledge file, and docs/BRAND_VOICE.md. Did not read predictions, mapping, manifest, labels, implementation, previous ratings, or final200/challenge80 data. No unblinding was performed. All 21 snapshot file hashes match the knowledge file's declared snapshot hashes.

Each exact customer utterance and reply was inspected, together with its supplied evidence. Retrieved historical customer examples were not treated as facts about the current customer. Embedded evidence classifications were not accepted as authoritative review outcomes. Historical 2017 replies were used only for diagnostic/voice context; current claims and procedures were judged against the frozen official sources.

## Rating conventions

Scores measure the visible reply's grounding, usefulness for the actual issue, tone, safety, and overall quality independently. A true safety/grounding score does not automatically make a reply useful. Correct account-specific support referrals can ship as handoffs, and remain excluded from useful resolution/clarification coverage.

Response kind describes the actual reply, not the ideal reply or presumed hidden route. A reply sending a social comment to support is therefore a handoff with a relevance defect. Self-service steps for submitting/voting on a feature proposal are classified as resolution for that limited scope; generic contact referrals are handoffs.

Necessary missing-context questions can be useful clarifications. Exact app version is not assumed known merely because a customer says the app is updated. Country checks are relevant where the available procedure is region-scoped, but a named country already present in the frozen availability list should receive an explicit current answer.

A generic honest contact link was not marked wrong_handoff merely because it was weak. Low resolution/tone scores identify unhelpful generic replies. wrong_issue flags were reserved for a different problem or a concrete material actionable omission. Every flagged row has non-none severity and a rationale identifying the defect. Minor wording/context edits do not imply fabricated policy or staff action.

The current full snapshots were checked beyond the selected claim summaries. For example, the Connect snapshot documents lossless playback, the availability snapshot lists India, Serbia, Maldives and Sri Lanka, and the explicit-content snapshot supplies current filter controls. These facts affect present-day answers to historical requests.

## Validation and aggregate results

- Exactly 100 JSONL rows, one per blinded packet row.
- id, alias, run_id, reply_hash and rubric_version preserved verbatim for all rows.
- Every reply_hash verified as SHA-256 of the exact UTF-8 reply_draft.
- All five scores are integers from 1 to 5; all seven flags are booleans.
- Reviewer identity, method, UTC timestamp, verdict, response kind, severity and rationale present on every row.
- Verdict counts: {"edit": 25, "reject": 37, "ship": 38}.
- Response-kind counts: {"clarification": 11, "handoff": 67, "resolution": 22}.
- Severity counts: {"major": 37, "minor": 26, "none": 37}.
- Rows with one or more flags: 15.
- Useful shipped resolution/clarification rows under the rubric definition: 22.

The ratings were frozen before any identity mapping or gold-label access. This review stops at the blind boundary.
