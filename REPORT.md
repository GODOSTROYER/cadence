# Cadence — report

**Hiver SDE Intern take-home · Arnav Bule.** Revised engineering evaluation, 16 September 2026. Full implementation evidence and alternatives: [audit](docs/IMPLEMENTATION_AUDIT.md). This report distinguishes archived results from new measurements.

## 1. Problem framing

Cadence answers @SpotifyCares conversation openers with one of 12 intents, a public reply draft grounded in historical support examples, and `auto_handle` or `escalate` with a reason. Spotify was selected because its corpus contains procedural support, not only account-specific redirects. The prepared sample contains 27,627 threads; the underlying conversations are predominantly from 2017.

“Good” means a useful, relevant reply with supported actions and links, subject to escalation safety. Billing, security, private account access and inputs that cannot be understood from text require escalation. Auto-handle coverage is valuable only at an acceptable miss rate. A correct intent or a fluent reply is insufficient. There are no actual refunds, account changes or posted tweets.

The take-home deliberately excludes account tools, full conversation state, image interpretation, fine-tuning and a vector database. A one-call model and lexical retriever are practical here; the experiment must justify any more complex architecture.

## 2. Data, labels and method

The historical dataset has 250 **AI-labelled** examples: 50 dev and 200 nominal test. Earlier work inspected and fixed errors across three runs. Its test set is therefore a regression set, not untouched confirmation. An audit also found 7 of 250 messages with a >90%-similar message in another corpus thread; excluding only the original thread did not eliminate near-duplicate leakage.

A fresh sample of 200 was drawn with seed 2026 after excluding the original candidate pool, taxonomy sample, old labels, overlapping tweet components and near duplicates. Its source lock was committed before inference. Codex read each message and wrote an intent, escalation decision and individual rationale without viewing its prediction. All 200 labels are explicitly `label_source: ai`, and 81 require escalation. Sampling/de-duplication changes inclusion probabilities; this is not a traffic-weighted production estimate. The detected-English pool still contains one AI-labelled non-English case.

**No human review was performed, as requested by the author.** The reviewer also developed code and knew the taxonomy. These labels form an AI-reviewed benchmark, not independent human ground truth. Neither historical AI agreement nor the new judge's order consistency establishes judge–human agreement. That assignment requirement remains unfulfilled rather than being simulated.

Pipeline: clean input → deterministic rules → BM25 k6 → structured Gemini 3.5 Flash-Lite call → rules, primary/secondary intent defaults and confidence 0.9 → reply integrity checks. Checks cover citation membership, unsupported URLs, resource references, placeholders and certain unsafe commitments. Post-benchmark guards additionally block unsupported completed actions, numeric capability limits and automatic private handoffs. They do not establish semantic entailment. Three current help articles can be attached only when the evidence identifies the relevant procedure.

The original claim that 0.9 met dev recall≥0.9 was incorrect: recall was 0.85, and the selector used its F2 fallback. The revised experiment freezes 0.9; no threshold is selected from fresh benchmark errors. The practical promotion target is recall≥0.90 with lower 95% bound≥0.88, plus no known hard-safety release failures; these are targets, not achieved guarantees.

## 3. Results and baselines

### Frozen revised benchmark — 200 AI-reviewed messages

Execution commit `b8317d6`; all four systems share the same 200 IDs. Majority intent is fitted on old dev labels only. The simple baseline uses keyword intent, rules and the nearest historical reply, without an LLM. Both agent arms share prompt, model and policy, changing only evidence count. All frozen artifacts are under `results/holdout_final/`.

| System | Intent accuracy | Macro-F1 | Escalation recall | Auto-handles | Misses among auto |
|---|---:|---:|---:|---:|---:|
| Majority / always escalate / template |.115|.017|1.000|0/200|N/A|
| Keyword / rules / nearest reply |.600|.601|.346|166/200|53/166|
| Same-prompt agent, k0 |.800|.826|1.000|0/200|N/A|
| Retrieval agent, k6 |.770|.789|.938|70/200|5/70|

For k6, paired-example bootstrap 95% intervals (2,000 resamples, seed 2026) are: macro-F1 [.647, .836], escalation recall [.882, .988], coverage [.285, .415], unsafe-auto risk [.014, .138]. The numerical recall gate passes this bootstrap calculation, but known hard release failures prevent a safety claim. CI choice matters: a post-hoc Wilson interval for 76/81 recall has a lower bound around .864, below the .88 target. This is a robustness warning, not a replacement preregistered gate.

**Retrieval did not demonstrate a classification gain.** k6−k0 accuracy difference is −.030, paired CI [−.075, .010], exact McNemar p=.286. Macro-F1 difference is −.0367, CI [−.0873, .0101]. Before policy, raw-model escalation recall is .630 with retrieval versus .790 without: difference −.160, CI [−.246, −.081]. This motivates testing separate routing on new dev data. Final k0 coverage is zero because citation policy vetoes uncited automatic replies; that comparison cannot establish a retrieval safety benefit.

A 20-message development experiment compared normalized pre-guard k6/k0 drafts in both orders: AI judge mean difference +1.15/5, CI [.70, 1.625], order consistency 70%. That is exploratory same-family evidence about drafts, not human usefulness. The full frozen benchmark separately judges released agent versus simple-baseline replies in both orders. Across 200 pairs, the agent scores 4.1075/5 versus 2.6900: paired difference +1.4175, CI [1.1450, 1.6675]. Both-order ship rate is 69% versus 16.5%. Preference order consistency is only 73.5%; first-position mean is 3.635 versus 3.1625 second. Critically, h_003’s obsolete limit and h_168’s fictional DM action both receive 5/5 and “ship” in both orders. Thus this judge rewards plausible historical imitation while missing real release failures. Human agreement is null; full evidence is in `results/holdout_final/summary.json`.

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

1. **AI ground truth:** both old and new labels are model-produced. Reviewer/developer overlap and missing human agreement limit trust.
2. **Test reuse:** archived metrics follow repeated error inspection. They are regression results; improved code cannot inherit them.
3. **Rare classes:** some new classes have only 1–5 examples. Twelve-class macro-F1 has high variance and is not traffic-weighted accuracy.
4. **Safety versus coverage:** high recall can be bought by escalating everything. Report missed escalations, auto coverage and unsafe risk among auto-handles together.
5. **Weak judge:** different model does not mean independent family; order changes 30% of preferences in the small dev comparison. The full-run judge also uses both orders. Score CIs do not remove systematic bias.
6. **Grounding proxies:** citations prove membership, not entailment; a current help URL may still be the wrong procedure.2017 policy is not current policy.
7. **Replay versus execution:** offline reproducibility verifies saved artifacts, not today's model or live endpoint. Successful-call timings omit outright failed requests unless separately counted.
8. **Cost and transport:** configured free tier is not a billing guarantee. Local latency and eight remote health probes cannot support a production SLA.

## 6. One more week

First establish an independent quality reference if the author later permits it; otherwise keep the explicit AI-only limitation. Create new dev cases and relevance/usable-resolution labels, then compare selective generation, BM25/hybrid and a simple escalation-risk score separately. Freeze the chosen design before another untouched benchmark. Prefer the candidate with better safe coverage under the same recall bound, not the highest isolated intent score. Add a small deployment canary measuring errors, queueing, cold/warm latency and privacy behavior before any production claim.

Preserve the simple pipeline and evidence artifacts. Do not spend the week on autonomous tools, fine-tuning, a vector database or an elaborate dashboard. The strongest submission improvement is a claim the reviewer can reproduce and a limitation they can see.
