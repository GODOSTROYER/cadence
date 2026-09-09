# Cadence

**An evaluated AI support agent for @SpotifyCares.** Given a customer tweet, Cadence classifies the intent, drafts a public reply grounded in how SpotifyCares historically resolved similar issues, and decides whether the reply can go out unreviewed or a human must take the case, with a stated reason. The proof that it works matters more than the system: a hand-labelled golden set, an evaluation harness with baselines, an LLM judge checked against human ratings, and a dashboard that shows the caveats next to the numbers.

Built by Arnav Bule for the Hiver SDE Intern take-home. Report: [REPORT.md](REPORT.md). Decisions: [DECISION_LOG.md](DECISION_LOG.md).

> Headline numbers, baselines, failure modes and the "what is misleading" section live in [REPORT.md](REPORT.md) and in `results/eval_summary.json`; they are filled in by the pipeline below.

## Reproduce the headline results in under 15 minutes

No API key is needed: every Gemini call made for the reported numbers is committed in `cache/llm_cache.sqlite` and replayed byte-for-byte.

```bash
git clone https://github.com/GODOSTROYER/cadence.git && cd cadence
python -m pip install -e ".[dev]"          # Python 3.11+
python -m cadence.cli reproduce            # index (≈2 s) → agent + baselines → judge → metrics → UI export
```

Roughly three minutes on a laptop. Outputs: `results/eval_summary.json`, `results/failure_modes.json`, `results/figures/*.png`, `results/predictions.jsonl`, `results/judge_scores.jsonl`.

Then look at it:

```bash
cd ui && npm install && npm run build && cd ..
python -m cadence.cli serve                # http://127.0.0.1:8000 — dashboard + API
```

(`make reproduce` and `make serve` wrap the same commands.)

### Live mode (your own key)

```bash
cp .env.example .env                       # put GEMINI_API_KEY=... inside (free tier at aistudio.google.com)
python -m cadence.cli run -- --fresh       # re-run the agent live; cache misses hit the API, rate-limited
python -m cadence.cli judge -- --fresh
python -m cadence.cli evaluate
```

The playground at `/agent` answers free text live once a key is present; without one it replays the recorded golden runs.

### From raw data

Download `twcs.csv` from Kaggle ([thoughtvector/customer-support-on-twitter](https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter)) into `data/raw/twcs/twcs.csv`, then:

```bash
python -m cadence.cli prepare-data         # 2.8M rows → 27,627 SpotifyCares threads (≈30 s)
python -m cadence.cli sample               # stratified golden-set candidates
```

The processed brand subset (`data/processed/`) is committed, so this step is optional.

## What it does

```
customer tweet ──► deterministic rules ──► BM25 retrieval (k=6, own thread excluded) ──► one Gemini structured call
                   (money, security,        over 27.6k historical threads,              intent + confidence + reply
                    legal, churn, media)    "usefulness" re-rank towards                + citations + decision proposal
                                            threads with real resolutions
                                                                                        ▼
                                                                          policy layer: rules veto → LLM decision → confidence threshold
                                                                                        ▼
                                                                  AgentResponse: intent, ≤280-char reply, citations, auto_handle | escalate + reason
```

- **Intents** (12, defined from the data): `config/intents.yaml`, method in `docs/TAXONOMY.md`.
- **Escalation policy** (8 reason codes, rules can only add escalations): `config/escalation.yaml`, definition in `CONTRACT.md §5`.
- **Brand voice** measured from 43k replies: `docs/BRAND_VOICE.md`.
- **Golden set** (two independent passes + adjudication, dev/test split): `data/golden/`, guide in `data/golden/LABELLING_GUIDE.md`, sampling in `docs/SAMPLING_NOTE.md`.
- **Evaluation**: `cadence.eval` — accuracy/macro-F1 with bootstrap CIs, escalation precision/recall/auto-handle rate, comparative blind LLM judge on a 5-dimension rubric, judge-vs-human agreement (quadratic-weighted κ, Spearman ρ), failure-mode mining.
- **Baselines**: majority class, keyword rules, TF-IDF + logistic regression (out-of-fold), LLM zero-shot without retrieval, always/never escalate, template reply, nearest-neighbour historical reply.

## Repository map

```
config/            intents.yaml · escalation.yaml · models.yaml
src/cadence/       data · retrieval · llm · agent · baselines · eval · api · cli
scripts/           01_prepare_data … 07_export_ui_data, resolve_links, make_label_chunks, build_golden
data/processed/    spotify_threads.jsonl.gz · spotify_openers.parquet · link_map.json · reply_templates.json · stats.json
data/golden/       golden_set.jsonl · annotations_{a,b}.jsonl · adjudication.jsonl · human_ratings.jsonl · LABELLING_GUIDE.md
results/           predictions.jsonl · judge_scores.jsonl · eval_summary.json · failure_modes.json · figures/
cache/             llm_cache.sqlite (committed replay cache) · bm25_index.pkl (rebuilt in ~1 s)
ui/                Vite + React + Tailwind dashboard: overview, playground, evaluation, golden explorer, failure modes, blind rating, decisions, method
docs/              TAXONOMY.md · BRAND_VOICE.md · SAMPLING_NOTE.md
CONTRACT.md        the schemas and module seams everything was built against
```

## Dashboard

`ui/` is a static-capable React app. `npm run dev:static` renders entirely from `ui/public/data/*.json` (written by `cadence.cli export`); `npm run dev` proxies to the API for the live playground and the blind human-rating flow (`/rate`), which appends to `data/golden/human_ratings.jsonl` and feeds the judge-agreement numbers.

## Tests

```bash
python -m pytest            # 240+ tests, no network, < 20 s
python -m ruff check src scripts tests
cd ui && npm run typecheck && npm run build
```

## What I borrowed

- Dataset: Customer Support on Twitter (Kaggle, thoughtvector), used under its Kaggle terms; the SpotifyCares subset is redistributed here in processed form for reproducibility.
- Libraries: pandas, scikit-learn, scipy, pydantic, FastAPI, google-genai, rich, typer, matplotlib, rapidfuzz; React, Vite, Tailwind, framer-motion, recharts, lucide. BM25 is implemented in `cadence/retrieval/bm25.py` (Okapi BM25, k1=1.5, b=0.75) rather than imported.
- Fonts: Instrument Serif, Geist, Geist Mono via Google Fonts.
- Method references: Cohen's weighted κ (Cohen 1968) via scikit-learn; percentile bootstrap CIs; the comparative/blind judging setup follows common LLM-as-judge practice (shuffled anonymised candidates to counter position bias).
- AI coding assistants were used freely, as the brief allows, for code, the two independent annotation passes and adjudication. The taxonomy, escalation policy, labelling guide, rubric and every decision are written down so anyone can re-label a sample and compare.

## License

MIT.
