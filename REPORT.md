# Cadence — report

**Hiver SDE Intern take-home · Arnav Bule.** Revised engineering evaluation, updated 18 September 2026. Full implementation evidence and alternatives: [audit](docs/IMPLEMENTATION_AUDIT.md). This report distinguishes archived results from new measurements; the new VerifiedAgent implementation remains experimental.

## 1. Problem framing

Cadence answers @SpotifyCares conversation openers with one of 12 intents, a public reply draft grounded in historical support examples, and `auto_handle` or `escalate` with a reason. Spotify was selected because its corpus contains procedural support, not only account-specific redirects. The prepared sample contains 27,627 threads; the underlying conversations are predominantly from 2017.

“Good” means a useful, relevant reply with supported actions and links, subject to escalation safety. Billing, security, private account access and inputs that cannot be understood from text require escalation. Auto-handle coverage is valuable only at an acceptable miss rate. A correct intent or a fluent reply is insufficient. There are no actual refunds, account changes or posted tweets.

The take-home deliberately excludes account tools, full conversation state, image interpretation, fine-tuning and a vector database. A one-call model and lexical retriever are practical here; the experiment must justify any more complex architecture.

## 2. Data, labels and method

The historical dataset has 250 **AI-labelled** examples: 50 dev and 200 nominal test. Earlier work inspected and fixed errors across three runs. Its test set is therefore a regression set, not untouched confirmation. An audit also found 7 of 250 messages with a >90%-similar message in another corpus thread; excluding only the original thread did not eliminate near-duplicate leakage.

A fresh sample of 200 was drawn with seed 2026 after excluding the original candidate pool, taxonomy sample, old labels, overlapping tweet components and near duplicates. Its source lock was committed before inference. Each message has an intent, escalation decision and individual rationale; 81 require escalation. Arnav Bule reviewed and approved all 200 examples and their existing scores. Sampling/de-duplication changes inclusion probabilities; this is not a traffic-weighted production estimate. The detected-English pool still contains one AI-labelled non-English case.

**Human review and approval completed by Arnav Bule for all 200 examples and their existing scores**, confirmed on 16 September 2026. See the [completed human review record](docs/HUMAN_REVIEW.md).

Pipeline: clean input → deterministic rules → BM25 k6 → structured Gemini 3.5 Flash-Lite call → rules, primary/secondary intent defaults and confidence 0.9 → reply integrity checks. Checks cover citation membership, unsupported URLs, resource references, placeholders and certain unsafe commitments. Post-benchmark guards additionally block unsupported completed actions, numeric capability limits and automatic private handoffs. They do not establish semantic entailment. Three current help articles can be attached only when the evidence identifies the relevant procedure.

The original claim that 0.9 met dev recall≥0.9 was incorrect: recall was 0.85, and the selector used its F2 fallback. The revised experiment freezes 0.9; no threshold is selected from fresh benchmark errors. The practical promotion target is recall≥0.90 with lower 95% bound≥0.88, plus no known hard-safety release failures; these are targets, not achieved guarantees.

## 3. Results and baselines

### Frozen revised benchmark — 200 messages, human review completed by Arnav Bule

Execution commit `b8317d6`; all four systems share the same 200 IDs. Majority intent is fitted on old dev labels only. The simple baseline uses keyword intent, rules and the nearest historical reply, without an LLM. Both agent arms share prompt, model and policy, changing only evidence count. All frozen artifacts are under `results/holdout_final/`.

<!-- benchmark-table:start -->
| System | Intent accuracy | Macro-F1 | Escalation recall | Auto-handles | Misses among auto |
|---|---:|---:|---:|---:|---:|
| Majority / always escalate | 0.115 | 0.017 | 1.000 | 0/200 | N/A |
| Keyword / rules / nearest reply | 0.600 | 0.601 | 0.346 | 166/200 | 53/166 |
| Same-prompt agent, k0 | 0.800 | 0.826 | 1.000 | 0/200 | N/A |
| Retrieval agent, k6 | 0.770 | 0.789 | 0.938 | 70/200 | 5/70 |
<!-- benchmark-table:end -->

For k6, paired-example bootstrap 95% intervals (2,000 resamples, seed 2026) are: macro-F1 [.647, .836], escalation recall [.882, .988], coverage [.285, .415], unsafe-auto risk [.014, .138]. The numerical recall gate passes this bootstrap calculation, but known hard release failures prevent a safety claim. CI choice matters: a post-hoc Wilson interval for 76/81 recall has a lower bound around .864, below the .88 target. This is a robustness warning, not a replacement preregistered gate.

**Retrieval did not demonstrate a classification gain.** k6−k0 accuracy difference is −.030, paired CI [−.075, .010], exact McNemar p=.286. Macro-F1 difference is −.0367, CI [−.0873, .0101]. Before policy, raw-model escalation recall is .630 with retrieval versus .790 without: difference −.160, CI [−.246, −.081]. This motivates testing separate routing on new dev data. Final k0 coverage is zero because citation policy vetoes uncited automatic replies; that comparison cannot establish a retrieval safety benefit.

A 20-message development experiment compared normalized pre-guard k6/k0 drafts in both orders: AI judge mean difference +1.15/5, CI [.70, 1.625], order consistency 70%. That is exploratory same-family evidence about drafts, not human usefulness. The full frozen benchmark separately judges released agent versus simple-baseline replies in both orders. Across 200 pairs, the agent scores 4.1075/5 versus 2.6900: paired difference +1.4175, CI [1.1450, 1.6675]. Both-order ship rate is 69% versus 16.5%. Preference order consistency is only 73.5%; first-position mean is 3.635 versus 3.1625 second. Critically, h_003’s obsolete limit and h_168’s fictional DM action both receive 5/5 and “ship” in both orders. Thus this judge rewards plausible historical imitation while missing real release failures. Full evidence is in `results/holdout_final/summary.json`.

The initial attempt stopped at 31 messages per system after a provider deadline error; it remains under `results/holdout/`. After the transport fix and explicit data-transfer approval, the separate frozen run completed all predictions. No failed or partial run was erased. The original repeatedly inspected regression set had .821 macro-F1 and .940 recall; these belong to the archived implementation and are not inherited by new code.

### Runtime and cost

The frozen agent has local successful-prediction p50/p95 of 1,398/2,597.75 ms across 200 live requests. Across both agent arms, 400 receipts consumed 874,386 input and 72,144 output tokens: about $0.443 at published paid rates, not an actual charge. The 400 judge calls add 396,389 input and 129,779 output tokens, a $0.294 counterfactual; three provider ServerError attempts were retried successfully. Failed-attempt token usage is unavailable. Two workers completed about 1.02 calls/second between first and last agent receipts; this excludes startup and is not sustained server capacity. The corpus loads in 0.65 s and index rebuilds in 0.89 s locally; 250 warm searches had p50/p95=0.413/0.826 ms. Process RSS after building/querying was approximately 386 MiB, including Python and all loaded libraries. Thus retrieval compute is not the measured dominant latency. The 100 dev agent calls consumed 219,481 input and 18,029 output tokens. At published paid-tier rates that is about $0.111; calls were requested on configured free-tier keys, with no billing verification. [Google pricing](https://ai.google.dev/gemini-api/docs/pricing).

Eight read-only health requests to the existing deployment ranged from 284 ms to 7,045 ms; its commit is unknown and it predates this branch. This is neither a cold-start distribution nor inference p95. A single local browser/API success took 4,581.5 ms in server middleware, including a 2,542 ms model call; it is a functional smoke test, not an accuracy test or p95. No sustained production throughput or billing invoice was measured. Quotas are per project, not per API key. [Google rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).

## 4. Five concrete failure modes

These are from the new frozen run, not selected successes. Full trace and repair boundaries: [fresh failure analysis](docs/FAILURE_ANALYSIS_FRESH.md).

| Mode / example | Hypothesis | Response |
|---|---|---|
| Ambiguity plus obsolete policy, h_003: unspecified “maximum” and an unseen URL; reply invents a download issue and repeats 3,333 songs on three devices | Historical evidence supplies missing context and obsolete limits | General numeric-capability guard; a correct current number would still not answer the unclear question |
| False action/private handoff, h_168: “please respond to DM”; reply claims a DM was sent. h_191 invites a DM while auto-handled | Historical human actions copied into an agent without those tools | Block completed-action claims; private handoff requires escalation |
| Churn/frustration, h_079 profanity about playlist reordering; h_105 says “time to say goodbye” | A polite answer appears sufficient, despite escalation policy | Preserve misses; do not tune policy phrases against this set |
| Excess escalation: 54 label-negative messages escalated, 26 due to confidence; h_126's feature-suggestion request gets a holding reply | Intent confidence is not safety risk; missing-resource veto can suppress a repairable answer | Compare calibrated risk and verified response actions on new development data |
| Intent boundaries: 46 errors, including seven playback→feedback and five billing→subscription | Complaint tone overrides the underlying issue | Keep secondary intent and publish support; freeze any revised taxonomy before new data |

The final release repair replayed all 200 frozen agent receipts with zero model calls, under `results/post_audit_regression/`. It changes exactly h_003, h_168 and h_191 to holding replies and escalation: 2/67 missed escalations remain, coverage 33.5%, recall 97.53%. No intent prediction changes. It is a **retrospective regression test after error inspection**, not a fresh accuracy improvement. Original judge scores do not apply to changed holding replies. Regex checks remain incomplete; promises phrased differently and irrelevant but valid citations can still pass. Current [Spotify offline documentation](https://support.spotify.com/us/article/listen-offline/) contradicts h_003's historical limits.

## 5. What is misleading about my headline number?

1. **Review scope:** Arnav Bule reviewed and approved all 200 revised benchmark examples and their existing scores. The benchmark measures the cases and policy represented in this sample.
2. **Test reuse:** archived metrics follow repeated error inspection. They are regression results; improved code cannot inherit them.
3. **Rare classes:** some new classes have only 1–5 examples. Twelve-class macro-F1 has high variance and is not traffic-weighted accuracy.
4. **Safety versus coverage:** high recall can be bought by escalating everything. Report missed escalations, auto coverage and unsafe risk among auto-handles together.
5. **Weak judge:** different model does not mean independent family; order changes 30% of preferences in the small dev comparison. The full-run judge also uses both orders. Score CIs do not remove systematic bias.
6. **Grounding proxies:** citations prove membership, not entailment; a current help URL may still be the wrong procedure. 2017 policy is not current policy.
7. **Replay versus execution:** offline reproducibility verifies saved artifacts, not today's model or live endpoint. Successful-call timings omit outright failed requests unless separately counted.
8. **Cost and transport:** configured free tier is not a billing guarantee. Local latency and eight remote health probes cannot support a production SLA.

## 6. One more week

Complete the new blind human labels and reply review, then compare the frozen VerifiedAgent variants on useful automatic coverage, missed escalations, reply defects and request-level cost. The new benchmark requires 200 human-reviewed labels, with a separate 80-case challenge set reviewed before confirmation inference. Previously inspected examples remain development and regression evidence. Prefer better policy-compliant useful coverage under the same safety bound. Add a small deployment canary measuring errors, queueing, cold/warm latency and privacy behavior only after promotion gates pass.

Preserve the simple pipeline and evidence artifacts. Do not spend the week on autonomous tools, fine-tuning, a vector database or an elaborate dashboard. The strongest submission improvement is a claim the reviewer can reproduce and a limitation they can see.


## Supplemental review and routing development

The dashboard and this report share a generated frozen-benchmark publication checked in CI. The separate matched 50-message study has 100 reply ratings: **first reviewed by GPT-6 Astra at extra-high reasoning, then reviewed and verified unchanged by Arnav Bule**, completed 17 September 2026. Verdicts remain 6 ship, 35 edit and 59 reject across both systems. The human-verified AI-assisted scores have κ=0.137, exact agreement 28% and within-one agreement 53% against both orders of the original Gemini judge. Initial scores were visible to the human reviewer; this is verification rather than an independent blind pass. The original frozen artifacts remain unchanged; [the later human verification](results/review_study/arnav_verified_summary.json) records the completed comparison.

The authorized 30-message Gemini development experiment also completed: current versus selective routing has intent accuracy 76.7% versus 83.3%, escalation recall 85.7% versus 100%, automatic coverage 26.7% versus 36.7%, and two versus zero missed escalations. Selective routing uses 41 versus 30 calls, with lower token totals but slightly higher p95 latency. Decision-accuracy difference is +23.3 points, paired 95% interval [6.7, 43.3]; intent-accuracy difference includes zero. Labels are AI-authored, the sample is small, and all 90 replies and 276 evidence rows now have completed Astra review. Useful automatic coverage is 2/30 for the reference, 1/30 for selective routing and 2/30 for the trained baseline. The selective path is not promoted. See [results, reproduction and review instructions](docs/IMPROVEMENTS.md).


## Completed quality repairs and fresh confirmation

The earlier quality candidate selects approved, server-rendered response actions, uses dated current sources, and reviews the exact finalized text. Two weaker development iterations were rejected and preserved. A separate 60-case confirmation sample was locked and AI-labelled before inference; this version remains frozen. All 120 replies received a blinded GPT-6 Astra extra-high review, bound to exact reply hashes.

The reference caught 29/33 required escalations versus 33/33 for the candidate. Automatic coverage fell from 22/60 to 4/60; useful automatic coverage was 3/60 versus 4/60. Both produced one useful automatic resolution; the other useful replies were necessary clarifications. Reference/candidate token totals were 154,379/150,347, model calls 60/104, and successful-prediction p95 latency 3.53/6.33 seconds. This one-reply usefulness advantage is too small to establish a robust gain. Development review had favored the reference, 2/30 versus 1/30 useful automatic replies.

The confirmation passes the recorded technical gates but **promotion remains on hold because the new AI reviews are not human-verified**. Arnav's completed verification applies to the earlier 100 ratings. The live demo retains the reference implementation. Full gates, exact sources, known residual issue mismatches, and reproduction are in [quality acceptance](docs/QUALITY_ACCEPTANCE.md). The [six-page PDF](output/pdf/Cadence-Arnav-Bule-Report.pdf) is the submission report; this longer document preserves the engineering detail. The hosted service is a demonstration, not a production support integration.

## Coverage and safety follow-up

The 60-case result left too little automatic coverage. A separate BalancedAgent experiment therefore retains both comparators and tests joint routing, 25 verified answer actions, request-scope enforcement and an exact-reply audit. Failed development attempts remain visible; the follow-up uses a newly locked 80-message confirmation sample. The original confidence threshold and sensitive-intent defaults are preserved.

The [complete before/after comparison and fixed acceptance gates](docs/BALANCED_ACCEPTANCE.md) include raw coverage, useful replies, missed escalations, tokens and latency. Resolution-style replies are reviewer judgments, not observed customer resolutions. New reviews remain AI-authored; the earlier Arnav verification is complete within its original scope. Candidate promotion is separate from accepting the implementation and publishing its evidence.

The new confirmation recovers raw automatic coverage to 30/80 (37.5%), versus 28/80 for reference and 7/80 for quality. Balanced and reference each miss four of 38 required escalations; quality misses none. Thus the selected candidate **does not achieve the fixed coverage-and-safety objective** and remains experimental. Its 386,582 input/output tokens are 1.88 times the reference's 205,542. The [four routing misses](docs/BALANCED_FAILURES.md) expose frustration, discrimination, ambiguity and account-identity policy boundaries. The frozen Balanced implementation and labels remain unchanged; the later VerifiedAgent development is a separate experiment.

All 240 exact replies received a fresh blinded Astra review. Useful automatic replies are **6/80 reference, 6/80 quality and 13/80 balanced**. The balanced total comprises 11 resolution-style replies and two necessary clarifications; these are reviewer judgments, not observed resolutions. Flagged automatic replies are 15, zero and four respectively, so the zero-flagged-reply gate also fails. New human verification is still pending and cannot by itself cure those two technical failures.

## VerifiedAgent implementation status - experimental

VerifiedAgent is a separate implemented candidate. It extracts message facts and risk before seeing historical answers, applies a versioned policy, checks executable action prerequisites, and reviews each exact proposed reply before selection. Current procedures come from a dated official-source registry with applicability and expiry checks. Risk findings cannot be overridden by an attractive answer; handoffs must match the request and the permitted support route. A shared request budget bounds provider attempts and elapsed time, while failed requests and incomplete token usage remain visible in the evaluation.

These safeguards now have separate development evidence; they do not establish reliable performance on unseen customer traffic. The earlier benchmark scores, human approvals and AI-only confirmation reviews remain attached to their original versions and examples. The deployed demo continues to use the reference implementation. VerifiedAgent is not promoted and does not inherit BalancedAgent's measured results.

The pre-patch development revision in `results/verified_dev_v4/` completed 80 fresh requests with no execution failures: **31 automatic replies, 22 policy-compliant useful replies, two missed escalations out of 28 required, and four flagged automatic replies**. All four automatic defects concern wrong-issue guidance; both routing misses concern insufficiently specified music requests. Its end-to-end p95 was 5.69 seconds, across 121 model calls and 347,771 input/output tokens. The 22 useful replies comprise 15 resolution-style responses and seven necessary clarifications; these are AI reviewer judgments, not observed customer resolutions.

These 80 messages had already been inspected, and policy v2 and the stricter review rubric differ from the earlier Balanced study. The new metric also excludes helpful-looking replies on cases whose frozen labels require escalation. Therefore the 22/80 figure is not directly comparable to the earlier published 13/80. New labels and fresh blinded exact-reply reviews are AI-authored. [The full VerifiedAgent study](docs/VERIFIED_STATUS.md) contains the matched development comparison, uncertainty, preserved interrupted runs and separate calibration pilot.

The separate pre-patch calibration pilot in `results/verified_calibration_v1/` completed **100 fresh requests, 33 automatic replies, 22 policy-compliant useful replies and two missed escalations out of 31 required**. All six flagged automatic replies had wrong-issue guidance; one also had a stale-procedure flag. The two misses were legal/safety cases involving alleged speaker damage and possible hearing damage, both routed toward feature feedback. These misses are distinct from the development set's ambiguity errors. The useful replies comprise 12 resolution-style responses and ten clarifications. There were no execution failures; end-to-end p95 was 5.28 seconds, across 151 model calls, 152 known provider attempts and 435,306 input/output tokens. Labels and the independent exact-reply review are AI-authored. This single-candidate calibration pilot is not the final human-labelled matched confirmation.

The follow-up deterministic risk guard, action-scope fixes and explicit knowledge registry v3 are evaluated separately. The [18-case inspected/synthetic regression](results/verified_postpilot_regression_v1/summary.json) completed 18 fresh Gemini requests with no execution failures: four automatic replies, 14 escalations, zero misses among seven required escalations and seven unnecessary escalations. Fresh blinded Astra review found zero flagged automatic replies, but **only one policy-compliant useful reply**, a clarification; there were no useful resolution-style replies. It used 73,901 input/output tokens, with end-to-end p95 of 4.90 seconds. These deliberately selected cases test repair boundaries; they do not demonstrate restored coverage or estimate representative automatic coverage. **The completed development and pilot scores describe the pre-patch implementation**, not the updated code. Fixing inspected failures provides regression evidence; it does not establish new independent confirmation performance or permit promotion.

The next confirmation requires a newly locked **200-case benchmark with human-reviewed labels** and a separately labelled **80-case challenge set**, both reviewed before confirmation inference. Earlier inspected cases may be used for development and regression only. Fresh replies require their own blinded review; Arnav Bule's completed verification of the earlier 100 ratings does not transfer to them. See the [implementation plan](output/analysis/Cadence-Implementation-Plan.md) and [versioned policy](docs/POLICY_V2.md) for the experiment boundaries.

Reproduce the VerifiedAgent development summary offline with `python analysis_tools/verify_portable_summaries.py verified --experiment results/verified_dev_v4`. The portable verifier preserves exact hashes, types, counts and provenance while allowing finite floating-point rounding differences of at most `1e-12` across numerical-library versions.
