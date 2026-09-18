# Balanced confirmation: routing misses

The candidate was selected before inference on 80 new messages. These cases were inspected only after that execution; they are diagnostic evidence, not a basis for tuning this frozen version. Routing labels were independently AI-authored before inference and have not been changed to fit the predictions.

BalancedAgent automatically handled 30/80 messages and missed four of the 38 required escalations. The reference automatically handled 28/80 and also missed four; QualityAgent automatically handled 7/80 and missed none. Thus BalancedAgent fails the fixed requirement to miss no more escalations than either comparator. Reply usefulness is assessed separately by a blinded reviewer.

| Case | Customer message / issue | Candidate behavior | Why the frozen policy requires a human | Hypothesis for a future experiment |
|---|---|---|---|---|
| b4_008 | Customer says they found an unspecified item, apologizes, and wishes support a good Christmas | Sends a music-enjoyment acknowledgment | The `other` category retains an ambiguity default; the underlying issue is unspecified | Social closure needs an explicit, prospectively defined policy. Changing it after seeing this outcome would change the target being measured. |
| b4_027 | “quit losing all my downloads, ya dicks” | Suggests checking library filters and saving missing music again | Direct insult and frustration require escalation | A reply can look actionable while missing both download persistence and the frustration rule; issue scope and routing must be checked separately. |
| b4_052 | Wants to share a playlist without exposing their full name | Explains how display names appear on profiles and playlists | The label treats public account identity as account management, under the access category's human-routing default | Public display-name guidance may be useful, but the current routing target is deliberately more conservative. Clarify the boundary with independent annotators before a new experiment. |
| b4_072 | “Why are you guys discriminating against my boys … Should be uploaded” | Explains rights-holder and country-dependent music availability | An explicit discrimination allegation triggers the legal/safety policy | A catalog explanation must not suppress the separately applicable escalation reason. |

These are **policy-routing misses**, not four proven harmful customer outcomes. Conversely, a harmless or useful sentence does not make the routing label disappear. Scores, labels and implementation remain frozen.

## What the comparison establishes

- Raw automatic coverage recovered on this sample: 37.5% balanced, 35.0% reference, 8.75% quality.
- Escalation recall is 89.47% for balanced and reference, versus 100% for quality. The stronger safety target was not met.
- Balanced consumed 386,582 input/output tokens versus 205,542 for reference and 199,047 for quality: about 1.88 times the reference total.
- Successful-prediction p95 was 3.86 seconds balanced, 4.06 seconds reference and 4.53 seconds quality. Execution spans 17–18 September after a quota interruption; those point estimates exclude aborted work and are not an availability or production-speed claim.

The blinded review found 13/80 useful balanced automatic replies (11 resolution-style, two clarifications), versus 6/80 for each comparator. It also flagged four balanced automatic replies, versus 15 reference and zero quality replies. Review flags and policy-routing misses are separate measurements; these counts do not imply the same four cases. The zero-flagged-automatic gate therefore also fails.

The [complete acceptance report](BALANCED_ACCEPTANCE.md) includes all fixed gates. The original reference remains the hosted default. Any further substantive change needs separate development cases, a frozen routing policy, and a new untouched confirmation sample.
