# Verified post-pilot boundary regressions

This is a **14-row development regression set**. It is deliberately selected, not representative, not an unseen confirmation sample, and not evidence of generalization.

## Composition and authorship

- **2 reused historical customer cases:** `vc5_085` and `vc5_086`, copied from `data/verified_calibration/ai_labels.jsonl`. Their identifiers, thread identifiers, customer text, original AI gold (including sentiment), and original annotator are preserved exactly. Their split is now explicitly `development`, with reuse recorded in each row.
- **12 synthetic cases:** `pp6_001` through `pp6_012`. The root assistant authored the exact input strings. A separate child annotator, **gpt-6-astra xhigh**, independently authored their labels against the frozen policy.
- All labels are AI-authored. No human annotation, human validation, or future human review is claimed.

The source calibration file was not modified. Only the two authorized source records were surfaced or inspected during this task; no other calibration, final200, or challenge80 texts were displayed.

## Why these cases were selected

These targeted post-pilot regressions exercise:

- Account prevention advice, negated incidents, and actual account compromise.
- Cancel/leave language whose object is a download or playlist, versus an explicit threat to leave Spotify.
- Ordinary gratitude and figurative language versus actual ear/property harm.
- An explicit hearing-safety concern and an attributed device name that contains harm-related words.
- Necessary technical clarification without treating missing device details as an automatic risk.

Selection was by the root assistant and is not independent sampling. The reused cases were already inspected. Results on this set must remain development regression evidence and must not be folded into an unseen confirmation claim.

## Freeze and provenance

All 14 rows use `split: "development"` and `label_source: "ai"`. The 12 synthetic labels were completed before the new post-pilot regression inference. Candidate implementation, inference outputs, and reply scores were not inspected by this annotator.

- Freeze time (UTC): `2026-09-18T12:38:46.2547695Z`
- Frozen policy: `config/policy_v2.json`
- Policy SHA-256: `cad5c7058e464d0f1d620b04868247df6fe5df25b2f4505b2c08c27fb0a2dae0`
- Reused source SHA-256: `8523e075284993751300c2b00a24cdb1490b9837cfc5cb8a46dc2d2459fd289a`
- `labels.jsonl` SHA-256: `14aad5ace94bd527cb0ae5c6691ea53c49c27ff61ec34cb11bff7c60d2df93d9`

The frozen labels contain **7 escalation-required** and **7 eligible** cases. Eligibility only means no mandatory policy veto; it does not establish that an available reply is current, supported, useful, or ready to send.

See [LABEL_REVIEW.json](LABEL_REVIEW.json) for source metadata, independence statements, validation checks, and annotation interpretations.
