# Cadence — Astra Ultra review of flagged cases

**Additional AI review of 55 flagged cases: 35 real confirmation messages and 20 synthetic challenge cases.** Arnav Bule requested GPT-6 Astra with **ultra reasoning** to perform this review. Every decision is explicitly attributed to AI. Human verification remains pending.

## Outcome

All 55 cases received individual Ultra review. **33 are confirmed, 4 revised, and 18 need discussion.** In total, 11 cases propose label changes: the 4 revised cases plus 7 that retain an unresolved question. The remaining 44 keep the prior labels. These counts describe annotation decisions, not model performance or human agreement.

## Read the review

Open **Cadence-Astra-Ultra-Review.xlsx**. The Confirmation and Challenge sheets show each source message/setup, the prior accepted Astra-high proposal, the Ultra proposal, exact label changes, the rationale, and a response to the flagged question. CSV copies and `review_data.json` carry the same review decisions.

AI dispositions mean:

- **confirmed:** Ultra retained the prior labels and supplied its answer to the flag.
- **revised:** Ultra proposed one or more label changes and supplied its reasoning.
- **needs_discussion:** a factual or policy ambiguity remains; a best-supported proposal may still differ from the prior labels. Read the remaining question.

These statuses describe AI work. The separate human-review fields remain **Pending**, with reviewer, review time and human notes blank. During human validation, check the message and scenario, compare both proposals, record any corrections in the human notes, and complete the human review fields. Preserve a reviewed copy.

## Scope and provenance

- The prior [280-case validation package](../astra-high-280-v1/README.md), original judgments, explicit earlier revisions, and original workbook are preserved. This follow-up covers only its 55 attention-flagged rows; the other 225 cases received no new Ultra review here.
- Reviewers could see the prior AI proposals and flagged questions. This is an additional AI adjudication pass, not blind independent annotation or human verification.
- The model is **GPT-6 Astra**, reasoning effort **ultra**, review source **ai**. Review timestamps and task identities are recorded per case. A separate Astra Ultra acceptance pass checks the results and delivery artifacts.
- The frozen [annotation policy and taxonomy](../astra-high-280-v1/ANNOTATION_GUIDE.md) govern the decisions. `REVIEW_GUIDE.md` defines this review's scope and schema.
- No candidate inference or reply-quality scoring was performed. These intent/routing proposals do not establish judge–human agreement and have not been imported as human gold labels.
- Confirmation and synthetic challenge results must stay separate. Proposed escalation counts are label decisions, not measured agent performance.

`MANIFEST.json` identifies the exact reviewed inputs. `ACCEPTANCE.json` records the final acceptance and file bindings. `STATE.md` and `STATE.json` support recovery after interruption. Run `python output/validation/astra-ultra-flagged-v1/assemble_review.py` from the repository root to verify coverage, provenance, policy-schema validity, source integrity and the absence of human-import/inference markers.
