# Independent blinded AI review

Completed on 2026-09-18, with final structural validation at 12:18:09 UTC.

## Reviewer and scope

- Reviewer type: **AI**, not human.
- Recorded reviewer identity: **GPT-6 Astra xhigh independent controls review**.
- Reviewed the exact customer text, rendered reply, and supplied evidence from `blind_packet.jsonl` against `verified-support-review-v1`.
- The target was present-day help for historical customer utterances. Historical conversations informed tone and diagnostic patterns only; they did not authorize current policy, staff actions, links, eligibility, or procedures.
- Reviewers did not open predictions, the sealed mapping, manifests, routing summaries, previous scores, implementation, labels, or reserved data. No unblinding was performed.

## Frozen context

All four AI review batches used the same rubric, `config/knowledge/v2.json` version `spotify-current-v2-2026-09-18`, all 21 source snapshots explicitly listed in that configuration, and `docs/BRAND_VOICE.md`. The supplied per-row evidence remained part of each complete review context. No live research or additional source corpus was used.

Every listed source snapshot's file SHA-256 matched its `snapshot_sha256` in the frozen configuration.

| Input | SHA-256 |
| --- | --- |
| `blind_packet.jsonl` | `24f2beecdccae3c38aca30a3d80e2659c75875668b598c2e16b85685b3bcc14e` |
| `rubric.json` | `61ecdac91bfc872a370a83e46ba3fdd6a9881f150c7ea5bcadd44df0a2b94e0c` |
| `config/knowledge/v2.json` | `9abe3912d763ebb8b58e3aaf913158ea8bab4a87142a5a95ea3a8480c9a5d478` |
| `docs/BRAND_VOICE.md` | `407985aa09f67829e687d0663a897b59bf57f871b2789de0468bfa6677a44b74` |

## Deduplication and review method

The packet contains **320 rows and 97 unique complete content contexts**. Deduplication excluded only the five identity fields: `id`, `alias`, `run_id`, `reply_hash`, and `rubric_version`. It retained all other fields and their complete contents, including customer text, reply wording, every evidence item, scores, links, citation booleans, and any scenario field if present. It did not group by reply text alone, infer system identity, or normalize customer wording.

Three inherited Astra xhigh batch reviewers independently judged contexts 1–25, 26–50, and 51–75. The coordinating reviewer judged contexts 76–97. Each batch read the same frozen source set and did not consult other batch ratings. These are 97 semantic AI judgments across four batches, **not 320 independent judgments** and not a multi-rater agreement study.

The 97 judgments were copied only to exact duplicate complete contexts, producing 223 additional duplicate-context rating rows. Each output row retains its own original identity fields. The per-judgment actual UTC timestamp is retained on duplicates. Code performed identity copying, duplicate fanout, hashing, and structural validation; it did not assign semantic scores.

`blind_review_unique.jsonl`, the four `blind_ai_ratings_part*.jsonl` files, and `assemble_blind_ai_ratings.ps1` retain the blinded assembly audit trail. The additional manual decision file for the coordinator's batch records its row-specific semantic judgments before identity enrichment.

## Judgment conventions

- A necessary, relevant question may be high-quality clarification; it is not labeled a completed resolution.
- An appropriate handoff can be rated well. Generic contact language can also be factual and safe while remaining materially unhelpful for the actual issue.
- Honest assistant limitations were distinguished from invented staff actions. Unsupported referrals, actions, or current policy were not inferred from historical examples.
- Known details were checked before approving diagnostic questions. A technically safe reply could still fail for addressing the wrong issue or omitting a material actionable part.
- Defects and their severity are explained in the individual rationales. Ratings assess exact visible replies, not inferred routing labels or system identities.

## Validation and stopping point

`blind_ai_ratings.jsonl` contains **320 completed rows** in packet order. Validation passed for all five identity fields, 320 independently recomputed UTF-8 reply hashes, complete unique-context coverage, integer 1–5 values for all five dimensions, seven boolean flags, allowed categorical values, explicit UTC timestamps, named AI reviewer identity, and nonempty rationales.

Validation read only the blinded packet, its derived unique contexts, and the newly authored review parts. This review ends here, before unblinding or any alias-level comparison. Source review and reply review are AI-authored; no human validation is asserted.
