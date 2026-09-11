# Cadence — Report

*An evaluated AI support agent for @SpotifyCares. Hiver SDE Intern take-home, Arnav Bule.*

Every number below is measured on the **200 held-out test examples** of a 250-example golden set (50 dev examples were used only to pick the confidence threshold). Intervals are 95% bootstrap CIs (1,000 resamples). All Gemini calls are cached in the repo; `python -m cadence.cli reproduce` replays them without a key.

## 1. Problem framing

### What the agent does
A customer tweets at @SpotifyCares. Cadence (1) classifies the message into one of 12 intents defined from the data, (2) drafts a public reply grounded in how SpotifyCares historically resolved similar messages, and (3) decides whether that reply can be posted without a human (`auto_handle`) or a person must take the case (`escalate`), with one of eight reason codes and a sentence of justification.

### Why SpotifyCares
I profiled all 108 brands in the dataset. Spotify has 43k brand tweets and 27.6k conversation openers, 98% English. Its public replies contain actual resolutions: clean-reinstall steps, "log out everywhere", links to specific help articles, a standard language redirect for non-English messages, and a standard acknowledgement for feature requests. That makes "grounded in historical resolutions" testable. AmazonHelp is bigger but almost every reply moves the conversation to a link; airlines are dominated by cases that legitimately need a human. Spotify also has a recognisable voice (warm, brief, one emoji, agent initials), so a tone dimension in the judge rubric means something.

### What "good" means for this brand
1. **Never post something a human would have to retract.** The costly error is a missed escalation: promising a refund, engaging publicly with a hacked-account report, or replying confidently to a screenshot the model cannot see. Escalation recall is the first number I look at; the auto-handle rate only means something conditional on it.
2. **Auto-handled replies must be grounded.** Every step or link must trace to a historical brand reply for a similar issue or to the brand's written voice guide. Invented URLs or invented policy count as failures even when the reply sounds right.
3. **Sound like SpotifyCares.** ≤280 characters, warm opener, concrete next step, at most one emoji, no grovelling, never asks for passwords or card numbers, asks for a DM only when account access is genuinely needed.
4. **Be honest about uncertainty.** Confidence below a tuned threshold routes to a human with the reason `low_confidence`, and the reason is shown to the reviewer.

### What I chose not to build
- **Multi-turn handling.** The agent answers conversation openers only; follow-ups mostly happen in DMs the dataset cannot see.
- **Actual account actions.** No refunds, resets or plan changes are simulated; the decision layer routes those to a human.
- **Dense retrieval or fine-tuning.** BM25 with a "usefulness" re-rank surfaces resolution threads well enough to evaluate honestly; a dense hybrid is the first next-week item.
- **Non-English support.** Non-English messages are an intent with a fixed, historically grounded reply (the language redirect), not a translation pipeline.
- **A production service.** The FastAPI server exists so the dashboard and the blind rating flow work locally.

## 2. Data and method

**Data.** 2,811,774 tweets → 91,889 in the SpotifyCares reply graph → **27,627 threads** (one per conversation opener), of which 27,056 are English; bulk Oct–Dec 2017. 37% of first brand replies ask for a DM; 89% of the brand's shortened links were resolved to real URLs (most now redirect to the Spotify home page, 8 keep a support-article path). Cleaning rules and thread reconstruction: `CONTRACT.md §3`, `cadence.data`.

**Intent taxonomy.** TF-IDF + k-means (k=25) over the English openers, 200 random openers read end to end, 250 hand-labelled openers to calibrate, then frozen: 12 intents with written boundary rules (`docs/TAXONOMY.md`). A keyword classifier tuned on that calibration set reaches 0.83 accuracy on its held-out half, which is the bar the `simple_keyword` baseline was expected to hit.

**Golden set.** 250 examples drawn by the stratified procedure in `docs/SAMPLING_NOTE.md` (13 per keyword bucket to guarantee coverage of rare intents, 30% uniform random draws, a deliberate short/media-only bucket, 10 genuinely non-English openers). Each was labelled in two independent passes against `data/golden/LABELLING_GUIDE.md`; 19 disagreements were adjudicated with written rationales. Inter-annotator agreement: **κ 0.96 (intent), κ 0.95 (escalation)**, 0 examples dropped. Gold escalation share 41%. Split: 50 dev / 200 test, stratified by intent × decision.

**Pipeline.** Deterministic rules (money, security, legal, churn/abuse, media-only) → BM25 retrieval over all 27.6k threads, k=6, the example's own thread excluded, with a re-rank that favours threads whose brand reply contains real steps or a resolved link → **one** Gemini structured call (`gemini-3.5-flash-lite`) returning intent, confidence, reply, citations and a decision proposal → policy layer: a rule can only *add* an escalation, then the LLM's decision, then `intent_confidence < 0.9` → `low_confidence`. Replies are capped at 280 characters and signed ` /AI`.

**Evaluation harness.** Accuracy/macro-F1 with bootstrap CIs; escalation precision, recall, auto-handle rate, reason-code accuracy, and a threshold sweep; a comparative blind LLM judge (`gemini-3.1-flash-lite`, a different model than the agent) that scores the agent, nearest-neighbour and template replies for the same message in one call with shuffled anonymised labels on five 1–5 dimensions plus three hard flags; judge-vs-human agreement (quadratic-weighted κ, Spearman ρ) computed from blind ratings entered on the dashboard's Rate page; five failure modes mined automatically and then read by hand.

**Models.** Chosen by probing what the free tier allowed on the day (`DECISION_LOG.md` #14): the thinking Flash models carry a ~20-request-per-day cap per key, so the 475-call evaluation runs on Flash-Lite models. The zero-shot baseline uses the *same* model as the agent with no retrieval, which turns it into a clean ablation.

## 3. Results

### Headline

| | Agent | 95% CI |
|---|---|---|
| Intent macro-F1 (12 classes) | **0.82** | 0.77 – 0.87 |
| Intent accuracy | 0.82 | |
| Escalation recall (escalate = positive) | **0.90** | 0.84 – 0.96 |
| Escalation precision | 0.68 | |
| Auto-handle rate | **45%** | 38 – 52% |
| Missed escalations (the costly error) | 8 of 83 | |
| Reason-code accuracy on true escalations | 0.64 | |
| Judge overall reply quality (1–5) | **4.33** | 4.21 – 4.45 |
| Judge "ship as-is" rate | 77% | |
| Hallucinated link/policy flag rate | 5% | |

### Intent classification vs. baselines

| System | Accuracy | Macro-F1 | 95% CI |
|---|---|---|---|
| Trivial: majority class | 0.16 | 0.02 | 0.02 – 0.03 |
| Simple: keyword rules | 0.60 | 0.61 | 0.53 – 0.66 |
| Simple: TF-IDF + logistic regression (out-of-fold) | 0.52 | 0.52 | 0.44 – 0.57 |
| LLM zero-shot, no retrieval (same model) | 0.82 | 0.82 | 0.75 – 0.87 |
| **Agent (rules + retrieval + LLM)** | **0.82** | **0.82** | 0.77 – 0.87 |

The LLM is what carries intent classification; retrieval adds nothing measurable to it (the zero-shot ablation ties). Per-class F1 ranges from 0.97 (`account_hacked_or_security`) and 0.96 (`billing_or_charge`) down to 0.52 (`playlist_or_library`) and 0.71 (`other`, recall 0.55): the escalation-critical intents are the easy ones, the fuzzy boundaries are where errors live.

### Escalation vs. baselines

| System | Precision | Recall | Auto-handle rate | Missed | Unnecessary |
|---|---|---|---|---|---|
| Trivial: always escalate | 0.41 | 1.00 | 0% | 0 | 117 |
| Trivial: never escalate | – | 0.00 | 100% | 83 | 0 |
| Simple: deterministic rules only | 0.97 | 0.36 | 84% | 53 | 1 |
| LLM zero-shot, no retrieval | 0.87 | 0.89 | 57% | 9 | 11 |
| **Agent** | 0.68 | **0.90** | **45%** | **8** | 35 |

The rules alone are precise but blind to `needs_account_lookup` cases (they catch money and security words, not "my family invite fails"). The LLM catches those. The uncomfortable result is the last two rows: the retrieval-augmented agent escalates *less* readily than the same model without evidence, and only reaches 0.90 recall through the confidence guard, which costs 24 extra unnecessary escalations. The threshold sweep makes this explicit:

| Threshold | Recall | Precision | Auto-handle |
|---|---|---|---|
| ≤ 0.60 (guard effectively off) | 0.66 | 0.90 | 69% |
| 0.85 | 0.77 | 0.84 | 62% |
| **0.90 (chosen on dev)** | **0.90** | **0.68** | **45%** |
| 0.95 | 0.98 | 0.57 | 28% |

Reading: seeing six threads where the brand posted self-serve steps makes the model confident it can auto-handle, including cases the policy says need account access. Section 4 (failure mode 1) has the examples and the fix.

### Reply quality vs. baselines (blind comparative judge, 200 messages × 3 replies)

| Reply source | Grounded | Resolves | Tone | Safe | Overall | Ship rate | Wrong-issue flag |
|---|---|---|---|---|---|---|---|
| Trivial: most common brand template | 2.98 | 2.94 | 3.16 | 3.58 | 2.65 | 26% | 16% |
| Simple: nearest-neighbour historical reply | 3.79 | 3.20 | 3.81 | 4.96 | 3.24 | 50% | 33% |
| **Agent** | **4.63** | **4.41** | **4.40** | **4.97** | **4.33** | **77%** | **1%** |

Pairwise, the judge preferred the agent's reply over the nearest-neighbour reply in 65% of messages and over the template in 82%. The template's low "safe" score is the judge penalising a DM request on messages that needed no account access (`asks_sensitive_info` 26%). Retrieval's real contribution is here, not in classification: the same historical replies that do not help the model classify do help it write.

### Does the judge agree with a human?

Not measured yet. The blind rating flow (`/rate`: 60 pairs, 20 per system, system identity hidden, keyboard-driven rubric) writes `data/golden/human_ratings.jsonl`; the next `evaluate` run computes quadratic-weighted κ, Spearman ρ, exact and within-one agreement per dimension and renders them on the Judge-agreement tab. Until those ratings exist, every reply-quality number above is one LLM's opinion of another LLM's writing and should be read as such.

## 4. Failure analysis — top 5 failure modes

See `docs/FAILURE_ANALYSIS.md` and `results/failure_modes.json` (rendered with real examples on the dashboard's Failure modes page). Summary to follow once the hand analysis is complete.

## 5. What is misleading about my headline number

1. **"0.90 escalation recall" is a policy setting, not a model property.** Without the confidence guard the same model reaches 0.66. The guard was chosen on 50 dev examples to hit recall ≥ 0.9, and it buys that recall crudely: precision drops from 0.90 to 0.68 and the auto-handle rate from 69% to 45%. A different min-recall target gives a different headline.
2. **Both annotation passes were AI agents reading the same guide.** κ 0.96 / 0.95 is an upper bound on what two humans would reach, and the gold labels inherit the guide's blind spots. The adjudication log shows where the guide itself was ambiguous (presale codes, "get in touch" requests, informational download questions).
3. **n = 200, and rare intents have ~10 test examples.** Macro-F1 0.82 has a CI of 0.77–0.87; per-class numbers for `metadata_or_artist_issue` (n=9) or `download_or_offline` (n=10) swing by a whole example.
4. **The judge is an LLM of the same family as the agent, and no human ratings exist yet.** 4.33/5 is Gemini 3.1 Flash-Lite grading Gemini 3.5 Flash-Lite. The rubric, shuffling and comparative format reduce but do not remove self-preference and verbosity bias.
5. **Retrieval looks good in reply quality and useless in classification, and I cannot separate the two cleanly.** One call does both, so any retrieval-induced bias in the decision (failure mode 1) is entangled with the reply gains.
6. **"Grounded" means grounded in the retrieved evidence.** A reply that faithfully follows a topically wrong retrieved thread still scores as grounded; the judge only sees the same evidence the agent saw.
7. **2017 English openers only, on a free-tier Lite model.** Multi-turn threads, screenshots and DMs are absent; results on a stronger model would move in both directions (better replies, and possibly more confident over-automation).

## 6. What I would do with one more week

1. **Fix the decision layer first.** Split the single call into decide-then-draft, give the decision step the policy and the customer text but *not* the evidence, and re-measure the sweep; the target is recall ≥ 0.9 at ≥ 60% auto-handle without the crude confidence guard. Add a `needs_account_lookup` rule family (first-person failure verbs + account objects).
2. **Get real human ratings.** 60 blind ratings via `/rate` from two people, report κ, and re-weight the rubric where the judge and humans disagree.
3. **Calibrate confidence.** Fit a temperature/isotonic map from dev confidences to observed accuracy, and replace the fixed 0.9 with a calibrated probability.
4. **Dense hybrid retrieval with usefulness labels.** Embed with a small local model, fuse with BM25, and label 200 retrieved threads for "contains a resolution" to train the re-ranker instead of hand-tuning multipliers.
5. **A second golden set from a different month** to check that the taxonomy and the numbers transfer, and a human labelling pass on 100 examples to measure agent-vs-human agreement on the labels themselves.

## Appendix
- Decision log: `DECISION_LOG.md` (16 decisions)
- Contract / schemas: `CONTRACT.md`
- Reproduce: `README.md`
- Figures: `results/figures/` (confusion matrix, per-intent F1, threshold sweep, judge scores, baselines)
