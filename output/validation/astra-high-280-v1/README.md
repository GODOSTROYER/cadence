# Cadence — labels for Arnav's validation

**280 AI draft labels: 200 real confirmation messages and 80 synthetic challenge cases.**

Each case was individually labelled by **GPT-6 Astra with high reasoning** using policy v2, then checked by a separate Astra extra-high acceptance reviewer. Two explicit Astra-high revisions corrected one routing inconsistency and one unsupported rationale detail; their originals and review history are preserved. **55 cases are flagged for closer attention; all 280 still require your validation.** No candidate inference has run on these cases.

## Review the workbook

Open **Cadence-Label-Validation.xlsx**. It has separate **Confirmation** and **Challenge** sheets.

1. Read the customer message and, for challenge cases, the scenario setup.
2. Check the proposed intent, secondary intent, escalation decision, reason and sentiment. The label fields start with Astra's proposals; edit them where needed.
3. Read Astra's rationale and the human-review question. Independent acceptance-review suggestions, where present, are shown explicitly. The original AI judgments remain preserved in `drafts/`.
4. Set **Review status** to **Approved**, **Corrected**, or **Needs discussion**. Every row initially says **Pending**; a prefilled proposal is not an approval.
5. Add a short note for corrections or unresolved questions. Enter your name and actual review time in the reviewer fields when finished.
6. Save a reviewed copy and return it for validation/import. CSV copies provide the same draft fields if you prefer another editor.

Use the frozen [policy](../../../docs/POLICY_V2.md) and the [annotation guide](ANNOTATION_GUIDE.md). A recognizable technical issue may permit a useful question; actual billing, security, legal/safety, account intervention, directed abuse, explicit churn, repeated unsuccessful contact, or a human-support request may require escalation. Eligible means a supported response may be possible, not that the issue has been resolved.

## Provenance and next step

- Confirmation is a deduplicated historical corpus sample; challenge is a synthetic boundary suite. Keep their results separate.
- Astra-high drafts and any Astra extra-high acceptance suggestions are **AI work**. Human verification remains blank and pending.
- Because these drafts are visible during your review, the eventual record will say **AI-assisted labels verified/corrected by Arnav Bule**. It will not claim blind independent human labeling.
- The original sample locks, examples and blank human worksheets are preserved. The current importer requires an independent-human attestation; this AI-assisted workbook must not be submitted through that command under an inaccurate attestation. Record the actual assisted-review method before any later evaluation.
- These are intent/routing labels. Separate blinded human ratings of generated replies are needed later to measure reply-judge agreement.

`MANIFEST.json` binds the source inputs; `DRAFT_VALIDATION.json` records shape/provenance checks; `reviews/` preserves acceptance-review findings. `STATE.json` and `../../analysis/ACTIVE_LABELING_STATE.md` provide resume instructions if the task is interrupted.
