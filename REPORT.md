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

Pipeline: clean input → deterministic rules → BM25 k6 → structured Gemini 3.5 Flash-Lite call → rules, primary/secondary intent defaults and confidence 0.9 → reply integrity checks. Checks cover citation membership, unsupported URLs, resource references, placeholders and certain unsafe commitments. They do not establish semantic entailment. Three current help articles can be attached only when the evidence identifies the relevant procedure.

The original claim that 0.9 met dev recall≥0.9 was incorrect: recall was 0.85, and the selector used its F2 fallback. The revised experiment freezes 0.9; no threshold is selected from fresh benchmark errors. The practical promotion target is recall≥0.90 with lower 95% bound≥0.88, plus no known hard-safety release failures; these are targets, not achieved guarantees.

## 3. Results and baselines

### Archived 200-example regression set — old implementation

| System | Intent accuracy | Macro-F1 | Escalation recall | Auto-handle rate |
|---|---:|---:|---:|---:|
| Majority / always escalate |0.15|0.02|1.00|0%|
| Keyword / rules |0.60|0.61|0.41|82%|
| Original zero-shot LLM |0.81|0.822|0.916|52.5%|
| Original retrieval agent |0.815|0.821|0.940|43%|

Original agent macro-F1 CI was[0.76,0.87], recall CI[0.88,0.99]. Its 5 missed escalations among 86 auto-handles give 5.81% unsafe-auto risk under those labels. The more conservative agent had lower decision accuracy than zero-shot: paired difference−7.5 percentage points, 95% CI[−14.0,−0.99], exact McNemar p=0.0357. This is a safety/coverage tradeoff, not universal superiority.

The original judge mean 4.58/5 and 90% ship-as-is are archived, weakly validated scores. The failure review found missing-resource replies that this judge still approved. The historical TF-IDF baseline used out-of-fold training on other test labels, so it is not a clean frozen-training comparison; it is not used as the fresh simple baseline.

### Revised development experiments — exploratory, not the fresh benchmark

These measurements precede the final transport and incident-status guard patch. They do not establish the final patch's end-to-end performance.

| Comparison | Measurement |
|---|---|
| k6 vs k0, same 50 dev messages/prompt/model/policy | Intent accuracy 0.82 vs 0.82; macro-F1 0.844 vs 0.855 |
| Paired macro-F1 difference |−0.0102; 95% bootstrap CI[−0.1181,0.0825] |
| Raw model escalation recall |0.70 vs 0.80; raw decision accuracy 0.86 both |
| Final k6 release policy | Recall 0.90; coverage 34%; 2 unsafe among 17 auto-handles |
| Pre-guard draft quality, 20 message pairs, both orders | k6−k0 mean 1.15/5; 95% CI[0.70,1.625]; order consistency 70% |
| Live local model latency, 50 calls per arm | k6 p50/p95=1,437/2,388.85 ms; k0=1,425/2,320.7 ms |

The k0 final release has zero auto-handling because it cannot provide citations. That is a policy consequence, not evidence retrieval improved safety. An earlier released-reply judge comparison is also retained; it is confounded by these holding replies. The corrected comparison judges the original model drafts before the integrity veto. Same-family AI preference on 20 dev cases is encouraging but not proof of user usefulness.

**Fresh benchmark status: incomplete.** The first run stopped at 31 of 200 messages per system (124 predictions; 69 successful call receipts) because of a provider deadline error. Automatic approval review blocked a resume pending explicit Gemini data-transfer approval. No partial headline is reported. The timeout defect is fixed in final code; a subsequent run must record that new revision. The planned complete comparison includes majority/template fitted from old dev, keyword/nearest historical reply, revised agent, and controlled k0. The preserved manifest and run status are under `results/holdout/`.

### Runtime and cost

The corpus loads in 0.65 s and index rebuilds in 0.89 s locally; 250 warm searches had p50/p95=0.413/0.826 ms. Process RSS after building/querying was approximately 386 MiB, including Python and all loaded libraries. Thus retrieval compute is not the measured dominant latency. The 100 dev agent calls consumed 219,481 input and 18,029 output tokens. At published paid-tier rates that is about $0.111; calls were requested on configured free-tier keys, with no billing verification. [Google pricing](https://ai.google.dev/gemini-api/docs/pricing).

Eight read-only health requests to the existing deployment ranged from 284 ms to 7,045 ms; its commit is unknown and it predates this branch. This is neither a cold-start distribution nor inference p95. No sustained production throughput, browser interaction latency or billing invoice was measured. Quotas are per project, not per API key. [Google rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).

## 4. Five concrete failure modes

Examples below are from the archived regression analysis. They motivated changes before the fresh benchmark; they are not evidence those changes generalize.

| Mode and real example | Hypothesis | Response and remaining uncertainty |
|---|---|---|
| Missing resource: g_105 asks how to apply a Premium offer; reply says “heading to this link?” without a link | Historical shortened URLs no longer resolve to useful articles; model copies a pointer template | Guard dangling references and use narrow verified links. Valid URL still does not prove relevant advice |
| Historical status copied as current: g_127 reports Android sharing crashes; reply claims developers are investigating | Evidence is mistaken for current service state | Prompt and release guard reject explicit investigation/status claims; paraphrases remain a residual risk requiring a stronger action/source policy |
| Retrieval anchoring: g_012, “Andorra != Switzerland :) <url>”, becomes feature feedback | Nouns in neighbors supply a missing issue | Ignore URLs as meaningful words, strengthen ambiguous rules and untrusted-evidence prompt. General deictic interpretation remains difficult |
| Excess escalation: g_051 says Browse fails to load, correctly classified but escalated at 0.85 | Intent uncertainty is conflated with whether public troubleshooting is safe | Do not lower threshold based on these test examples. Compare risk-specific features with new dev data |
| Intent boundary: g_162 asks about a 10,000 song playlist limit, predicted feedback instead of playlist/library | Complaint phrasing overrides taxonomy's issue boundary | Preserve visible boundary rules and report per-class support. Retrieval cannot repair an ambiguous taxonomy by itself |

`docs/FAILURE_ANALYSIS.md` and `results/failure_modes.json` preserve verbatim messages, drafts and hypotheses. Regex integrity checks address only some surface failures; no claim of zero hallucinations is made.

## 5. What is misleading about my headline number?

1. **AI ground truth:** both old and new labels are model-produced. Reviewer/developer overlap and missing human agreement limit trust.
2. **Test reuse:** archived metrics follow repeated error inspection. They are regression results; improved code cannot inherit them.
3. **Rare classes:** some new classes have only 1–5 examples. Twelve-class macro-F1 has high variance and is not traffic-weighted accuracy.
4. **Safety versus coverage:** high recall can be bought by escalating everything. Report missed escalations, auto coverage and unsafe risk among auto-handles together.
5. **Weak judge:** different model does not mean independent family; order changes 30% of preferences in the small dev comparison. Score CIs do not remove systematic bias.
6. **Grounding proxies:** citations prove membership, not entailment; a current help URL may still be the wrong procedure.2017 policy is not current policy.
7. **Replay versus execution:** offline reproducibility verifies saved artifacts, not today's model or live endpoint. Successful-call timings omit outright failed requests unless separately counted.
8. **Cost and transport:** configured free tier is not a billing guarantee. Local latency and eight remote health probes cannot support a production SLA.

## 6. One more week

First establish an independent quality reference if the author later permits it; otherwise keep the explicit AI-only limitation. Create new dev cases and relevance/usable-resolution labels, then compare selective generation, BM25/hybrid and a simple escalation-risk score separately. Freeze the chosen design before another untouched benchmark. Prefer the candidate with better safe coverage under the same recall bound, not the highest isolated intent score. Add a small deployment canary measuring errors, queueing, cold/warm latency and privacy behavior before any production claim.

Preserve the simple pipeline and evidence artifacts. Do not spend the week on autonomous tools, fine-tuning, a vector database or an elaborate dashboard. The strongest submission improvement is a claim the reviewer can reproduce and a limitation they can see.
