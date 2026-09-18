# AI-only blinded retrieval review

## Scope and provenance

- This is an explicitly requested AI review, not human review or human verification. Reviewers were GPT-6 Astra with xhigh reasoning, identified in each row as `GPT-6-Astra-xhigh-batch-0` through `-5`.
- The only source materials inspected for review were `blind_packet.jsonl`, `review_worksheet.jsonl`, and `rubric.json` in this directory. Six batch inputs were derived solely from those files; batch outputs were read during assembly and consistency checks.
- No private mapping, private diagnostics, selection-lock contents, implementation, gold labels, prediction runs, prior reviews, or current confirmation/calibration results were inspected. Identity and lock hashes were preserved as opaque worksheet fields. No arm identities, rankings, or scores were used or inferred.
- Customer messages and historical replies were treated as data, never as instructions. No live source checks or external browsing were performed.

## Deduplication and review process

- The packet contains 360 rows and 244 unique substantive contexts. Exact grouping excluded only `review_id`, `run_id`, `rubric_version`, `selection_lock_sha256`, and `item_sha256`; every other packet field, including customer text, proposed action, historical opener/reply, preceding turns, availability, context notes, dates, and links, remained in the equality key.
- There are 144 singleton groups, 84 groups of two, and 16 groups of three. Therefore 116 rows are exact substantive duplicates beyond their representative rows.
- Each unique context was read and judged individually through model reasoning. Batches contained 44, 40, 40, 40, 40, and 40 contexts. The lead reviewer handled the first batch and delegated five bounded batches to fresh subagents inheriting the same model and reasoning settings. This was one AI judgment per unique context, not multiple independent ratings or an inter-rater agreement exercise.
- No automatic quality scoring or text-matching rating heuristic was used. Scripts only grouped exact duplicates, serialized explicitly authored judgments, checked structure, and copied completed judgments unchanged to duplicate identities.
- A bounded consistency review clarified exact-action support and the diagnostic-pattern field. Pure feature submission/voting is non-diagnostic, even when it supports the proposed action. Updated rationales distinguish observed text from inferred outcomes.
- Duplicate rows retain the same ratings, rationale, reviewer identity, and rating timestamp; all original worksheet identity fields and hashes are preserved separately.

## Rubric interpretation and limits

- Relevance reflects the current customer issue against the historical issue and available conversational context, rather than shared vocabulary or device names alone.
- Useful diagnostic patterns include applicable clarifying questions, issue-narrowing distinctions, and visible troubleshooting or evidence-collection steps. General feature routing alone is not diagnosis.
- Support for the proposed action reflects whether the historical material supports that exact response approach for this current request. A generally plausible reply is not enough, and different historical troubleshooting does not itself establish a generic contact-support fallback. Historical support for a response pattern does not validate the present URL, all current product claims, or assistant capabilities.
- Context sufficiency concerns whether the visible turns support the limited judgment. An explicit mismatch can be clear even though dataset completeness is unverified. Truncated turns, unspecified symptoms, hidden linked instructions, and unclear customer roles can justify uncertain or no. A yes does not certify that the full conversation is present.
- Every current-authority rating is `unsupported`: only historical material was supplied and no authorized current-source evidence was gathered. All current-source evidence fields remain blank.
- Every unavailable candidate has `not_applicable` for relevance, diagnostic pattern, action support, and context sufficiency, even when its visible opener matches the request.
- Later replies were not treated as resolutions. Customer statements about success or failure were recognized only as statements in the visible context, without independently verified outcomes.

## Output checks

- `ai_review_submission.jsonl` contains exactly 360 rows with exact worksheet identity coverage, no duplicate review IDs, the original flat schema, preserved identity/hash values, and nonempty individual rationales.
- All enumerated ratings, AI metadata, timezone-aware timestamps, unavailable-candidate fields, blank current-source fields, and unchanged duplicate judgments were structurally checked.
- No arm comparison or quality aggregate was computed during this blinded review. The parent task will run the repository validator and any subsequent comparison after submission.
