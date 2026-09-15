"""Cadence command line: ``python -m cadence.cli <command>`` (or ``cadence <command>`` once installed).

Every pipeline command loads the matching ``scripts/NN_*.py`` file with ``importlib`` and calls its
``main(argv)``; unknown options are passed straight through to the script, so
``python -m cadence.cli run --limit 20`` behaves exactly like ``python scripts/04_run_agent.py --limit 20``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import typer

from cadence import __version__
from cadence.config import Paths
from cadence.utils.log import get_logger

log = get_logger(__name__)

SCRIPTS: dict[str, str] = {
    "reproduce-recorded": "reproduce_recorded.py",
    "prepare-data": "01_prepare_data.py",
    "resolve-links": "resolve_links.py",
    "build-index": "02_build_index.py",
    "sample": "03_sample_candidates.py",
    "run": "04_run_agent.py",
    "judge": "05_judge.py",
    "evaluate": "06_evaluate.py",
    "export": "07_export_ui_data.py",
}
"""CLI command -> script file under ``scripts/``."""

REPRODUCE_STEPS: tuple[str, ...] = ("reproduce-recorded",)
ALL_STEPS: tuple[str, ...] = ("prepare-data", "build-index", "run", "judge", "evaluate", "export")

_PASSTHROUGH = {"allow_extra_args": True, "ignore_unknown_options": True}

app = typer.Typer(
    name="cadence",
    help="Cadence — an evaluated AI support agent for @SpotifyCares.",
    no_args_is_help=True,
    add_completion=False,
    context_settings=_PASSTHROUGH,
)


def scripts_dir() -> Path:
    """``<repo>/scripts`` (resolved at call time so tests can point ``Paths.ROOT`` elsewhere)."""
    return Paths.ROOT / "scripts"


def load_script(filename: str) -> ModuleType:
    """Import ``scripts/<filename>`` as a module without requiring it to be a package."""
    path = scripts_dir() / filename
    if not path.exists():
        raise FileNotFoundError(f"script not found: {path}")
    spec = importlib.util.spec_from_file_location(f"cadence_scripts.{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load script {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_script(command: str, argv: Sequence[str] = ()) -> int:
    """Run the script behind ``command`` with ``argv`` and return its exit code (``None`` counts as 0)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    module = load_script(SCRIPTS[command])
    main = getattr(module, "main", None)
    if not callable(main):
        raise AttributeError(f"{SCRIPTS[command]} does not expose main(argv)")
    log.info("running %s %s", SCRIPTS[command], " ".join(argv))
    result = main(list(argv))
    return int(result or 0)


def _run_or_exit(command: str, argv: Sequence[str]) -> None:
    try:
        code = run_script(command, argv)
    except (FileNotFoundError, ImportError, AttributeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if code:
        raise typer.Exit(code=code)


def _run_steps(steps: Sequence[str]) -> None:
    for step in steps:
        typer.echo(f"==> {step}")
        _run_or_exit(step, [])


def _register_script_command(name: str, help_text: str) -> None:
    @app.command(name=name, help=help_text, context_settings=_PASSTHROUGH)
    def _command(ctx: typer.Context) -> None:
        _run_or_exit(name, ctx.args)


for _name, _help in (
    ("prepare-data", "Raw twcs.csv -> data/processed/* (threads, openers, templates, stats)."),
    ("resolve-links", "Resolve the top t.co links once over the network -> link_map.json."),
    ("build-index", "Build the BM25 retrieval index -> cache/bm25_index.pkl."),
    ("sample", "Stratified golden-set candidate sampling -> data/golden/candidates.jsonl."),
    ("run", "Run the agent and all baselines on the golden set -> results/predictions.jsonl."),
    ("judge", "LLM-as-judge over predictions -> results/judge_scores.jsonl."),
    ("evaluate", "Metrics, CIs, failure modes and figures -> results/eval_summary.json."),
    ("export", "Copy results into ui/public/data/*.json for the static UI."),
):
    _register_script_command(_name, _help)


@app.command(help="Start the FastAPI server (API + built UI).")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address."),
    port: int = typer.Option(8000, "--port", help="Port."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (development)."),
) -> None:
    import uvicorn

    uvicorn.run("cadence.api.server:app", host=host, port=port, reload=reload, log_level="info")


@app.command(help="Reproduce headline results from the committed cache (no API key needed).")
def reproduce() -> None:
    os.environ["CADENCE_CACHE_ONLY"] = "1"
    _run_steps(REPRODUCE_STEPS)


@app.command(name="all", help="Full pipeline: prepare-data, build-index, run, judge, evaluate, export.")
def run_all() -> None:
    _run_steps(ALL_STEPS)


@app.command(help="Print the Cadence version.")
def version() -> None:
    typer.echo(__version__)


if __name__ == "__main__":
    app()
