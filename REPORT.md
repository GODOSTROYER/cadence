# Cadence — Report

*An evaluated AI support agent for @SpotifyCares. Hiver SDE Intern take-home, Arnav Bule.*

> Numbers marked `TBD` are filled from `results/eval_summary.json` once the live run completes. Every reported metric is on the held-out `test` split of the golden set and carries a bootstrap 95% confidence interval.

## 1. Problem framing

### What the agent does
A customer tweets at @SpotifyCares. Cadence (1) classifies the message into one of 11 intents defined from the data, (2) drafts a public reply grounded in how SpotifyCares historically resolved similar messages, and (3) decides whether that reply can be posted without a human (`auto_handle`) or whether a person must take the case (`escalate`), with a stated reason code and a sentence of justification.

### Why SpotifyCares
I profiled all 108 brands in the dataset. Spotify has 43k brand tweets and 26k conversation openers, roughly 93% English. Crucially, its public replies contain actual resolutions: clean-reinstall steps, "log out everywhere", links to specific help articles, a standard language redirect for non-English messages, and a standard acknowledgement for feature requests. That makes "grounded in historical resolutions" testable. AmazonHelp is bigger but almost every reply moves the conversation to a link; airlines are dominated by cases that legitimately need a human. Spotify also has a recognisable voice (warm, brief, one emoji, agent initials), so a tone dimension in the judge rubric means something.

### What "good" means for this brand
1. **Never post something a human would have to retract.** The costly error is a missed escalation: promising a refund, engaging with a hacked-account report publicly, or replying confidently to a screenshot the model cannot see. Escalation recall is therefore the first number I look at, and the auto-handle rate is only meaningful conditional on it.
2. **Auto-handled replies must be grounded.** A reply is good if every step or link in it can be traced to a historical brand reply for a similar issue or to the brand's written voice guide. Invented URLs or invented policy are scored as failures even when the reply "sounds right".
3. **Sound like SpotifyCares.** ≤280 characters, warm opener, concrete next step, at most one emoji, no grovelling, never asks for passwords or card numbers, asks for a DM only when account access is genuinely needed.
4. **Be honest about uncertainty.** Confidence below a tuned threshold routes to a human with the reason `low_confidence`, and the reason is shown to the reviewer.

### What I chose not to build
- **Multi-turn handling.** The agent answers conversation openers only. Follow-ups in the data mostly happen in DMs we cannot see, so a multi-turn evaluation would be evaluating against missing ground truth.
- **Actual account actions.** No refunds, password resets or plan changes are simulated. The decision layer's job is to route those to a human, not to fake them.
- **Dense/embedding retrieval and fine-tuning.** BM25 with a "usefulness" re-rank was good enough to surface resolution threads; a dense hybrid is the first item on the next-week list, not a prerequisite for a trustworthy evaluation.
- **Non-English support.** Non-English messages are an intent with a fixed, historically-grounded reply (the language redirect), not a translation pipeline.
- **A production web service.** The FastAPI server exists so the dashboard and the blind rating flow work locally; it is not hardened, authenticated or deployed.

## 2. Data and method

### Data
`TBD` from `data/processed/stats.json`: threads, openers, date range, share of first replies asking for a DM, share with links, link-resolution success rate. Cleaning rules and thread reconstruction are specified in `CONTRACT.md §3` and implemented in `cadence.data`.

### Intent taxonomy
Defined from the data by TF-IDF clustering (k=25) plus reading several hundred openers, then frozen before labelling. Final list with boundary rules: `docs/TAXONOMY.md`. Estimated distribution and the hand-labelled calibration sample: `TBD`.

### Golden set
`TBD` examples sampled by the stratified procedure in `docs/SAMPLING_NOTE.md` (keyword buckets per intent to guarantee coverage of rare intents, ≥30% uniform random draws, a deliberate short/media-only bucket), labelled in two independent passes against `data/golden/LABELLING_GUIDE.md`, then adjudicated. Inter-annotator agreement: intent κ `TBD`, escalation κ `TBD`. Split: `TBD` dev / `TBD` test.

### Pipeline
Rules → BM25 retrieval (k=6, the example's own thread excluded) → one Gemini structured call → policy layer (rules veto, LLM decision, confidence threshold) → ≤280-char reply with citations. Details and prompts: `cadence.agent`.

### Evaluation harness
Automated metrics (intent accuracy/macro-F1, escalation precision/recall/auto-handle rate, reason-code accuracy), bootstrap CIs, an LLM judge with a five-dimension rubric run comparatively and blind across three systems, and a human-vs-judge agreement study on 60 blind ratings (quadratic-weighted κ, Spearman ρ, exact and within-one agreement).

## 3. Results

### Headline
`TBD`

### Intent classification vs. baselines
`TBD` — trivial (majority class), simple (keyword rules; TF-IDF + logistic regression, out-of-fold), LLM zero-shot without retrieval, agent.

### Escalation vs. baselines
`TBD` — always-escalate, never-escalate, rules-only, agent; threshold sweep on dev; missed escalations listed.

### Reply quality vs. baselines
`TBD` — template reply, nearest-neighbour historical reply, agent; judge scores per dimension, ship rate, pairwise win rate.

### Does the judge agree with a human?
`TBD`

## 4. Failure analysis — top 5 failure modes
`TBD` (from `results/failure_modes.json`, refined by hand with real examples and hypotheses).

## 5. What is misleading about my headline number
`TBD` — to be written from the final numbers. Known items already: the golden set was designed by the same person who designed the taxonomy and prompt; the judge is from the same model family as the agent; test n is small so CIs are wide; 2017 Twitter openers only; English only; the auto-handle rate depends on a threshold tuned on 50 dev examples; "grounded" is judged against retrieved evidence, so a wrong retrieval that the reply follows faithfully still scores as grounded.

## 6. What I would do with one more week
`TBD`

## Appendix
- Decision log: `DECISION_LOG.md`
- Contract / schemas: `CONTRACT.md`
- Reproduce: `README.md`
