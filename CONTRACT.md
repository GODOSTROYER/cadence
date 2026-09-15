# Cadence — Engineering Contract (shared spec for all modules)

**Project:** Cadence — an evaluated AI support agent for **@SpotifyCares**, built for the Hiver SDE Intern take-home.
**Author:** Arnav Bule (GitHub: GODOSTROYER). All code is authored under this identity.
**Repo root:** `Z:\Projects\Hiver` (pushed to `github.com/GODOSTROYER/cadence`).

This document is the single source of truth for file paths, data schemas, module interfaces and
policies. Every module must conform to it so that independently-built parts fit together.
If you must deviate, add a note under "Deviations" at the bottom of this file (append-only).

---

## 0. Ground rules for every builder

- Python 3.12, package `cadence` under `src/cadence/` (src layout). Import as `from cadence.x import y`.
- Dependencies are pinned in `pyproject.toml` (already created). **Do not edit pyproject.toml**; if you need a
  new dependency, append a line to `docs/DEP_REQUESTS.md` and code defensively (optional import).
- Type hints everywhere, pydantic v2 models (or dataclasses) for records, docstrings on public functions.
- No network calls except: Gemini API (via `cadence.llm.gemini` only) and the one-time t.co link resolver.
- Deterministic: fixed seeds (`SEED = 42`), stable sort orders, `random_state` everywhere.
- Windows-friendly: always `pathlib.Path`, `encoding="utf-8"` on every `open()`, never assume `/tmp`.
- All scripts runnable as `python scripts/NN_name.py` from repo root and expose `main(argv=None)`.
- Logging via `cadence.utils.log.get_logger(__name__)`; `rich` progress bars are fine.
- Tests in `tests/test_<module>.py` using pytest; fast (< 5s total per module), no API calls (use mock/cache).
- **Do NOT run git commands** (no init/commit/branch). The orchestrator commits.
- Do not touch files outside your assigned paths except to append to `docs/DEP_REQUESTS.md` or this file's Deviations.
- Write files as UTF-8 (tweets contain emoji). Set `PYTHONIOENCODING=utf-8` when printing tweets on Windows.
- Python is invoked as `python` (3.12). Repo root is the working directory for every script.

## 1. Directory layout

```
Z:\Projects\Hiver
├── README.md                  # reproduce headline results in <15 min
├── REPORT.md                  # the 6-page report
├── DECISION_LOG.md            # 10–15 non-obvious decisions
├── CONTRACT.md                # this file
├── pyproject.toml             # deps pinned
├── Makefile                   # make setup / data / index / golden / run / judge / eval / ui / serve / all
├── .env.example               # GEMINI_API_KEY=...
├── .gitignore
├── config/
│   ├── intents.yaml           # intent taxonomy (id, name, description, examples, default_decision, keywords)
│   ├── escalation.yaml        # escalation policy: reason codes + rule keyword lists
│   └── models.yaml            # model names, RPM/RPD limits, temperature
├── data/
│   ├── raw/twcs/twcs.csv      # Kaggle (gitignored, 516MB)
│   ├── processed/
│   │   ├── spotify_threads.jsonl.gz     # ALL SpotifyCares threads (committed, ~10MB)
│   │   ├── spotify_openers.parquet      # flat table for fast analysis (thread_id, created_at, customer_text, first_reply_text, ...)
│   │   ├── link_map.json                # t.co -> {"url": resolved, "title": str|null, "count": n}
│   │   ├── reply_templates.json         # top-N canonical brand reply templates (for trivial baseline)
│   │   └── stats.json                   # counts used in report
│   └── golden/
│       ├── candidates.jsonl             # ~400 stratified candidates (pre-label)
│       ├── golden_set.jsonl             # FINAL 150–250 labelled examples (schema §7)
│       ├── annotations_a.jsonl          # pass A labels
│       ├── annotations_b.jsonl          # pass B labels
│       ├── adjudication.jsonl           # disagreements + resolution
│       ├── human_ratings.jsonl          # human reply-quality ratings (schema §7)
│       └── LABELLING_GUIDE.md           # labelling guidelines + sampling note
├── cache/
│   ├── llm_cache.sqlite       # committed; every Gemini call keyed by hash (replay without a key)
│   └── bm25_index.pkl         # retrieval index (rebuildable in seconds)
├── results/
│   ├── predictions.jsonl      # per-golden-example outputs of every system (schema §6)
│   ├── judge_scores.jsonl     # per-example judge output for every system (schema §7)
│   ├── eval_summary.json      # everything the UI/report needs (schema §8)
│   ├── failure_modes.json     # top-5 failure modes with examples (schema §9)
│   └── figures/               # png charts for the report (matplotlib)
├── src/cadence/
│   ├── __init__.py
│   ├── config.py              # paths, constants, load yaml configs
│   ├── utils/  (log.py, text.py, io.py, hashing.py)
│   ├── data/   (load.py, threads.py, clean.py, links.py, sample.py)
│   ├── retrieval/ (bm25.py, index.py)
│   ├── llm/    (gemini.py, cache.py, ratelimit.py, mock.py, base.py)
│   ├── agent/  (models.py, prompts.py, rules.py, pipeline.py)
│   ├── baselines/ (trivial.py, simple.py, nn_reply.py, zero_shot.py)
│   ├── eval/   (metrics.py, judge.py, agreement.py, bootstrap.py, failures.py, run_eval.py, figures.py)
│   ├── api/    (server.py)
│   └── cli.py                 # typer CLI: `python -m cadence.cli <command>`
├── scripts/
│   ├── 01_prepare_data.py     # raw csv -> processed/*
│   ├── 02_build_index.py      # processed -> cache/bm25_index.pkl
│   ├── 03_sample_candidates.py# stratified candidate sampling -> data/golden/candidates.jsonl
│   ├── 04_run_agent.py        # golden -> results/predictions.jsonl (agent + baselines)
│   ├── 05_judge.py            # predictions -> results/judge_scores.jsonl
│   ├── 06_evaluate.py         # -> results/eval_summary.json, failure_modes.json, figures
│   ├── 07_export_ui_data.py   # copies results/golden into ui/public/data/*.json for static mode
│   └── resolve_links.py       # t.co resolver (network, one-time)
├── ui/                        # Vite + React + TS + Tailwind (see §11 and ui/DESIGN.md)
└── tests/
```

## 2. Data: source facts (measured)

- `twcs.csv` columns: `tweet_id:int, author_id:str, inbound:bool, created_at:str, text:str, response_tweet_id:str (comma-joined ids or NaN), in_response_to_tweet_id:float (NaN for roots)`.
- 2,811,774 rows; 108 brands. SpotifyCares: 43,265 outbound tweets; 26,068 **openers** (inbound root tweets that received a brand reply). Date range Apr 7 2017 → Dec 2017 (bulk Oct–Nov).
- `created_at` format: `Tue Oct 31 22:10:47 +0000 2017`.
- Handles are anonymized as numeric ids. `@115888`, `@117168`, `@117153`, `@SpotifyCares`, `@spotifycares` all refer to Spotify accounts → strip them. Any other `@\w+` is a customer/other handle → replace with `@user`.
- Brand replies end with agent initials like ` /JI`, ` /NS` → capture into `agent_sig`, strip from `text`.
- Links are `https://t.co/...` (opaque). `https://t.co/ldFdZRiNAt` (10k uses) is the "DM us" card. Resolve top ~150 links with HTTP HEAD (follow redirects, timeout 8s) → `link_map.json`.
- ~93% of openers are English; ~14% contain a URL/media.
- Thread depth: ~72% of openers get exactly one brand reply; ~28% have multi-turn public exchanges.

## 3. Processed thread schema — `data/processed/spotify_threads.jsonl.gz`

One JSON object per opener (conversation), sorted by `opener_tweet_id`:

```json
{
  "thread_id": "t_2200000",
  "opener_tweet_id": 2200000,
  "created_at": "2017-10-31T22:10:47Z",
  "customer_author_id": "115712",
  "customer_text_raw": "@SpotifyCares my app keeps crashing since the update https://t.co/xyz",
  "customer_text": "my app keeps crashing since the update <url>",
  "has_link": true, "n_words": 8, "language": "en",
  "brand_replies": [
    {"tweet_id": 2200001, "created_at": "...", "text_raw": "@115712 Hey there! ... /JI https://t.co/abc",
     "text": "Hey there! Can you let us know the device and OS? We'll take a look <url>", "agent_sig": "JI",
     "links": ["https://t.co/abc"], "resolved_links": ["https://support.spotify.com/..."], "asks_dm": false}
  ],
  "turns": [
    {"role": "customer", "tweet_id": 2200000, "created_at": "...", "text": "..."},
    {"role": "brand", "tweet_id": 2200001, "created_at": "...", "text": "...", "agent_sig": "JI"}
  ],
  "n_brand_replies": 1, "n_turns": 2,
  "first_reply_text": "Hey there! Can you let us know ...",
  "first_reply_asks_dm": false
}
```
`language`: "en" if the text matches a small English stopword heuristic (≥1 of: the, i, my, is, it, to, and, not, can, you, please, why, when, app, spotify... use ≥2 hits for texts > 6 words), else "other".

### 3.1 Cleaning rules (`cadence.data.clean.clean_text(text, role)`)
1. Unescape HTML entities (`&amp;` → `&`).
2. Remove Spotify handles (`@SpotifyCares`, `@spotifycares`, `@115888`, `@117168`, `@117153`, case-insensitive).
3. Replace remaining `@\w+` with `@user`.
4. Replace URLs (`https?://\S+`) with `<url>` (record `has_link`).
5. For `role == "brand"` only: strip trailing agent signature ` /[A-Z]{1,3}` (may precede a URL) → `agent_sig`.
6. Collapse whitespace; keep emoji and punctuation (they carry sentiment).
`asks_dm` = regex `\b(dm|direct message|dms)\b` on lowercase brand text.

## 4. Intent taxonomy — `config/intents.yaml`

Draft (validated/refined by the taxonomy pass with data counts; ids are stable strings):

| id | name | typical message | default decision |
|---|---|---|---|
| `playback_or_app_bug` | Playback / app malfunction | crashes, won't play, skipping, web player broken, error codes, Spotify Connect/device issues | auto_handle (troubleshoot) |
| `download_or_offline` | Downloads / offline mode | downloads disappear, offline mode not working, storage | auto_handle |
| `login_or_password` | Login / password / account access | can't log in, forgot password, Facebook login broken, lost email | escalate (needs_account_lookup) unless generic reset steps suffice |
| `account_hacked_or_security` | Account security | unknown device playing, hacked, email changed by someone else | escalate (account_security) |
| `billing_or_charge` | Billing / charges / refunds | charged unexpectedly, double charge, payment failing, refund, gift card checkout | escalate (billing_dispute) |
| `subscription_or_plan` | Plan / eligibility / upgrade / cancel | student/family/trial/telco bundle/Hulu bundle, upgrade, cancel, price | auto_handle (info) unless account-specific |
| `content_or_availability` | Missing content / greyed-out / region | artist/album missing, greyed out, "put X on Spotify", not available in my country | auto_handle |
| `playlist_or_library` | Playlists / saved music / personalization | playlist songs missing, library disappeared, Wrapped/Top Songs, Daily Mix, recommendations | auto_handle |
| `feature_request_or_feedback` | Product feedback & suggestions | UI complaints, new features, platform requests (Switch, iPhone X) | auto_handle (acknowledge) |
| `non_english` | Message not in English | any non-English request | auto_handle (language redirect) |
| `other` | Praise, thanks, unclear, spam, media-only, off-topic | "thanks!", party invite, "ummm what am I supposed to do? <url>" | escalate if media-only/unclear else auto_handle |

Constraints: 10–12 intents; every intent should be ≥ ~2% of openers except `account_hacked_or_security`
(rare but important). The taxonomy pass may merge/split but must keep ids `snake_case` and update `config/intents.yaml`.

## 5. Escalation policy — `config/escalation.yaml`

**Decision** ∈ {`auto_handle`, `escalate`}.
`auto_handle` means: the drafted public reply can be posted **without human review**. It must be fully
grounded in historical brand practice (self-serve steps, help-article link, acknowledgement, language redirect)
and require no account access, no money movement, no policy exception, no legal/PR exposure.

`escalate` means a human agent must take the case. Exactly one **primary** `reason_code`:

| reason_code | when |
|---|---|
| `billing_dispute` | any money: charges, refunds, double billing, payment failures, price disputes |
| `account_security` | hacked, unknown device, unauthorized changes, identity questions |
| `needs_account_lookup` | resolution requires looking at the account "backstage" (login recovery, missing purchase, plan eligibility check for this user) |
| `high_frustration_or_churn` | explicit churn threat, profanity directed at brand, repeated contact, PR risk |
| `legal_or_safety` | legal threats, harassment, self-harm, discrimination, press |
| `ambiguous_or_media_only` | cannot determine issue from text (screenshot-only, "help", truncated) |
| `low_confidence` | model's intent confidence < threshold (tuned on dev split) |
| `out_of_scope` | not a support request the brand can act on (politics, spam, other companies) |

Hybrid implementation: deterministic **rules** (`cadence.agent.rules.apply_rules(text) -> RuleResult{flags, force_escalate, reason_code, reason}`)
produce `rule_flags` and can force `escalate` (money words, security words, profanity+brand, legal words, media-only/too short).
The LLM proposes a decision + reason; final decision = `escalate` if rules force it OR LLM says escalate OR
intent_confidence < threshold. The stated reason is the rule's reason if forced, else the LLM's. Always include a
one-sentence human-readable `reason`.

## 6. Agent output — `AgentResponse` (pydantic, `cadence.agent.models`)

```json
{
  "id": "g_017",
  "system": "agent",
  "input_text": "...",
  "intent": "billing_or_charge", "intent_confidence": 0.86, "secondary_intent": null,
  "sentiment": "frustrated",
  "reply_draft": "Hey! Sorry about the double charge...",
  "citations": ["t_2200000", "t_2200987"],
  "grounding_notes": "Steps mirror thread t_2200000's reply (clean reinstall).",
  "decision": "escalate",
  "escalation": {"reason_code": "billing_dispute", "reason": "Customer disputes a charge; requires billing access."},
  "rule_flags": ["money_keywords"],
  "evidence": [{"thread_id": "t_2200000", "score": 12.3, "customer_text": "...", "brand_reply": "...", "resolved_links": [], "cited": true}],
  "model": "gemini-2.5-flash", "latency_ms": 1432, "cached": false,
  "trace": {"retrieval_ms": 12, "llm_ms": 1400, "prompt_tokens": 2100, "output_tokens": 240, "llm_decision": "escalate", "llm_reason_code": "billing_dispute", "forced_by_rules": true}
}
```
- `system` ∈ {`agent`, `trivial`, `simple`, `nn_reply`, `llm_zero_shot`}. Baselines fill the same schema
  (`citations`/`evidence` may be empty, `intent_confidence` may be null, `escalation` null when decision is auto_handle).
- `sentiment` ∈ {`positive`, `neutral`, `frustrated`, `angry`}.
- `reply_draft` ≤ 280 chars, may end with the signature ` /AI` (brand style; the agent must never impersonate a human's initials).

## 7. Golden example & rating schemas

`data/golden/golden_set.jsonl` — one object per line:
```json
{
  "id": "g_001", "thread_id": "t_2200000", "split": "test",
  "text": "<cleaned customer_text>", "text_raw": "...", "created_at": "...",
  "historical_brand_reply": "<first brand reply, cleaned>", "historical_thread": [ ...turns... ],
  "gold": {
    "intent": "billing_or_charge", "secondary_intent": null,
    "should_escalate": true, "escalation_reason_code": "billing_dispute",
    "sentiment": "frustrated", "media_only": false, "notes": "double charge after cancel"
  },
  "annotations": {"a": {"intent": "...", "should_escalate": true, "escalation_reason_code": "...", "sentiment": "...", "media_only": false, "notes": "..."},
                  "b": {...}},
  "agreement": {"intent": true, "should_escalate": true},
  "adjudicated": false, "sampling_bucket": "kw:billing"
}
```
`split`: "dev" (≈50, stratified) | "test" (rest). `id`s are `g_` + zero-padded 3-digit.

Human ratings (`data/golden/human_ratings.jsonl`) and judge scores (`results/judge_scores.jsonl`) share:
```json
{"id": "g_001", "system": "agent", "rater": "human" | "<judge model name>",
 "scores": {"grounded": 4, "resolves": 3, "tone": 5, "safe": 5, "overall": 4},
 "flags": {"hallucinated_link_or_policy": false, "asks_sensitive_info": false, "wrong_issue": false},
 "verdict": "ship" | "edit" | "reject", "rationale": "...", "rated_at": "ISO-8601"}
```
Rubric (1–5 ints): **grounded** (every claim/step/link traceable to evidence or general brand practice; 1 = invented policy),
**resolves** (addresses the actual issue with a concrete next step; 1 = irrelevant), **tone** (SpotifyCares voice:
warm, brief, ≤1 emoji, no grovelling, ≤280 chars), **safe** (no refund/compensation promises, no legal commitments,
asks only for a DM — never passwords/card numbers), **overall** (holistic). Verdict: ship (overall ≥4, no flags) / edit / reject.

## 8. `results/eval_summary.json` (consumed by UI + report)

```json
{
  "meta": {"brand": "SpotifyCares", "n_golden": 200, "n_dev": 50, "n_test": 150, "generated_at": "...",
           "agent_model": "...", "judge_model": "...", "git_sha": "...", "cache_hit_rate": 0.97, "threshold": 0.6},
  "headline": {"intent_macro_f1": 0.81, "escalation_recall": 0.94, "auto_handle_rate": 0.52,
               "judge_overall_mean": 4.1, "judge_overall_mean_nn": 2.6,
               "ci95": {"intent_macro_f1": [0.74, 0.87], "escalation_recall": [..], "auto_handle_rate": [..], "judge_overall_mean": [..]}},
  "intent": {
    "labels": ["playback_or_app_bug", "..."],
    "support": {"<id>": 23},
    "systems": {"agent": {"accuracy": 0.8, "macro_f1": 0.78, "weighted_f1": 0.8,
                          "per_class": {"<id>": {"precision": .., "recall": .., "f1": .., "support": ..}},
                          "confusion": {"labels": [...], "matrix": [[..]]}, "ci95": {"accuracy": [..], "macro_f1": [..]}},
                "trivial_majority": {...}, "simple_keyword": {...}, "simple_tfidf_lr": {...}, "llm_zero_shot": {...}}
  },
  "escalation": {"systems": {"agent": {"precision": .., "recall": .., "f1": .., "auto_handle_rate": .., "accuracy": ..,
                                       "missed_escalations": 3, "unnecessary_escalations": 12,
                                       "reason_code_accuracy": .., "confusion": {"tp": .., "fp": .., "fn": .., "tn": ..}, "ci95": {...},
                                       "missed_examples": ["g_012", "g_077"]},
                             "trivial_always_escalate": {...}, "trivial_never_escalate": {...}, "simple_rules": {...}},
                 "threshold_sweep": [{"threshold": 0.5, "recall": .., "precision": .., "auto_handle_rate": ..}, ...]},
  "reply_quality": {"systems": {"agent": {"mean": {"grounded": .., "resolves": .., "tone": .., "safe": .., "overall": ..},
                                          "dist_overall": [n1, n2, n3, n4, n5], "ship_rate": .., "flag_rates": {"hallucinated_link_or_policy": .., "asks_sensitive_info": .., "wrong_issue": ..},
                                          "ci95": {"overall": [..]}},
                                "trivial_template": {...}, "nn_reply": {...}},
                    "pairwise": {"agent_vs_nn_win_rate": 0.78, "agent_vs_trivial_win_rate": 0.9}},
  "judge_agreement": {"n": 60, "weighted_kappa_overall": 0.61, "spearman_overall": 0.72, "exact_agreement": 0.45,
                      "within_one": 0.9, "per_dimension": {"grounded": {"weighted_kappa": .., "spearman": ..}, ...},
                      "pairs": [{"id": "g_001", "system": "agent", "human": 4, "judge": 5}]},
  "annotator_agreement": {"intent_kappa": 0.79, "intent_raw": 0.85, "escalation_kappa": 0.7, "escalation_raw": 0.88, "n_disagreements": 31},
  "cost": {"n_llm_calls": 640, "total_prompt_tokens": .., "total_output_tokens": .., "wall_minutes": ..}
}
```

## 9. `results/failure_modes.json`
```json
[{"id": "fm1", "title": "Screenshot-only messages get confidently classified", "count": 9, "share": 0.06,
  "hypothesis": "...", "examples": [{"golden_id": "g_042", "text": "...", "gold_intent": "...", "pred_intent": "...", "gold_decision": "escalate", "pred_decision": "auto_handle", "reply_draft": "...", "why": "..."}],
  "proposed_fix": "..."}]
```

## 10. API (FastAPI, `cadence.api.server:app`, port 8000)

- `GET  /api/health` → `{status, has_api_key, cache_only, agent_model, judge_model, cache_entries, index_size, n_golden}`
- `POST /api/agent/handle` body `{text: str, mode?: "live"|"cache_only"}` → `AgentResponse` (§6). No key + cache miss → 503 `{detail}`.
- `GET  /api/results` → `eval_summary.json`
- `GET  /api/failures` → `failure_modes.json`
- `GET  /api/golden` → `[GoldenExample & {predictions: {system: AgentResponse}, judge: {system: JudgeScore}}]`
- `GET  /api/golden/{id}` → one merged example
- `GET  /api/ratings` → list; `POST /api/ratings` body = rating record (§7, `rater` forced to "human") → appends to `data/golden/human_ratings.jsonl`
- `GET  /api/rating-queue` → `[{"id", "system_alias": "A"|"B"|"C", "text", "reply_draft", "evidence": [...]}]` blind queue of (example, system) pairs still unrated by the human, system identity hidden behind an alias resolved server-side
- `GET  /api/decisions` → parsed `DECISION_LOG.md` as `[{n, title, decision, why}]`
- `GET  /api/threads/{thread_id}` → processed thread (§3)
- Static: serve `ui/dist` at `/` with SPA fallback when the folder exists. CORS open for `http://localhost:5173`.

## 11. UI (Vite + React 18 + TypeScript + Tailwind v4 + framer-motion + recharts + lucide-react)

Product name **Cadence**. Static mode (`VITE_STATIC=1`) reads `public/data/{eval_summary,failure_modes,golden_merged,decisions,health}.json`
(produced by `scripts/07_export_ui_data.py`) and disables live agent (shows recorded runs). Live mode calls `/api/*`.
Design brief lives in `ui/DESIGN.md`. Routes: `/` Overview, `/agent` Playground, `/eval` Evaluation, `/golden` Explorer,
`/failures` Failure modes, `/rate` Human rating, `/decisions` Decision log, `/method` Method & data.

## 12. LLM layer (`cadence.llm`)

- `cadence.llm.base.LLMClient` protocol: `generate_json(prompt: str, schema: type[BaseModel], *, system: str | None = None, temperature: float | None = None, cache: bool = True) -> tuple[BaseModel, CallMeta]` where `CallMeta{model, cached: bool, latency_ms, prompt_tokens, output_tokens, attempts}`.
- `GeminiClient(model: str, rpm: int, rpd: int, temperature=0.2, api_key=None, cache_path=Paths.LLM_CACHE)` implements it with `google-genai` structured output (`response_mime_type="application/json"`, `response_schema`).
- Cache: SQLite `cache/llm_cache.sqlite`, table `calls(key TEXT PRIMARY KEY, model TEXT, created_at TEXT, system TEXT, prompt TEXT, schema_json TEXT, temperature REAL, response_json TEXT, prompt_tokens INT, output_tokens INT, latency_ms INT)`.
  key = sha256(model | system | prompt | schema_json | temperature). Env `CADENCE_CACHE_ONLY=1` forbids network (raise `CacheMissError`).
- Rate limiter: token bucket per model (RPM) + persisted daily counter (RPD) in the same SQLite (`quota(model, day, n)`); on 429/RESOURCE_EXHAUSTED → exponential backoff (respect retry info if present), max 6 tries; raise `QuotaExhausted` when RPD reached.
- Models from `config/models.yaml`: `agent_model`, `judge_model`, `zero_shot_model`, with `limits` per model; overridable via env `CADENCE_AGENT_MODEL`, `CADENCE_JUDGE_MODEL`.
- `MockClient` returns deterministic canned JSON (fills schema fields with plausible defaults) for tests; selected when `CADENCE_LLM=mock`.
- API key from env `GEMINI_API_KEY` (or `GOOGLE_API_KEY`), loaded via python-dotenv from `.env`.
- Factory: `cadence.llm.get_client(role: "agent"|"judge"|"zero_shot") -> LLMClient`.

## 13. Evaluation protocol

- Golden split: `dev` (≈50) used ONLY for tuning the confidence threshold and prompt iteration; all reported numbers on `test`.
- Intent: accuracy, macro-F1, per-class F1, confusion; bootstrap 95% CI (1000 resamples, seed 42).
- Escalation: `escalate` is the positive class. Report precision/recall/F1, auto-handle rate, missed escalations (FN, the costly error), reason-code accuracy on true positives.
- Reply quality: judge scores (§7) for `agent`, `nn_reply`, `trivial` on every test example. One comparative judge call per example scores all three replies at once, systems shuffled and anonymized as A/B/C (position-bias mitigation). Judge model ≠ agent model.
- Judge agreement: human ratings on a stratified 60-example subset (20 per system, blind) → quadratic-weighted Cohen's κ, Spearman ρ, exact & within-1 agreement on `overall`; per-dimension κ.
- Baselines: intent → majority class, keyword rules, TF-IDF+LogisticRegression (5-fold stratified CV over golden; predictions are out-of-fold), LLM zero-shot (no retrieval, batched 10 messages/call); escalation → always/never escalate, keyword rules; reply → most-common brand template, nearest-neighbour historical reply (BM25 top-1's first brand reply).

## 15. Cross-module interfaces (the seams between independently built parts)

### 15.1 Systems (final list)
`SYSTEMS = ("agent", "trivial", "simple", "simple_keyword", "llm_zero_shot")`
- `agent`: full pipeline (rules + BM25 retrieval + Gemini structured call).
- `trivial`: intent = majority class of golden gold labels; decision = always `escalate` (reason `low_confidence`, reason text "trivial baseline escalates everything"); reply = most common brand template (`reply_templates.json[0]`).
- `simple`: intent = TF-IDF + LogisticRegression, 5-fold stratified out-of-fold predictions over the golden set; decision = deterministic rules only (`cadence.agent.rules`), auto_handle when nothing fires; reply = nearest-neighbour historical reply (BM25 top-1 thread's `first_reply_text`, excluding the example's own thread).
- `simple_keyword`: intent only, from `keywords` in `config/intents.yaml` (first intent whose keyword count is highest; ties → earlier intent; no hit → `other`). Other fields copy `simple`.
- `llm_zero_shot`: intent + decision from the zero-shot model with taxonomy + policy in the prompt, **no retrieval**, batched 10 messages per call; reply_draft empty string.
Reply-quality judging covers `agent`, `simple`, `trivial`. "nn" in `eval_summary.headline.judge_overall_mean_nn` refers to `simple`.

### 15.2 Retriever (`cadence.retrieval.index`)
```python
@dataclass
class Hit:
    thread_id: str
    score: float
    thread: dict          # full processed thread object (§3)

class Retriever:
    @classmethod
    def build(cls, threads: list[dict]) -> "Retriever": ...
    @classmethod
    def load(cls, path: Path = Paths.BM25_INDEX) -> "Retriever": ...
    def save(self, path: Path = Paths.BM25_INDEX) -> None: ...
    def search(self, query: str, k: int = 6, exclude_thread_ids: set[str] | None = None) -> list[Hit]: ...
    def get(self, thread_id: str) -> dict | None: ...
    def __len__(self) -> int: ...
```
`exclude_thread_ids` MUST be used when evaluating a golden example (exclude its own `thread_id`) to avoid leakage.

### 15.3 Agent (`cadence.agent.pipeline`)
```python
class SupportAgent:
    def __init__(self, client: LLMClient, retriever: Retriever, k: int = 6, threshold: float | None = None): ...
    def handle(self, text: str, *, id: str | None = None, exclude_thread_ids: set[str] | None = None) -> AgentResponse: ...
```
`cadence.agent.rules.apply_rules(text: str) -> RuleResult` where
`RuleResult{flags: list[str], soft_flags: list[str], force_escalate: bool, reason_code: str | None, reason: str | None}`.
`cadence.agent.models.AgentResponse` is the pydantic model of §6 (`.model_dump()` → JSON row of predictions.jsonl).

### 15.4 Baselines (`cadence.baselines`)
```python
def run_baselines(golden_rows: list[dict], retriever: Retriever, *, zero_shot_client: LLMClient | None = None,
                  systems: tuple[str, ...] = ("trivial", "simple", "simple_keyword", "llm_zero_shot")) -> dict[str, list[AgentResponse]]
```
Each returned list is aligned with `golden_rows` (same order, `id` copied from the golden row).

### 15.5 Judge (`cadence.eval.judge`)
```python
def run_judge(golden_rows: list[dict], predictions: dict[str, list[AgentResponse | dict]], client: LLMClient,
              systems: tuple[str, ...] = ("agent", "simple", "trivial")) -> list[dict]   # JudgeScore rows (§7)
```
One comparative call per golden example; replies shuffled/anonymised as A/B/C with `random.Random(SEED + index)`.

### 15.6 Decision log format (`DECISION_LOG.md`, parsed by the API)
```
## 1. Title of the decision
**Decision:** what was decided (one or two sentences).
**Why:** the reasoning (one to three sentences).
```
Repeated for each decision; numbers ascending.

### 15.7 Brand voice notes
`docs/BRAND_VOICE.md` (written by the taxonomy pass) describes SpotifyCares' reply style with measured facts
(greetings, sign-offs, emoji rate, length distribution, common phrases, per-intent resolution patterns).
`cadence.agent.prompts` loads it into the system prompt when present and falls back to a built-in summary otherwise.

## 14. Deviations (append-only)

- (none yet)
- **cadence.llm (LLM layer):** the per-minute limiter is a sliding window over the last `rpm` request start times (same guarantee as a token bucket: never more than `rpm` calls in any 60 s) rather than a literal token bucket; `GeminiClient(model, rpm=None, rpd=None, temperature=None, api_key=None, cache_path=Paths.LLM_CACHE, max_output_tokens=None, *, clock, sleeper)` — rpm/rpd/temperature/max_output_tokens default from `config/models.yaml` and the keyword-only `clock`/`sleeper` exist only for tests; `generate_json(cache=False)` skips the lookup but still stores the fresh response so replays work; `CallMeta.output_tokens` = candidate + thinking tokens and `attempts` is 0 on a cache hit; response schemas must avoid `dict[...]`, `extra="allow"`, int Literals/Enums, tuples and recursive models (see the `cadence.llm` package docstring).
- (baselines) `run_baselines` returns `llm_zero_shot` aligned with `golden_rows` when every batch resolves; in cache-only mode, batches raising `CacheMissError` are logged and left out, so that one list can be shorter — consumers should align by `id`. The key is omitted entirely when the system is skipped (no client, no API key, no cache).
- agent: `Trace` carries one extra field `policy_conflict: bool` (final decision auto_handle while the intent's `default_decision` is escalate); `rules.apply_rules` adds a `too_short` flag (reason `ambiguous_or_media_only`) when the message has fewer than `min_words_for_auto_handle` words; `AgentResponse.rule_flags` lists hard flags followed by soft flags (use `trace.forced_by_rules` to know whether rules forced the decision).
- (eval) `eval_summary.json` keys systems by their §15.1 names (`agent`, `trivial`, `simple`, `simple_keyword`, `llm_zero_shot`) rather than the illustrative §8 names (`trivial_majority`, `simple_tfidf_lr`, `simple_rules`); `escalation.systems` additionally contains computed `trivial_always_escalate` / `trivial_never_escalate` baselines. Judge rows carry an extra `rank` (1 = best) and blocks carry `n`; `meta` adds `notes`, `systems`, `min_recall`, `n_boot`; `escalation` adds `threshold`, `threshold_chosen_on` and `unnecessary_examples`. Undefined statistics (e.g. Spearman on constant input) are `null`, never NaN.
- (data pipeline) `link_map.json` entries carry extra keys beyond §1: `original_url` (first hop after t.co), `chain` (full redirect chain), `status`, `error`. `resolved_links` on brand replies uses `cadence.data.links.best_url` (final URL, or the originally shared URL when the final one is a bare homepage and the original is not itself a shortener). `stats.json` adds `share_links_landing_on_homepage`, `n_links_resolved`, `n_links_attempted`, `timings_s`.
- (data pipeline) Openers are inbound root tweets with a brand reply *anywhere* in their same-author/brand reply chain (27,627), not only a direct brand reply (26,085 ≈ the 26,068 quoted in §2). Third-party replies are not followed into a thread. The stopword heuristic classifies 97.9% of openers as English (§2 estimated ~93%).
- (retrieval) `Hit.score` is the re-ranked score (BM25 × usefulness multiplier 1.25 / 0.85 / 1.0), not raw BM25, and hits are de-duplicated on near-identical `customer_text` (rapidfuzz ratio > 90), so `search(k)` can return fewer than `k` hits even when more threads match. The index text is `customer_text + first_reply_text` (decision and hand-check in the `cadence.retrieval.index` docstring); `Retriever.build` takes an extra keyword-only `include_reply` for the comparison. The pickle holds the full thread dicts (54 MB) and `Retriever.load` recomputes the usefulness multipliers.
- (taxonomy) `config/intents.yaml` v1 has 12 intents: the 11 draft ids plus `metadata_or_artist_issue` (content present but wrong — wrong artist/title/cover/version, duplicate artist pages — and artists asking about their own catalogue/profile; ≈3 % of openers, distinct resolution: "we'll pass it to the right team" / Artist Support form). Intent order in the YAML is non_english → account_hacked_or_security → billing_or_charge → login_or_password → download_or_offline → metadata_or_artist_issue → playlist_or_library → content_or_availability → playback_or_app_bug → subscription_or_plan → feature_request_or_feedback → other, because the `simple_keyword` tie-break prefers earlier intents (safer/specific first, `other` last). Keywords include curly-apostrophe variants and a few deliberate overlaps that act as weights. `scripts/03_sample_candidates.py` was re-run as `--per-bucket 25 --min-random-share 0.28` to land at 438 candidates with 25 per intent bucket (defaults give 493).
- UI (ui/): `eval_summary.json` may carry optional additive fields the dashboard reads when present — `meta.caveats: string[]` (Overview callout), `meta.dataset` (Method data facts; falls back to §2 constants), `meta.zero_shot_model`, `judge_agreement.judge_minus_human_mean`, and extra keys under `escalation.systems` (e.g. `llm_zero_shot`). `ui/public/data/intents.json` and `escalation.json` are derived from `config/*.yaml` (mock generator: `ui/mock/generate_mock_data.py`; the export script should regenerate them the same way). The intent taxonomy is 12 intents (v1) rather than the 11 in §4.
- UI (Evaluation + Golden explorer pages): view state is linkable — `/eval?tab=intent|escalation|reply|judge&system=<summary key>` (a `#tab` hash is accepted and normalised) and `/golden?id=<g_id>&q=<search>&intent=<gold>&pred=<predicted>&split=dev|test&correct=correct|incorrect&decision=escalate|auto_handle|mismatch&system=<§15.1 id>` — other pages should deep-link with these. The pages accept both the §8 illustrative system keys and the §15.1 ids, read the optional additive fields `intent.systems[k].ci95.per_class_f1`, `escalation.threshold` / `threshold_chosen_on` / `systems[k].unnecessary_examples`, `meta.notes` / `n_boot`, `reply_quality.systems[k].n`, `judge_agreement.per_dimension[d].n` when present, and treat `reply_quality`, `judge_agreement`, `pairwise` win rates, `mean[d]`, `ship_rate` and every `ci95` as nullable (rendered as "—"). When a system lacks exported per-class CIs, F1 whiskers are recomputed by a seeded bootstrap (1000, seed 42) from the exported test rows only if those rows reproduce the summary's per-class F1; otherwise no whiskers are drawn.

## Audit revision addendum (September 2026)

This addendum supersedes historical narrative claims without changing the archived artifact schemas. All historical annotations and the new200-example benchmark are explicitly AI-reviewed; human labels and judge–human agreement are unavailable. The new set is separate from the50dev/200reused-test historical partition.

`Trace` now records `integrity_flags`, `integrity_blocked` and successful-call `attempts`. Threshold replay must preserve an integrity veto. Sensitive primary OR secondary intents invoke enforced defaults. An unsupported final reply is replaced by a holding reply and escalated. Membership in evidence is necessary for citations but not sufficient proof of semantic grounding.

Deployment does not persist visitor response prompts in the evaluation cache. Local reproduction verifies recorded artifacts and makes no live calls; it is not fresh model inference. Client budgets and UTC counters are local scheduling controls, not provider quota entitlements or provider reset times. The code/label manifest defines each benchmark's execution revision; later documentation changes do not rewrite that provenance.
