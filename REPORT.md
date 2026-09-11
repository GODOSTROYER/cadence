# Cadence — Report

*An evaluated AI support agent for @SpotifyCares. Hiver SDE Intern take-home, Arnav Bule.*

Every number below is measured on the **200 held-out test examples** of a 250-example golden set (50 dev examples were used only to pick the confidence threshold). Intervals are 95% bootstrap CIs (1,000 resamples). All Gemini calls are cached in the repo; `python -m cadence.cli reproduce` replays them without a key. The numbers are from the **second run**: the first run's failure analysis found three defects, they were fixed, and the agent and judge were re-run; the first run is kept under `results/v1/` and compared in §4.

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

**Data.** 2,811,774 tweets → 91,889 in the SpotifyCares reply graph → **27,627 threads** (one per conversation opener), of which 27,056 are English; 99.6% fall in Oct–Dec 2017. 37% of first brand replies ask for a DM; 89% of the brand's shortened links were resolved, but most now redirect to the Spotify home page and only eight keep a support-article path, which matters for grounding (§4). Cleaning rules and thread reconstruction: `CONTRACT.md §3`, `cadence.data`.

**Intent taxonomy.** TF-IDF + k-means (k=25) over the English openers, 200 random openers read end to end, 250 hand-labelled openers to calibrate, then frozen: 12 intents with written boundary rules (`docs/TAXONOMY.md`). A keyword classifier tuned on that calibration set reaches 0.83 accuracy on its held-out half, the bar the `simple_keyword` baseline was expected to hit (it hits 0.60 on the golden set, whose stratified sampling over-represents hard boundary cases).

**Golden set.** 250 examples drawn by the stratified procedure in `docs/SAMPLING_NOTE.md` (13 per keyword bucket to guarantee coverage of rare intents, 30% uniform random draws, a deliberate short/media-only bucket, 10 genuinely non-English openers). Each was labelled in two independent passes against `data/golden/LABELLING_GUIDE.md`; 19 disagreements were adjudicated with written rationales. Inter-annotator agreement: **κ 0.96 (intent), κ 0.95 (escalation)**, 0 examples dropped. Gold escalation share 41%. Split: 50 dev / 200 test, stratified by intent × decision.

**Pipeline.** Deterministic rules (money, security, legal, churn/abuse, media-only) → BM25 retrieval over all 27.6k threads, k=6, the example's own thread excluded, with a re-rank that favours threads whose brand reply contains real steps or a resolved link → **one** Gemini structured call (`gemini-3.5-flash-lite`) returning intent, confidence, reply, citations and a decision proposal → policy layer: a rule can only *add* an escalation, then the LLM's decision, then `intent_confidence < 0.9` → `low_confidence`. Replies are scrubbed of placeholders and useless links, capped at 280 characters and signed ` /AI`.

**Evaluation harness.** Accuracy/macro-F1 with bootstrap CIs; escalation precision, recall, auto-handle rate, reason-code accuracy, and a threshold sweep; a comparative blind LLM judge (`gemini-3.1-flash-lite`, a different model than the agent) that scores the agent, nearest-neighbour and template replies for the same message in one call with shuffled anonymised labels on five 1–5 dimensions plus three hard flags; judge-vs-human agreement (quadratic-weighted κ, Spearman ρ) computed from blind ratings entered on the dashboard's Rate page; failure modes mined automatically and then read by hand.

**Models.** Chosen by probing what the free tier allowed on the day (`DECISION_LOG.md` #14): the thinking Flash models carry a ~20-request-per-day cap per key, so the 475-call evaluation runs on Flash-Lite models. The zero-shot baseline uses the *same* model as the agent with no retrieval, which turns it into a clean ablation.

## 3. Results

### Headline

| | Agent | 95% CI |
|---|---|---|
| Intent macro-F1 (12 classes) | **0.82** | 0.76 – 0.86 |
| Intent accuracy | 0.81 | |
| Escalation recall (escalate = positive) | **0.93** | 0.87 – 0.98 |
| Escalation precision | 0.68 | |
| Auto-handle rate | **44%** | 37 – 51% |
| Missed escalations (the costly error) | 6 of 83 | |
| Reason-code accuracy on true escalations | 0.71 | |
| Judge overall reply quality (1–5) | **4.50** | 4.37 – 4.63 |
| Judge "ship as-is" rate | 87% | |
| Hallucinated link/policy flag rate | 5% | |

### Intent classification vs. baselines

| System | Accuracy | Macro-F1 | 95% CI |
|---|---|---|---|
| Trivial: majority class | 0.16 | 0.02 | 0.02 – 0.03 |
| Simple: keyword rules | 0.60 | 0.61 | 0.53 – 0.66 |
| Simple: TF-IDF + logistic regression (out-of-fold) | 0.52 | 0.52 | 0.44 – 0.57 |
| LLM zero-shot, no retrieval (same model) | 0.81 | 0.82 | 0.76 – 0.87 |
| **Agent (rules + retrieval + LLM)** | **0.81** | **0.82** | 0.76 – 0.86 |

The LLM is what carries intent classification; retrieval adds nothing measurable to it (the zero-shot ablation ties). Per-class F1 runs from 1.00 (`account_hacked_or_security`) and 0.92 (`billing_or_charge`) down to 0.50 (`playlist_or_library`) and 0.68 (`other`): the escalation-critical intents are the easy ones; the fuzzy boundaries are where errors live.

### Escalation vs. baselines

| System | Precision | Recall | Auto-handle rate | Missed | Unnecessary |
|---|---|---|---|---|---|
| Trivial: always escalate | 0.41 | 1.00 | 0% | 0 | 117 |
| Trivial: never escalate | – | 0.00 | 100% | 83 | 0 |
| Simple: deterministic rules only | 0.97 | 0.41 | 82% | 49 | 1 |
| LLM zero-shot, no retrieval | 0.80 | 0.92 | 53% | 7 | 19 |
| **Agent** | 0.68 | **0.93** | **44%** | **6** | 36 |

The rules alone are precise but blind to `needs_account_lookup` and ambiguous cases. The LLM catches those. The uncomfortable row is the comparison with zero-shot: the retrieval-augmented agent escalates *less* readily on its own than the same model without evidence, and reaches 0.93 recall only through the confidence guard, which costs 17 more unnecessary escalations. The threshold sweep makes this explicit:

| Threshold | Recall | Precision | Auto-handle |
|---|---|---|---|
| ≤ 0.60 (guard effectively off) | 0.73 | 0.88 | 66% |
| 0.85 | 0.84 | 0.85 | 59% |
| **0.90 (chosen on dev)** | **0.93** | **0.68** | **44%** |
| 0.95 | 0.96 | 0.59 | 32% |
| 1.00 (escalate everything) | 1.00 | 0.42 | 1% |

Reading: seeing six threads where the brand posted self-serve steps makes the model confident it can auto-handle, including cases the policy says need a human. §4 has the examples and the fix.

### Reply quality vs. baselines (blind comparative judge, 200 messages × 3 replies)

| Reply source | Grounded | Resolves | Tone | Safe | Overall | Ship rate | Wrong-issue flag |
|---|---|---|---|---|---|---|---|
| Trivial: most common brand template | 2.85 | 2.81 | 3.10 | 3.54 | 2.56 | 23% | 16% |
| Simple: nearest-neighbour historical reply | 3.79 | 3.19 | 3.93 | 4.97 | 3.31 | 52% | 33% |
| **Agent** | **4.58** | **4.28** | **4.77** | **4.99** | **4.50** | **87%** | **1%** |

Pairwise, the judge preferred the agent's reply over the nearest-neighbour reply in 67% of messages and over the template in 92%. The template's low "safe" score is the judge penalising a DM request on messages that needed no account access. Retrieval's real contribution is here, not in classification: the same historical replies that do not help the model classify do help it write.

### Does the judge agree with a human?

Not measured yet. The blind rating flow (`/rate`: 60 pairs, 20 per system, system identity hidden, keyboard-driven rubric) writes `data/golden/human_ratings.jsonl`; the next `evaluate` run computes quadratic-weighted κ, Spearman ρ, exact and within-one agreement per dimension and renders them on the Judge-agreement tab. Until those ratings exist, every reply-quality number above is one LLM's opinion of another LLM's writing and should be read as such.

## 4. Failure analysis

### First run → fixes → second run

The first full run (`results/v1/`) was read error by error (`docs/FAILURE_ANALYSIS_v1.md`). Three findings were defects rather than model limits, and were fixed before the second run:

| Finding in run 1 | Fix | Run 1 → run 2 |
|---|---|---|
| 20 replies (10%) contained a literal `<url>` placeholder copied from the evidence or a bare `https://open.spotify.com/` link | Scrub placeholders and home-page/DM/t.co links from drafts; hide useless resolved links from the model; prompt rule | 20 → 0 replies with placeholder or bare links |
| The judge docked 36 replies for the policy-mandated ` /AI` signature (25 of 36 "edit" verdicts) | Judge prompt states that the signature and "the help article" phrasing are not defects | Ship rate 77% → 87%; judge overall 4.33 → 4.50 |
| 4 of 8 missed escalations were churn threats the regex did not match ("switching to @user", "move to Apple Music", "fucking atrocious") | Wider `churn_or_abuse` rule (verified against benign phrases such as "switch to a family plan") | Missed escalations 8 → 6; recall 0.90 → 0.93 |

What did not change: intent macro-F1 (0.82 both runs), the 5% hallucinated-policy flag rate (the flagged content shifted from links to phrases such as "our engineers are on it" copied from unrelated threads), and the shape of the threshold trade-off.

### Top 5 failure modes (second run)

The full analysis with calibration and missed-escalation tables is in `docs/FAILURE_ANALYSIS.md`; the five modes with three verbatim examples each are in `results/failure_modes.json` and on the dashboard's Failure modes page. In brief:

1. **Missed escalations are dominated by account-specific and ambiguous cases the rules cannot see (6 of 83).** The model drafts confident self-serve steps where the gold policy says a human must look at the account; the zero-shot model, with no evidence in front of it, escalates more of them.
2. **The confidence guard is a blunt instrument.** Most of the 36 unnecessary escalations are correct intents at confidence 0.85, escalated only by the threshold; intent accuracy at 0.85 is barely below accuracy at 0.90, so the cut is not measuring uncertainty.
3. **Copied reassurance and invented specifics.** The judge's hallucination flag now catches phrases lifted from unrelated evidence threads ("the tech folks are investigating") and over-specific promises rather than links.
4. **`other` (recall ≈ 0.6) absorbs the intent of the nearest retrieved thread.** Jokes, screenshot captions, presale codes and "hire me" tweets take a product intent from the evidence; the zero-shot model gets most of these right, which makes this the one clearly retrieval-induced error class.
5. **`playlist_or_library` vs. `playback_or_app_bug` and `feature_request` (F1 0.50).** "Playlist" as a noun pulls messages about broken playback into the playlist intent, and "limit" complaints oscillate between library and feature request; the zero-shot model makes the same mistakes, so this is a taxonomy/prompt boundary, not retrieval.

## 5. What is misleading about my headline number

1. **"0.93 escalation recall" is a policy setting, not a model property.** Without the confidence guard the same model reaches 0.73. The guard was chosen on 50 dev examples to hit recall ≥ 0.9, and it buys that recall crudely: precision drops from 0.88 to 0.68 and the auto-handle rate from 66% to 44%. A different min-recall target gives a different headline, and on the second run the original chooser wanted to escalate *everything* until I excluded that degenerate option (`DECISION_LOG.md` #17).
2. **These are second-run numbers, and the fixes came from reading the test errors.** Each fix targeted a named defect (placeholder links, a judge rubric bug, a regex gap) rather than a score, and the first run is kept for comparison, but a reviewer should treat the improvement from run 1 to run 2 as partly informed by the test set.
3. **Both annotation passes were AI agents reading the same guide.** κ 0.96 / 0.95 is an upper bound on what two humans would reach, and the gold labels inherit the guide's blind spots. The adjudication log shows where the guide itself was ambiguous.
4. **n = 200, and rare intents have ~10 test examples.** Macro-F1 0.82 has a CI of 0.76–0.86; per-class numbers for `metadata_or_artist_issue` (n=9) or `download_or_offline` (n=10) swing by a whole example.
5. **The judge is an LLM of the same family as the agent, and no human ratings exist yet.** 4.50/5 is Gemini 3.1 Flash-Lite grading Gemini 3.5 Flash-Lite. The rubric, shuffling and comparative format reduce but do not remove self-preference and verbosity bias; the first run showed how sensitive the score is to the judge prompt (fixing one rubric bug moved ship rate by ten points).
6. **Retrieval looks good in reply quality and useless in classification, and I cannot separate the two cleanly.** One call does both, so any retrieval-induced bias in the decision (failure modes 1 and 4) is entangled with the reply gains.
7. **"Grounded" means grounded in the retrieved evidence.** A reply that faithfully follows a topically wrong retrieved thread still scores as grounded; the judge only sees the same evidence the agent saw.
8. **2017 English openers only, on a free-tier Lite model.** Multi-turn threads, screenshots and DMs are absent; results on a stronger model would move in both directions.

## 6. What I would do with one more week

1. **Fix the decision layer first.** Split the single call into decide-then-draft, give the decision step the policy and the customer text but *not* the evidence, and re-measure the sweep; the target is recall ≥ 0.9 at ≥ 60% auto-handle without the crude confidence guard. Add a `needs_account_lookup` rule family (first-person failure verbs + account objects).
2. **Get real human ratings.** 60 blind ratings via `/rate` from two people, report κ, and re-weight the rubric where the judge and humans disagree.
3. **Calibrate confidence.** The model uses five confidence values in practice; fit an isotonic map from dev confidences to observed accuracy and replace the fixed cut with a calibrated probability.
4. **Dense hybrid retrieval with usefulness labels.** Embed with a small local model, fuse with BM25, and label 200 retrieved threads for "contains a resolution" to train the re-ranker instead of hand-tuning multipliers; add a topical-mismatch check so copied reassurance from unrelated threads is caught before the judge sees it.
5. **A second golden set from a different month** to check that the taxonomy and the numbers transfer, plus a human labelling pass on 100 examples to measure agent-vs-human agreement on the labels themselves.

## Appendix
- Decision log: `DECISION_LOG.md` (18 decisions)
- Contract / schemas: `CONTRACT.md`
- Reproduce: `README.md`
- Figures: `results/figures/` (confusion matrix, per-intent F1, threshold sweep, judge scores, baselines); first run under `results/v1/`
