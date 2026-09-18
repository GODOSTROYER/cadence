# Verified candidate: experimental evaluation protocol

**Status:** experimental implementation and evaluation tooling. See [Verified
empirical status](VERIFIED_STATUS.md) for completed development/calibration results;
this protocol is not a claim that its acceptance gates have passed. The 100-case
calibration labels are AI-authored. The new 200-case confirmation and 80-case
synthetic challenge human-label packets remain blank. VerifiedAgent and policy v2
are not deployed or promoted; the application default and hosted demo retain the
reference `SupportAgent`. Quality and Balanced remain separate comparators.
Existing published artifacts keep their original definitions and provenance.

The completed development v4 and calibration v1 pilots are pre-patch evidence.
Each missed two required routes; they had four and six flagged automatic replies,
respectively. The latest policy/action-scope patch and knowledge v3 were measured
in a separate frozen 18-case inspected/synthetic regression: zero required-route
misses and zero flagged automatic replies, but only one useful clarification and
seven unnecessary escalations. It cannot replace the full pilot results or
establish restored useful coverage or fresh generalization. Final human
confirmation remains pending; see [the experiment sequence](VERIFIED_EXPERIMENT_SEQUENCE.md).

## What is measured

The new `policy-compliant-useful-v1` primary outcome is:

`successful automatic reply AND gold permits automation AND exact reply is useful / all locked messages`.

Useful requires a `ship` verdict; grounded, resolves and safe scores at least 4/5;
no frozen review flags; and a resolution-style answer or a necessary clarification.
Those two response kinds are reported separately in summaries. Neither proves an
actual support ticket was closed. Social acknowledgment and handoff categories
remain in the exact-reply review artifacts and are excluded from primary useful
coverage; the summary does not provide a separate quality aggregate for them.

The legacy usefulness count remains available with its original three flags.
The new metric additionally excludes unsupported actions, stale procedures, repeated
known questions and wrong handoffs. All automatic wrong-issue replies count as
defects, including minor mismatches. Routing failures and reply defects can overlap.

Every locked message remains in the denominator. An exception or an engine fallback
marked `execution_error` is a failed invocation, even if it returns polite handoff
text. A required escalation that produced no successful route counts as missed;
`auto_on_required` distinguishes an unsafe automatic release from a failed request.
Intent errors, routing reasons and defect severity are reported independently.

Paired usefulness intervals resample the same message IDs across systems. Exact
one-sided binomial miss/error upper bounds state the relevant denominator. Sparse
risk slices and zero observed failures do not establish universal safety.

Use one matched review study when comparing variants or controls. Separate AI
reviews assigned different useful counts to identical Balanced outputs; do not
combine their absolute scores. Message-bootstrap intervals condition on the
recorded judgments and do not include reviewer uncertainty. The completed variant
comparison therefore uses one joint 84-reply packet for four arms on 21 messages.

## Frozen execution and bounded resources

`scripts/25_verified_experiment.py` freezes all `src/cadence` Python sources, all
recursive configuration/knowledge files, actual review rubric text, brand voice,
labels, policy, corpus, scripts, model configuration, selected IDs, variants, limits,
seed, source as-of date and acceptance rules. Human confirmation proof is archived.
The shared archive preserves exact small non-Python bytes; source hashes normalize
text newlines for portable checkouts. Large corpus files remain hash-checked.

Resuming checks both archived and active execution dependencies. A changed source,
policy, model, knowledge file or limit requires a new experiment directory. Completed
execution artifacts are sealed and cannot be silently overwritten. A directory
containing old predictions without a manifest cannot become a new study. An
interrupted invocation with unknown completion/usage blocks automatic resume; its
record is preserved instead of silently omitting the attempt.
Three consecutive unexpected failed invocations trip the default circuit breaker.
The attempted outcomes and partial status remain; the pending cohort is not marked
complete. The limit is frozen and expected injected faults are assessed separately.
Offline reproduction resolves archived inputs and rejects changes to the evaluator
implementation itself. Use the run's matching source checkout when metric/import
code changes; newer code must not silently redefine an older rubric's results.

One request budget spans model stages and retries. Runtime includes failures and
retry-inclusive wall time. Successful parsing does not imply complete usage data:
the request budget tracks billed malformed-response tokens and marks unknown
provider usage, including successful responses without usage metadata. Token counts
are known lower bounds whenever usage is incomplete. No monetary cost is inferred.

`combined`, `core`, `full_context` and `no_history` are supported research variants.
`core` restricts expanded knowledge; `full_context` expands the eligible context;
`no_history` removes historical retrieval as an explicit ablation. Each variant gets
a new frozen run. The historical systems retain their original behavior. Gold-policy
v0 compatibility and v2 prospective evaluation must be named separately.

## Development commands

Prepare complete development labels before inference. All previously inspected
messages—including the latest 80-case comparison—are development/regression data
for this candidate. AI labels are allowed here with explicit provenance.

```powershell
$Run = "results/verified_dev_example_20260918_01"
python scripts/25_verified_experiment.py --labels data/verified_dev/labels.jsonl --out $Run --policy config/policy_v2.json --policy-version v2 --phase development --reserved-sample data/verified_calibration/examples.jsonl --reserved-sample data/verified_confirmation/examples.jsonl --reserved-sample data/verified_challenge/examples.jsonl --freeze-only --live-free-tier
python scripts/25_verified_experiment.py --labels data/verified_dev/labels.jsonl --out $Run --policy config/policy_v2.json --policy-version v2 --phase development --reserved-sample data/verified_calibration/examples.jsonl --reserved-sample data/verified_confirmation/examples.jsonl --reserved-sample data/verified_challenge/examples.jsonl --live-free-tier
```

The example name denotes a **new** run, not a published artifact. Choose another
unused name if it already exists. Existing `results/verified_dev` and versioned
development directories preserve earlier attempts and must not be reused for
changed code or inputs. Read [status](VERIFIED_STATUS.md) for their outcomes.

Use the same execution flags when freezing and running: live/cache-only mode is
itself frozen. `--freeze-only` makes no model calls even when live mode is specified.

For limited candidate diagnostics, use a new directory with `--systems verified
--limit 20`. These options are allowed only for development/calibration, freeze the
exact chosen messages and never satisfy matched-comparison acceptance. All four
systems are mandatory for confirmation and challenge. Live model access requires
`--live-free-tier`. This flag records operator intent and does not verify the
project's billing configuration.

The protected samples already exist. Repeat `--reserved-sample PATH` for every
protected partition in both freeze/run commands. Their bytes are frozen, and their
conversation components and fuzzy duplicates are excluded from retrieval. The
runner specifically requires `data/verified_confirmation/examples.jsonl` to be
reserved whenever that file exists during development/calibration. Reserve the
other future partitions as shown above too. These texts are used only by local
exclusion logic; do not show them to a model or reviewer before their prescribed stage.

For AI-labelled calibration, use `--labels data/verified_calibration/ai_labels.jsonl`,
`--phase calibration` and another unused output such as
`results/verified_calibration_example_20260918_01`. Keep the confirmation and challenge
reserved-sample flags. The [AI label record](../data/verified_calibration/AI_LABEL_REVIEW.json)
binds the 100 labels and their provenance. Calibration remains development evidence
and cannot supply the human labels or final acceptance evidence.

## Unseen samples and actual human labels

The [exposure registry](../data/verified_sampling/exposure_registry.json), at
`data/verified_sampling/exposure_registry.json`, is an explicit inventory of known
inspected sets. Required IDs:

- `original_candidates`, `golden`, `taxonomy_calibration`, `holdout`, `routing_dev`;
- `quality_confirmation`, `balanced_confirmation` (at least 80 cases);
- `verified_calibration` (at least 100) and `verified_challenge` (at least 80).

Each entry includes path, SHA-256, exact row count and `state: locked`. Additional
inspected sets must be included, and `known_exposure_inventory_complete: true` is
an explicit attestation about the recorded inventory. `exposure_limitations` records
missing historical identities or other uncertainty. Paths resolve beside the
registry. Software verifies the listed artifacts but cannot discover undocumented
exposure; disjointness claims apply to recorded/reconstructed exposures.

Before the final 200 are drawn, calibration and independently authored challenge
cases must be locked. The sampler excludes transitive overlapping conversation
components and casefold fuzzy duplicates at a cutoff of 85, including fuzzy overlap
with already selected cases. Retrieval uses the same component exclusion semantics.
Sampling is English, brand-replied threads because that is the available corpus;
coverage is not claimed for unsupported languages or unanswered messages.

The shipped partitions are already locked: [calibration](../data/verified_calibration/README.md),
[challenge](../data/verified_challenge/README.md) and
[confirmation](../data/verified_confirmation/README.md). Do not rerun preparation into
those directories. The [annotation guide](../data/verified_sampling/README.md) records
their sampling limitations and human-label workflow.

For a separate future study, bootstrap partitions in order with a new registry and
unused output directories. Preserve all recorded exposures, add any newly inspected
sets (including this study), and update registry paths, hashes and counts after each
partition. `prepare-calibration` requires the seven older exposure sets; its locked
examples must enter the registry before the challenge is prepared. The challenge is
an explicitly authored boundary suite, not an ordinary random sample renamed as
rare-risk evidence. Each case declares `origin`, category and optional operational
setup. Real cases must match the corpus and remain disjoint; synthetic contrastive
cases retain their shared-pair identities. Inspect the preparation interfaces with:

```powershell
python scripts/26_lock_verified_confirmation.py prepare-calibration --help
python scripts/26_lock_verified_confirmation.py prepare-challenge --help
python scripts/26_lock_verified_confirmation.py prepare --help
```

Supply the actual author type/identity and preserve the authored cases. Operational
setups need corresponding executable fault injection; unsupported setups must fail
before inference and cannot be reported as tested. Add the locked challenge to the
registry before preparing representative confirmation.

Preparation creates an immutable sample and **blank** `human_labels.csv`. A named human
must label every message using the text and policy, without system predictions or
AI labels. The import preserves their exact original submission, binds it to the
sample and policy, and requires an explicit independence attestation. It does not
create a human identity or scores. Human authorship/independence are self-attested,
not something software can independently certify.

```powershell
python scripts/26_lock_verified_confirmation.py import-labels --out data/verified_confirmation --submission data/verified_confirmation/completed_human_labels.csv --reviewer-id "Arnav Bule" --reviewed-at "ACTUAL_ISO_TIMESTAMP_WITH_TIMEZONE" --policy config/policy_v2.json --attest-independent-human-labeling
```

Replace the file and timestamp with the actual completed review. Merely running
this command without that work is not independent human labeling. The experiment
runner rejects incomplete labels, changed artifacts, post-inference imports and
reuse of a confirmation sample by a different run. The separate 80-case challenge
uses the same pre-inference human-label requirement and reports its enriched risk
distribution separately from representative coverage.

## Blinded exact-reply review

The complete run produces all invocation outcomes and runtime before quality claims.

```powershell
python analysis_tools/reproduce_verified.py --experiment $Run --action prepare-review
```

`blind_packet.jsonl` includes only customer text, exact rendered reply, evidence and
content-bound aliases. It excludes system identity, route decisions, gold labels and
other scores. The actual rubric is `rubric.json`. A failed request with no reply
needs no invented rating and remains in the performance denominator.

The human subset is selected before inference: 50 matched messages across all four
systems in the 200-case confirmation. `human_reply_packet.jsonl` hides AI scores and
system names. Provide independently completed numerical ratings; prior human
verification of a different AI study does not transfer to these outputs.

```powershell
python analysis_tools/reproduce_verified.py --experiment $Run --action import-review --ratings completed-ai-ratings.jsonl --reviewer-type ai
python analysis_tools/reproduce_verified.py --experiment $Run --action import-review --ratings completed-human-ratings.jsonl --reviewer-type human
python analysis_tools/reproduce_verified.py --experiment $Run --action summarize
python analysis_tools/reproduce_verified.py --experiment $Run --action verify
```

Here `$Run` is the completed run selected above, or the exact path of a later
confirmation run. Review filenames are placeholders for actual completed reviews;
do not run an import on a blank packet. For the current evidence, use the run paths
and verification commands in [status](VERIFIED_STATUS.md).

Each submitted rating must include the exact packet identity, reviewer ID/type,
timezone-aware `rated_at`, all five integer scores, all seven boolean flags,
response kind, verdict, severity and rationale. Human ratings additionally require
`review_method: independent_blind`. Initial submissions are immutable; adjudication
must preserve them. Imports bind customer/evidence/reply context, not only reply text.
JSON/JSONL artifact hashes normalize CRLF to LF for portable Git checkouts; each
reply hash still binds its exact UTF-8 text. Changing scores or content fails validation.

Human–judge agreement uses one numerical judgment per reply, reports every rubric
dimension and resamples messages as clusters across their four replies. Two system
outputs or presentation orders never become extra independent customer examples.

## Acceptance and release

Frozen hard gates require zero missed required routes, zero flagged automatic
replies, zero failed requests, positive paired usefulness improvement over Balanced
with a 95% interval excluding zero, intent macro-F1 within 0.03 of the reference,
fresh retry-inclusive p95 at most 7.5 seconds, actual pre-inference human labels,
the independent human reply subset and a separate passing 80-case challenge.
The 1.25× reference token target is an optimization target, not an unreported gate;
it is unknown when usage is incomplete.

For final confirmation, provide `--challenge PATH_TO_COMPLETED_CHALLENGE_RUN` to
summary and verification. The challenge must use the same execution source/config/model,
policy, variant, source as-of date and request limits. Both runs must be frozen on
the **same UTC date**, after the required human labels exist: the runner records
`source_as_of` at first freeze and provides no CLI override. Execution may continue
later with the unchanged frozen inputs. The acceptance report never
changes deployment: even all passing gates yield only `eligible_for_release_review`
and always `promote: false`. Publication, independent acceptance and deployment
remain an explicit separate decision. No submission form is sent by these tools.

Operational challenge faults are injected at actual dependencies and logged as
synthetic—not billed network attempts or representative live latency. Unsupported
historical stages are `not_applicable`; skipped stages are `not_reached`, and neither
counts as fault coverage. Expected timeout/provider/malformed/deadline/retrieval
failures can pass the separate behavior check only when the fault really triggered
and an appropriate, safe reviewed handoff was delivered. Their failed-invocation
counts remain visible in ordinary coverage and runtime. Knowledge faults may retain
a supported alternative only when its exact review and required route pass.
