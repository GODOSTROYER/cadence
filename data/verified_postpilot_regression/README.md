# Verified post-pilot boundary regressions — revision 2

This is an **18-row development regression set**. It is deliberately selected, not representative, not an unseen confirmation sample, and not evidence of generalization.

## Revision history

- **Revision 1:** 14 cases, frozen at `2026-09-18T12:38:46.2547695Z`. The original `labels.jsonl`, `LABEL_REVIEW.json`, and `README.md` are preserved **byte-for-byte** under [revisions/v1](revisions/v1/README.md).
- **Revision 2:** 18 cases, frozen at `2026-09-18T12:46:07.6558216Z`. Adds `vc5_049`, `vc5_053`, `vc5_061`, and `vc5_098` at the root assistant's explicit request before new regression inference. The parent confirmed that no inference had begun.
- The original 14 customer/synthetic texts and gold annotations remain unchanged. Reuse metadata now explicitly marks all six calibration cases as previously inspected development regressions.
- The historical snapshot retains its original file contents, including paths recorded at the original freeze. Its recorded hashes identify the original 14-case packet.

## Composition and authorship

- **6 reused historical customer cases:** `vc5_085`, `vc5_086`, `vc5_049`, `vc5_053`, `vc5_061`, and `vc5_098`, copied from `data/verified_calibration/ai_labels.jsonl`. Identifiers, thread identifiers, exact customer text, original AI gold (including sentiment and notes), and original annotator are preserved. All six are explicitly **inspected development regressions**, not unseen cases.
- **12 synthetic cases:** `pp6_001` through `pp6_012`. The root assistant authored the exact strings. A separate child annotator, **gpt-6-astra xhigh**, independently authored their labels against frozen policy v2 in revision 1. Revision 2 retains those annotations unchanged.
- No new gold annotations were authored in revision 2; the four additions copy existing independent AI gold exactly.
- All labels are AI-authored. No human annotation, human validation, or future human review is claimed.

The source calibration file was not modified. Only the six authorized source records were surfaced or inspected during this task; no other calibration, final200, or challenge80 texts were displayed.

## Why these cases were selected

These targeted post-pilot regressions exercise account prevention versus compromise, local negation, cancel/leave language with different objects, explicit churn, gratitude and figurative language, actual harm and hearing-safety concerns, attributed device names, editorial curation, historical product-feature requests, and known-family-device playback complaints.

Selection was by the root assistant and is not independent sampling. The reused cases were already inspected. Results must remain development regression evidence and must not be folded into an unseen confirmation claim.

## Revision 2 freeze and provenance

Every row uses `split: "development"` and `label_source: "ai"`. Candidate implementation, inference outputs, and reply scores were not inspected by this annotator. This revision was completed before the new post-pilot regression inference.

- Freeze time (UTC): `2026-09-18T12:46:07.6558216Z`
- Frozen policy: `config/policy_v2.json`
- Policy SHA-256: `cad5c7058e464d0f1d620b04868247df6fe5df25b2f4505b2c08c27fb0a2dae0`
- Reused source SHA-256: `8523e075284993751300c2b00a24cdb1490b9837cfc5cb8a46dc2d2459fd289a`
- Revision 2 `labels.jsonl` SHA-256: `a054c3228d8b409d95bd146f89c894b283096942210ed2a93ae4c0ad1a3b02f3`

The frozen labels contain **7 escalation-required** and **11 eligible** cases. Eligibility only means no mandatory policy veto; it does not establish that an available reply is current, supported, useful, or ready to send.

### Preserved revision 1 hashes

| File | SHA-256 |
|---|---|
| `revisions/v1/labels.jsonl` | `14aad5ace94bd527cb0ae5c6691ea53c49c27ff61ec34cb11bff7c60d2df93d9` |
| `revisions/v1/LABEL_REVIEW.json` | `64bc9488258b0016015178526163a89918ea97e186ba83dfcb4264b4bd0f0a4b` |
| `revisions/v1/README.md` | `04b4d328c4dc3c5a88d7ad26c4d03566830e646e430173224eeb20db9a6ad895` |

See [LABEL_REVIEW.json](LABEL_REVIEW.json) for source metadata, the revision history, independence statements, validation checks, and annotation interpretations.
