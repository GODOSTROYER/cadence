# Cadence — task runner. Every target is also available as `python -m cadence.cli <command>`.
# On Windows without make, run the python commands directly (see README).

PY ?= python
export PYTHONIOENCODING=utf-8

.PHONY: help setup data index candidates golden run judge eval export ui ui-dev serve test lint all reproduce

help:
	@echo "make setup       install python deps (+ ui deps if node is present)"
	@echo "make data        raw twcs.csv -> data/processed/*"
	@echo "make index       build BM25 retrieval index"
	@echo "make candidates  stratified golden-set candidates"
	@echo "make run         run agent + baselines on the golden set -> results/predictions.jsonl"
	@echo "make judge       LLM-as-judge on predictions -> results/judge_scores.jsonl"
	@echo "make eval        metrics, CIs, failure modes, figures -> results/eval_summary.json"
	@echo "make export      copy results into ui/public/data for static mode"
	@echo "make ui          build the React UI"
	@echo "make serve       start FastAPI (serves API + built UI) on :8000"
	@echo "make reproduce   index + run + judge + eval + export from the committed cache (no API key needed)"

setup:
	$(PY) -m pip install -e ".[dev]"
	@if command -v npm >/dev/null 2>&1; then cd ui && npm install; else echo "npm not found; skipping ui deps"; fi

data:
	$(PY) scripts/01_prepare_data.py

index:
	$(PY) scripts/02_build_index.py

candidates:
	$(PY) scripts/03_sample_candidates.py

run:
	$(PY) scripts/04_run_agent.py

judge:
	$(PY) scripts/05_judge.py

eval:
	$(PY) scripts/06_evaluate.py

export:
	$(PY) scripts/07_export_ui_data.py

ui:
	cd ui && npm run build

ui-dev:
	cd ui && npm run dev

serve:
	$(PY) -m uvicorn cadence.api.server:app --host 127.0.0.1 --port 8000

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check src scripts tests

# Reproduce the headline numbers from the committed cache in a few minutes; no API key required.
reproduce:
	CADENCE_CACHE_ONLY=1 $(PY) scripts/02_build_index.py
	CADENCE_CACHE_ONLY=1 $(PY) scripts/04_run_agent.py
	CADENCE_CACHE_ONLY=1 $(PY) scripts/05_judge.py
	CADENCE_CACHE_ONLY=1 $(PY) scripts/06_evaluate.py
	$(PY) scripts/07_export_ui_data.py

all: data index run judge eval export ui
