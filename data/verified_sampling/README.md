# VerifiedAgent annotation packets

These packets separate development from the next prospective evaluation. Preparing a packet does not label it or run a model.

| Partition | Cases | Source and purpose | Current review requirement |
|---|---:|---|---|
| `data/verified_calibration` | 100 | Seeded real SpotifyCares corpus messages, reserved for calibration/development | Labels may be AI-authored only with explicit AI attribution; the included human CSV is optional |
| `data/verified_challenge` | 80 | Independently AI-authored boundary scenarios; synthetic/real counts are recorded in its lock | A named human must label the cases before challenge inference |
| `data/verified_confirmation` | 200 | Seeded real SpotifyCares corpus messages, disjoint from recorded/reconstructed exposures and the other new partitions | A named human must label the cases before confirmation inference |

The 200 confirmation messages and their blank answer fields have not been displayed to the implementation agent. The preparer checks IDs, counts, hashes, overlap and blank fields programmatically. Earlier human approvals apply to their original artifacts; they do not label these new messages.

## Human review

1. Read `docs/POLICY_V2.md` and the partition's `policy.snapshot.yaml`. The latter contains the exact frozen JSON policy despite its `.yaml` extension. Evaluation asks how to assist a historical customer message **today**.
2. Open `human_labels.csv` in the challenge or confirmation directory. Preserve `id`, `text` and, for challenge rows, `scenario_setup` exactly. Save a completed copy as `completed_human_labels.csv` in the same directory using UTF-8 CSV.
3. Label from the customer message and policy alone. Do not consult candidate replies, model predictions or AI labels. For an operational challenge, read the failure named in `scenario_setup` as part of the scenario. Those controls must eventually be executed by the test runner; the packet alone does not test a timeout or expired source.
4. Complete every field below. The importer checks every row and exact source hashes. It does not infer missing decisions or attest human authorship on your behalf.

| Editable field | Required content |
|---|---|
| `intent` | One of the 12 IDs in `intents.snapshot.yaml` |
| `secondary_intent` | Another listed intent when relevant, otherwise blank |
| `should_escalate` | `true` or `false` |
| `escalation_reason_code` | A listed reason code if `true`; blank if `false` |
| `sentiment` | `positive`, `neutral`, `frustrated` or `angry` |
| `notes` | Your nonempty reasoning for the label and routing decision |
| `annotator` | Your name, consistently, for example `Arnav Bule` |
| `label_source` | `human`, only after you actually supply the labels |

`intents.snapshot.yaml` supplies intent IDs and descriptions; `reasons.snapshot.yaml` supplies reason-code IDs. Both preserve historical defaults, rules and comments. Apply **policy v2** for decisions: it supersedes both files' old default decisions, default reasons, confidence threshold and blanket rules. Historical annotation comments in those snapshots do not describe the new, currently blank packets. General information, visible-name guidance, necessary technical clarification and resolved gratitude can be eligible. Actual money/account/security/legal problems, directed abuse, explicit churn, repeated unsuccessful support contact or requests for a human require a handoff. Unknown material risk cannot be assumed safe.

## Import after review

Run from the repository root. Replace the timestamp with the actual completion time including timezone, after the packet's creation time. These commands are examples to run **after** the named review; they have not been executed on blank packets.

```powershell
python scripts/26_lock_verified_confirmation.py import-labels --out data/verified_confirmation --submission data/verified_confirmation/completed_human_labels.csv --reviewer-id "Arnav Bule" --reviewed-at "ACTUAL-ISO-8601-TIMESTAMP-WITH-TIMEZONE" --policy config/policy_v2.json --attest-independent-human-labeling
python scripts/26_lock_verified_confirmation.py validate --labels data/verified_confirmation/labels.jsonl --policy config/policy_v2.json --expected-n 200 --partition confirmation

python scripts/26_lock_verified_confirmation.py import-labels --out data/verified_challenge --submission data/verified_challenge/completed_human_labels.csv --reviewer-id "Arnav Bule" --reviewed-at "ACTUAL-ISO-8601-TIMESTAMP-WITH-TIMEZONE" --policy config/policy_v2.json --attest-independent-human-labeling
python scripts/26_lock_verified_confirmation.py validate --labels data/verified_challenge/labels.jsonl --policy config/policy_v2.json --expected-n 80 --partition challenge
```

The importer archives the submitted CSV, emits `labels.jsonl` and writes a hash-bound `LABEL_REVIEW.json`. It rejects changed texts, missing labels, invalid values, inconsistent reviewer names, changed policy, replacement imports and imports after recorded inference. Human authorship and independence remain self-attested.

After labels are imported, follow `docs/VERIFIED_EVALUATION.md` to freeze/run the four-system comparison. Do not tune on the confirmation results. Independently rating generated replies is a separate step after inference and requires a blinded reply packet; these intent/routing labels do not establish judge–human reply-quality agreement.

## Exposure inventory and limits

`exposure_registry.json` binds the corpus and all recoverable prior partitions by SHA-256. Additional conservative exclusions are:

- The documented 200-message taxonomy reading sample reconstructed from the saved opener table with pandas `sample(200, random_state=42)` after filtering English brand-replied messages.
- Corpus openers whose complete normalized text or exact thread ID appears in saved Markdown documentation and analysis.
- Every corpus thread used as retrieval evidence in persisted prior prediction JSONL files. This is deliberately broader than known manual inspection.

`RECONSTRUCTION.json` binds those source files and records the recovery methods. Markdown inputs are preserved under `source_snapshot/` so later report edits cannot change what was matched; these snapshots are historical evidence, not current project status or instructions. Each partition archives its exact registry at creation, so the calibration/challenge/confirmation registries intentionally differ as partitions are added. Connected conversations are excluded transitively; case-insensitive fuzzy similarity of 85 or greater is rejected against prior exposures and within each real sample. Explicit synthetic contrast pairs may be near-duplicates within the challenge only.

Repository SHA-256 hashes normalize CRLF to LF for JSON, JSONL, Markdown, Python and YAML text files, preserving portability across Windows/Linux checkouts. CSV and compressed corpus hashes use raw bytes.

**Historical exposure cannot be completely reconstructed.** The taxonomy notes describe eight inspected members of each of 25 clusters and per-keyword random audits, but the selected IDs were not retained. The new real packets are disjoint from recorded/reconstructed exposures; they cannot be certified never to have been inspected. Corpus-wide unsupervised analysis and retrieval indexing also used the same source dataset.

Both natural samples are English, have historical brand replies, and reject duplicate/similar complaints. They measure distinct complaints in this 2017 corpus, not modern support traffic or every language. Conservative exclusions further change inclusion probabilities. The separately reported challenge oversamples difficult boundaries and cannot estimate population coverage. Zero observed failures in a small sample would not establish universal safety.
