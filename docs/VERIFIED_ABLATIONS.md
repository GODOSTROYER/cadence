# Verified development controls and retrieval diagnosis

See [Verified empirical status](VERIFIED_STATUS.md) for completed diagnostics and
measured results. This guide describes the available controls and how to create a
new study; it does not imply their review or release gates have passed. VerifiedAgent
and policy v2 remain experimental, with reference `SupportAgent` still the default.

These tools implement **development diagnostics**, with no deployment or promotion
path. They do not run new model calls. They never turn an archived escalation into
automatic handling, and cannot establish the benefit of new answers, better
clarification, or a deployable combined agent. The full Verified candidate is
evaluated separately by `scripts/25_verified_experiment.py`.

## What each control changes

Every control starts with the **same exact recorded Balanced output** on the same
development message. Archived Balanced prompts, policy and answers are preserved.

| Name | Intervention | What the comparison can establish |
|---|---|---|
| `balanced_replay` | None | Common output baseline; no fresh latency measurement |
| `independent_policy_veto` (E1 diagnostic) | Apply v2 policy to an independently extracted, customer-only request frame; replace an automatic output only when that policy requires escalation | Whether an independent policy check catches unsafe releases; also shows extra unnecessary escalations |
| `prerequisite_veto` (E2 diagnostic) | Enforce deterministic issue, known-fact and prior-step prerequisites on the **old exact card**; ignore frame risk and confidence | Whether executable applicability catches wrong-issue advice or repeated known questions |
| `combined_veto` | Apply both vetoes | Their overlap and combined coverage cost on the fixed stored answers |
| `unchanged_output_policy_rescore` | Score identical recorded routes against original and v2 labels | How much the reported routing change comes from the labeling target alone; behavior and calls remain identical |

E1 includes the whole prospective policy: mandatory risks, unsupported language
and uninterpretable input. It is therefore named `independent_policy_veto`, rather
than implying it changes only one risk family. No available answer can clear a
mandatory risk in this overlay. E2 intentionally allows the original risk defects
to remain; it is a research control and cannot be used as a serving agent.

The policy rescore is **not** a behavior-changing policy-only agent. A future live
policy wrapper must run identical base calls and additionally charge its frame
extraction call, retries and wall time. These artifacts make no such live claim.
Veto-only controls cannot recover old false escalations, and need not reproduce
the gains of an end-to-end agent trained or prompted differently.

## Freeze and run the offline controls

Wait until the Verified development run is complete and sealed. Its first stage
receives customer text and the frozen policy before any answer inventory, source
claim or retrieved history. The export verifies that implementation, policy and
exact message hashes match. Extraction results are **AI-authored**, even where
older, unrelated score artifacts have a human attestation.

```powershell
$Candidate = "results/verified_dev_v2"
$Frames = "results/verified_dev_frames_example_20260918_01"
$Ablation = "results/verified_ablation_example_20260918_01"

python scripts/27_verified_ablation.py frames `
  --run $Candidate `
  --labels data/verified_dev/labels.jsonl `
  --out $Frames

python scripts/27_verified_ablation.py prepare `
  --predictions results/balanced_confirmation/predictions.jsonl `
  --old-labels data/balanced_confirmation/labels.jsonl `
  --labels data/verified_dev/labels.jsonl `
  --frames $Frames `
  --out $Ablation
```

`results/verified_dev_v2` is a completed source run, not an output to overwrite.
The example output names must be unused; replace them for each new study. Frame
export requires the source run's matching extraction implementation and policy.
Use its matching source checkout if the active implementation has changed, or
select a newly completed full development run. Existing
`results/verified_dev_frames_v1` and `results/verified_ablation_v1` are retained
artifacts, not fresh output directories.

The first command writes `frames.jsonl` and `FRAMES.lock.json`. These bind the
source execution, model, policy, inference timing, customer text and extraction
content. Invalid or unavailable extraction remains explicitly unavailable. The
second command verifies the original Balanced execution seal and old label hash,
requires its exact renderer/configuration to match, archives those dependencies,
and records every old card's rendered hash. A different historical card inventory
requires its matching checkout; it is not silently called an applicability defect.
The command then produces all four complete
populations, a routing summary, the frozen current review rubric and a blinded
exact-reply review packet. Existing output directories cannot be overwritten.

The input labels must explicitly have `split: development`. The tools refuse a
confirmation, calibration or challenge run. Old confirmation cases are eligible
only after they have explicitly become inspected development examples for this
new candidate; their original frozen evidence remains unchanged.

### Interpreting counts, cost and reply quality

- Every message stays in the denominator. An unavailable frame on an attempted
  automatic overlay is a **failed wrapper**, even though its safe holding text
  says that human review is needed. It is not counted as a successful escalation.
- All blocked controls use the same complete, source-independent holding reply.
  They do not add a new procedure, changed source policy or specialist route.
- E2 identifies the old action by **exact rendered reply equality**. Unknown or
  modified card wording fails closed. A compound old question asking device and
  app version is rejected if either was supplied: this control cannot render a
  narrower replacement. Such avoidable handoffs are a limitation, not a finding
  that clarification is intrinsically unsafe.
- E2 does not validate current source freshness or invent new cards. That belongs
  to the separate knowledge-expansion experiment. Applicability is necessary,
  not proof of usefulness, current authority, or correct semantic extraction.
- Archived latency and usage move into `ablation.source_runtime`. There is no
  fresh end-to-end latency, token cost or free-extraction claim. Reusing recorded
  frames avoids spending model calls for this offline diagnostic; a live wrapper
  would have to pay for extraction in addition to the unchanged Balanced calls.
- `useful_coverage` remains null until independent blinded review of the exact
  outputs. An unchanged reply can reuse a prior development rating only when its
  content hash and rubric match and reuse is disclosed. Changed replies need new
  review. Human attestations never transfer automatically.

These comparisons control the reply inventory but share one imperfect extractor.
They measure conditional effects on recorded outputs, not a randomized independent
end-to-end study. In particular, the new frame was collected during the Verified
run rather than before a fresh Balanced invocation; the isolation claim concerns
the information available to extraction, not a fabricated chronology. Freeze the
chosen full candidate before genuinely unseen confirmation.

## Retrieval diagnostic worksheet

`analysis_tools/verified_retrieval_review.py` prepares a separate fixed development
subset. Freeze selection **before** inspecting retrieval results. It compares:

1. The existing BM25 retriever with raw customer text.
2. The same retriever with a query assembled from the request frame.
3. The request-frame query plus a simple issue/known-slot token reranker.

All arms retain identical transitive conversation-component and near-duplicate
exclusions. This is a lexical diagnostic, not a claim that token overlap measures
semantic relevance. Reviewers rate issue relevance, useful diagnostic pattern,
support for a proposed action and current authority separately.

First and later brand replies are reviewed as historical evidence. A later reply
is **not** automatically a resolution, and a historical support message does not
authorize a present-day procedure. Record missing intervening context, unobserved
resolution and absent current authority explicitly. The review packet hides the
retrieval arm, ranking and routing gold; a private hash-bound mapping permits
paired analysis. Blank worksheets are pending reviews, never favorable scores.

```powershell
$RetrievalStudy = "results/verified_retrieval_example_20260918_01"
python analysis_tools/verified_retrieval_review.py freeze `
  --labels data/verified_dev/labels.jsonl `
  --out $RetrievalStudy `
  --reserved-sample data/verified_calibration/examples.jsonl `
  --reserved-sample data/verified_confirmation/examples.jsonl `
  --reserved-sample data/verified_challenge/examples.jsonl `
  --sample-size 20 --seed 2026091806 --k 3

python analysis_tools/verified_retrieval_review.py prepare `
  --out $RetrievalStudy --run $Candidate
```

Use an unused output directory and the completed source run selected above. The
diagnostic must reserve every protected sample reserved by that run; the existing
confirmation sample is mandatory. Reserved text is read only for local overlap
exclusion and is never placed in the review packet. Existing retrieval studies
are frozen evidence; see [status](VERIFIED_STATUS.md) rather than preparing them again.

Freeze only once the dependency versions are stable. Changed selection, corpus,
retrieval/exclusion/normalization code or source-run inputs require a new lock.
The packet includes recorded intermediate turns where available and explicitly
marks absent context. First-versus-last-later selection is deterministic; no reply
is selected because it looks successful. Missing candidates remain visible.

Use `validate-ratings --help` for submitting a completed worksheet copy. Keep the
blank sealed template unchanged. Record an independent AI development review as
AI review, and a human review only when actually performed by the named person.
Do not promote a retrieval change based only on worksheet improvements: compare
the resulting exact replies in a separate controlled development run first.
