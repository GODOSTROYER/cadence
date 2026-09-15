# Evaluator's guide — fifteen minutes, in order

*For the Hiver team. Everything below is a claim followed by the place to check it.*

## 0. What you are looking at (one minute)

Cadence is an AI support agent for @SpotifyCares built from the Kaggle "Customer Support on Twitter" dataset. It classifies a customer tweet into one of 12 intents, drafts a public reply grounded in 27,627 real SpotifyCares conversations, and decides whether the reply can go out unreviewed or a human must take over, with a stated reason. The brief said the proof is worth more than the system; most of the repo is the proof.

| Where | What it is |
|---|---|
| **https://www.arnavbule.in/hiver-assignment/** | The pitch page and the live agent (real model, real keys). |
| `REPORT.md` | The six-page report: framing, method, results vs. baselines, failure analysis, what is misleading, next week. |
| `DECISION_LOG.md` | 18 non-obvious decisions, each with the why. |
| `docs/FAILURE_ANALYSIS.md` | Five failure modes with verbatim examples; the two earlier runs are in `_v1.md` / `_v2.md`. |
| `data/golden/` | 250 labelled tweets, both annotation passes, adjudication log, labelling guide. |
| `results/` | Every prediction, every judge score, the summary JSON, figures; `v1/` and `v2/` are the earlier runs. |
| `cache/llm_cache.sqlite` | Every Gemini call ever made for these numbers, so they replay without a key. |

## 1. Try the agent (three minutes)

Open the live site, paste a tweet, watch the decision. Useful probes:

- "my downloads keep disappearing on Android" → should auto-handle with self-serve steps grounded in a cited thread.
- "I was charged twice this month" → must escalate `billing_dispute` (a deterministic rule, not the model's mood).
- "someone else is playing music on my account" → must escalate `account_security`, even if the model wanted to auto-handle (enforced policy default).
- "Check your DMs" → a known failure mode: the model answers confidently; the gold label says a human should look.

The evidence panel shows the six retrieved threads and which ones were cited. The step timeline shows what was a rule, what was the model, and what was the confidence guard. Five free-tier keys are pooled behind the demo; you can paste your own from AI Studio in the playground if they run dry.

## 2. Check the headline numbers against the rubric (five minutes)

All on the 200 held-out test tweets, 95% bootstrap CIs, third and final run.

| Rubric item | Number | Check it |
|---|---|---|
| Intent classification | macro-F1 0.82 [0.76–0.87], 12 intents | `REPORT.md §3`, `results/eval_summary.json → intent` |
| Escalation decision | recall 0.94 [0.88–0.99] at 43% auto-handle; 5 missed of 83 | `results/eval_summary.json → escalation` (the threshold sweep is there too) |
| Reply quality | judge 4.58/5 vs 3.32 nearest historical reply vs 2.56 template; ship rate 90% | `results/judge_scores.jsonl` (600 rows, rationales included) |
| Two baselines minimum | seven: majority, keyword rules, TF-IDF+LR, zero-shot LLM (ablation), always/never escalate, template, nearest neighbour | `REPORT.md §3` tables |
| Golden set 150–250, sampling note | 250, stratified, two passes + adjudication, κ 0.96 / 0.95 | `docs/SAMPLING_NOTE.md`, `data/golden/LABELLING_GUIDE.md`, `data/golden/adjudication.jsonl` |
| LLM judge + human agreement | comparative blind judge on a different model; human-rating flow and κ/ρ wired, **no human ratings collected yet** | `cadence/eval/judge.py`, `cadence/eval/agreement.py`, `REPORT.md §3` last subsection |
| Failure analysis, top 5 | five modes, verbatim examples, fixes measured across three runs | `docs/FAILURE_ANALYSIS.md`, `results/failure_modes.json` |
| "What is misleading" | eight items, the first one is the recall figure itself | `REPORT.md §5`, also printed on the site |
| Reproduce in <15 min | `python -m cadence.cli reproduce`, ~3 min, no key | `README.md` |

## 3. Read the three things I would ask about (four minutes)

1. **The recall number is a policy setting.** Without the confidence guard the same model reaches 0.76 recall at 65% auto-handle. The guard (chosen on 50 dev tweets) moves that to 0.94 at 43%, at the price of 36 unnecessary escalations. The sweep is in the report; the reasoning for the rule that picks the threshold, and why it may never pick "escalate everything", is `DECISION_LOG.md #17`.
2. **Retrieval helps the reply, not the classification.** The zero-shot ablation (same model, no evidence) ties at 0.82 macro-F1 and escalates with better precision. Evidence of self-serve fixes makes the agent more willing to auto-handle; that is failure mode 1.
3. **The labels were produced by two AI passes from one written guide, then adjudicated.** κ 0.96 is therefore an upper bound on human agreement. The guide is in the repo so anyone can re-label a sample and compare; the adjudication log shows where the guide itself was ambiguous.

## 4. If you have two more minutes

- `git log --oneline` reads as the build history: contract first, modules in parallel, golden set, three evaluation runs with the fixes between them.
- `CONTRACT.md` is the spec every module was built against; it is why independently built parts fit.
- `python -m pytest` runs 250+ tests with no network.
