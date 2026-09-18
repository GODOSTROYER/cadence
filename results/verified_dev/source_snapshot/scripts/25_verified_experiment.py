"""Freeze and run matched Verified experiments; confirmation requires prior human labels.

No network calls occur without --live-free-tier. No command promotes a candidate.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import time
from contextlib import nullcontext
from datetime import UTC, date, datetime
from pathlib import Path

from rapidfuzz import fuzz, process

from cadence.config import Paths, model_name
from cadence.eval.provenance import revision, sha256
from cadence.eval.verified import RUBRIC, RUBRIC_VERSION, runtime
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl

VARIANTS = ("combined", "core", "full_context", "no_history")
SYSTEMS = ("agent", "quality", "balanced", "verified")
RULES = {"intent_f1_margin": .03, "max_p95_ms": 7500, "token_ratio_target": 1.25,
         "human_reply_messages": 50, "zero_required_route_failures": True,
         "zero_flagged_automatic": True, "positive_paired_useful_ci": True}


def utcnow():
    return datetime.now(UTC).isoformat()


class InvocationClient:
    """Observe all calls including exceptions; budget scopes span retries and stages."""

    def __init__(self, client):
        self.client = client
        self.calls = []

    @property
    def model(self):
        return self.client.model

    def request_budget(self, **kwargs):
        return self.client.request_budget(**kwargs) if hasattr(self.client, "request_budget") else nullcontext()

    def budget_status(self):
        return self.client.budget_status() if hasattr(self.client, "budget_status") else None

    def generate_json(self, *args, **kwargs):
        started = time.monotonic()
        try:
            answer, meta = self.client.generate_json(*args, **kwargs)
        except Exception as error:
            self.calls.append({"status": "error", "error_type": type(error).__name__,
                               "elapsed_ms": (time.monotonic() - started) * 1000})
            raise
        self.calls.append({"status": "success", "cached": meta.cached, "attempts": meta.attempts,
                           "prompt_tokens": meta.prompt_tokens, "output_tokens": meta.output_tokens,
                           "elapsed_ms": (time.monotonic() - started) * 1000})
        return answer, meta


def invocation(agent, client, label, excluded, *, seconds, max_attempts):
    """Exceptions and engine fallback traces are failed requests, even with safe wording."""
    client.calls = []
    started = time.monotonic()
    budget = None
    challenge = {}
    from cadence.eval.challenge import challenge_setup
    try:
        with challenge_setup(agent, client, label.get("scenario_setup", {})) as challenge:
            with client.request_budget(seconds=seconds, max_attempts=max_attempts) as budget:
                result = agent.handle(label["text"], id=label["id"], exclude_thread_ids=excluded)
                row = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        failed = bool(row.get("trace", {}).get("execution_error")) or any(c["status"] != "success" for c in client.calls)
        row["outcome"] = "failed" if failed else "success"
    except Exception as error:
        from cadence.data.clean import clean_text
        if getattr(agent, "system_name", None) == "verified":
            from cadence.agent.verified import normalize_input
            customer = normalize_input(label["text"])
        else:
            customer = clean_text(label["text"]).text
        row = {"id": label["id"], "input_text": customer, "reply_draft": "", "evidence": [],
               "decision": None, "intent": None, "outcome": "failed", "error_type": type(error).__name__}
    row["measurement"] = {"elapsed_ms": (time.monotonic() - started) * 1000, "calls": list(client.calls),
                          "budget": budget.as_dict() if budget and hasattr(budget, "as_dict") else None}
    row["challenge"] = challenge
    return row


def sampler_module():
    path = Path(__file__).with_name("26_lock_verified_confirmation.py")
    spec = importlib.util.spec_from_file_location("verified_sample", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_human_labels(args, n):
    sampler = sampler_module()
    method = sampler.validate_challenge if args.phase == "challenge" else sampler.validate_confirmation
    return method(args.labels, args.policy, expected_n=n)


def excluded_retrieval(threads, labels):
    """Transitive conversation components plus fuzzy opener exclusions."""
    sampler = sampler_module()
    components = sampler._components(threads)
    blocked = {components[t] for r in labels for t in sampler._tokens(r) if t in components}
    excluded = {t["thread_id"] for t in threads if components[str(t["thread_id"])] in blocked}
    texts = [t["customer_text"].casefold() for t in threads]
    for label in labels:
        excluded.update(threads[i]["thread_id"] for _, _, i in process.extract(
            label["text"].casefold(), texts, scorer=fuzz.ratio, score_cutoff=85, limit=None))
    # Fuzzy exclusions may add new components: close the graph again.
    blocked.update(components[str(t)] for t in excluded)
    excluded.update(t["thread_id"] for t in threads if components[str(t["thread_id"])] in blocked)
    return excluded


def freeze(args, labels):
    from cadence.eval.archive import archive_inputs, resolve_input, snapshot_dependencies

    args.out.mkdir(parents=True, exist_ok=True)
    if not (args.out / "manifest.json").exists() and any((args.out / name).exists() for name in (
        "predictions.jsonl", "calls.sqlite", "status.json", "runtime.json", "EXECUTION.json", "invocations_started.jsonl",
        "blind_packet.jsonl", "AI_REVIEW.json", "HUMAN_REVIEW.json")):
        raise ValueError("Unbound execution artifacts already exist; choose a clean experiment directory")
    rubric = args.out / "rubric.json"
    if rubric.exists() and read_json(rubric) != RUBRIC:
        raise ValueError("Frozen rubric changed")
    if not rubric.exists():
        write_json(rubric, RUBRIC)
    files = [Path(__file__), Path(__file__).with_name("26_lock_verified_confirmation.py"),
             Paths.ROOT / "analysis_tools/reproduce_verified.py", Paths.ROOT / "pyproject.toml",
             Paths.ROOT / "docs/BRAND_VOICE.md",
             args.labels, args.policy, Paths.THREADS, rubric]
    if args.phase in ("confirmation", "challenge"):
        files += [args.labels.parent / f for f in ("examples.jsonl", "SAMPLE.lock.json", "LABEL_REVIEW.json")]
        files += [args.labels.parent / f for f in read_json(args.labels.parent / "SAMPLE.lock.json")["files"]]
        files.append(args.labels.parent / "submitted_human_labels.csv")
    manifest = args.out / "manifest.json"
    # Resume must validate active dependencies as well as archived bytes: execution
    # imports live modules, so archived identity alone cannot authorize a changed run.
    if manifest.exists():
        watched = {*Paths.ROOT.glob("src/cadence/**/*.py"),
                   *(p for p in Paths.CONFIG.rglob("*") if p.is_file()), *files}
        inputs = {p.resolve().relative_to(Paths.ROOT).as_posix(): sha256(p) for p in watched}
        for name, digest in read_json(manifest)["frozen"]["inputs"].items():
            resolve_input(args.out, name, digest, root=Paths.ROOT)
    else:
        # Includes all source and recursive config, including current knowledge.
        inputs = snapshot_dependencies(args.out, files, root=Paths.ROOT)
    ids = sorted(r["id"] for r in labels)
    import random
    random.Random(args.seed).shuffle(ids)
    def relative(p):
        return p.resolve().relative_to(Paths.ROOT).as_posix()
    frozen = {"inputs": inputs, "labels": relative(args.labels), "policy": relative(args.policy),
              "rubric": relative(rubric), "rubric_version": RUBRIC_VERSION, "policy_version": args.policy_version,
              "phase": args.phase, "variant": args.variant, "n": len(labels), "systems": args.systems,
              "message_ids": [r["id"] for r in labels], "limit": args.limit,
              "model": model_name("agent"), "seed": args.seed, "acceptance": RULES,
              "source_as_of": read_json(manifest)["frozen"]["source_as_of"] if manifest.exists() else datetime.now(UTC).date().isoformat(),
              "human_reply_ids": ids[:min(RULES["human_reply_messages"], len(ids))],
              "resources": {"invocation_seconds": args.deadline, "max_network_attempts": args.max_attempts,
                            "planned_generation_calls": len(labels) * sum({"agent": 1, "quality": 3, "balanced": 2, "verified": 2}[s] for s in args.systems),
                            "retries_and_review_calls_additional": True},
              "retrieval": {"exclude_transitive_components": True, "fuzzy_cutoff": 85},
              "run_mode": "live" if args.live_free_tier else "cache_only"}
    if manifest.exists():
        if read_json(manifest)["frozen"] != frozen:
            raise ValueError("Execution/config/data changed; use a new experiment")
    else:
        write_json(manifest, {"frozen": frozen, "revision": revision(Paths.ROOT), "frozen_at": utcnow()})
    archive_inputs(args.out, inputs, root=Paths.ROOT)
    return frozen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--policy-version", choices=("v0", "v2"), required=True)
    parser.add_argument("--phase", choices=("development", "calibration", "confirmation", "challenge"), required=True)
    parser.add_argument("--variant", choices=VARIANTS, default="combined")
    parser.add_argument("--systems", nargs="+", choices=SYSTEMS, default=list(SYSTEMS))
    parser.add_argument("--limit", type=int, help="Development-only first N labels; exact IDs are frozen")
    parser.add_argument("--seed", type=int, default=2026091806)
    parser.add_argument("--deadline", type=float, default=45)
    parser.add_argument("--max-attempts", type=int, default=6)
    parser.add_argument("--live-free-tier", action="store_true")
    parser.add_argument("--freeze-only", action="store_true")
    args = parser.parse_args()
    if args.deadline <= 0 or args.max_attempts <= 0:
        raise ValueError("Positive bounded resource limits required")
    if len(set(args.systems)) != len(args.systems):
        raise ValueError("Duplicate comparison system")
    if args.limit is not None and (args.limit <= 0 or args.phase in ("confirmation", "challenge")):
        raise ValueError("Positive --limit is permitted only in development/calibration")
    if args.phase in ("confirmation", "challenge") and args.systems != list(SYSTEMS):
        raise ValueError("Final comparisons require all four frozen arms in standard order")
    labels = read_jsonl(args.labels)
    if not labels or len({r["id"] for r in labels}) != len(labels) or any(not r.get("gold") for r in labels):
        raise ValueError("Complete unique labels required")
    if any(type(r["gold"].get("should_escalate")) is not bool for r in labels):
        raise ValueError("Explicit boolean routing labels required")
    if args.limit is not None:
        labels = labels[:args.limit]
    from cadence.eval.challenge import validate_setup
    for row in labels:
        setup = validate_setup(row.get("scenario_setup", {}), args.systems)
        if setup and args.phase != "challenge":
            raise ValueError("Operational injections belong in the separately reported challenge phase")
    if args.phase in ("confirmation", "challenge"):
        if args.policy_version != "v2":
            raise ValueError("New confirmation uses the frozen prospective v2 policy")
        validate_human_labels(args, 200 if args.phase == "confirmation" else 80)
    expected_policy = Paths.CONFIG / ("policy_v2.json" if args.policy_version == "v2" else "escalation.yaml")
    if sha256(args.policy) != sha256(expected_policy):
        raise ValueError("Labeling policy must match the named executable policy version")
    frozen = freeze(args, labels)
    if args.freeze_only:
        print("Execution dependencies, rubric, limits and review subset frozen; no model calls.")
        return
    if (args.out / "EXECUTION.json").exists():
        for name, digest in read_json(args.out / "EXECUTION.json")["artifacts"].items():
            if sha256(args.out / name) != digest:
                raise ValueError("Completed execution artifact changed: " + name)
        print("This run is already sealed; use reproduce_verified.py for offline review and analysis.")
        return
    # Imports follow gating: no client or retriever is initialized before human label checks.
    from cadence.agent.balanced import BalancedAgent
    from cadence.agent.pipeline import SupportAgent
    from cadence.agent.quality import QualityAgent
    from cadence.agent.verified import VerifiedAgent
    from cadence.llm.gemini import GeminiClient
    from cadence.retrieval.index import Retriever

    label_execution_marker = None
    if args.phase in ("confirmation", "challenge"):
        marker = args.labels.parent / "INFERENCE_STARTED.json"
        if not marker.exists():
            write_json(marker, {"started_at": utcnow(), "labels_sha256": sha256(args.labels),
                                "manifest_sha256": sha256(args.out / "manifest.json")})
        validate_human_labels(args, frozen["n"])
        label_execution_marker = read_json(marker)
        if label_execution_marker.get("manifest_sha256") != sha256(args.out / "manifest.json"):
            raise ValueError("Human-labeled confirmation sample was already used by a different run")
    os.environ["CADENCE_CACHE_ONLY"] = "0" if args.live_free_tier else "1"
    threads = read_jsonl(Paths.THREADS)
    excluded = excluded_retrieval(threads, labels)
    retriever = Retriever.build([t for t in threads if t["thread_id"] not in excluded])
    base = GeminiClient(frozen["model"], cache_path=args.out / "calls.sqlite", deadline_s=args.deadline)
    client = InvocationClient(base)
    agents = {"agent": SupportAgent(client, retriever, threshold=.9),
              "quality": QualityAgent(client, retriever, threshold=.9, system_name="quality"),
              "balanced": BalancedAgent(client, retriever, threshold=.9, system_name="balanced"),
              "verified": VerifiedAgent(client, retriever, system_name="verified", variant=args.variant,
                                        as_of=date.fromisoformat(frozen["source_as_of"]),
                                        deadline_s=args.deadline, max_attempts=args.max_attempts)}
    agents = {s: agents[s] for s in args.systems}
    path = args.out / "predictions.jsonl"
    rows = read_jsonl(path)
    done = {(r["id"], r["system"]) for r in rows}
    expected = {(r["id"], s) for r in labels for s in args.systems}
    if len(rows) != len(done) or not done <= expected:
        raise ValueError("Unexpected/duplicate completed invocations")
    starts = read_jsonl(args.out / "invocations_started.jsonl")
    started_keys = {(r["id"], r["system"]) for r in starts}
    if len(started_keys) != len(starts) or not started_keys <= expected or not done <= started_keys:
        base.close()
        raise ValueError("Invocation ledger and saved predictions are not an exact run-bound history")
    from cadence.agent.verified import normalize_input
    from cadence.data.clean import clean_text
    label_text = {r["id"]: clean_text(r["text"]).text for r in labels}
    verified_text = {r["id"]: normalize_input(r["text"]) for r in labels}
    if any(row.get("input_text") != (verified_text if row["system"] == "verified" else label_text)[row["id"]] for row in rows):
        base.close()
        raise ValueError("Saved prediction customer text differs from locked labels")
    abandoned = started_keys - done
    if abandoned:
        base.close()
        raise ValueError("Interrupted invocations have unknown completion/usage; preserve this run and create a new run. Do not silently omit failed attempts.")
    try:
        for i, label in enumerate(labels):
            order = args.systems.copy()
            order = order[i % len(order):] + order[:i % len(order)]
            for system in order:
                if (label["id"], system) in done:
                    continue
                write_jsonl(args.out / "invocations_started.jsonl", [{"id": label["id"], "system": system, "started_at": utcnow()}], append=True)
                row = invocation(agents[system], client, label, excluded, seconds=args.deadline, max_attempts=args.max_attempts)
                row["system"] = system
                row["completed_at"] = utcnow()
                write_jsonl(path, [row], append=True)
                rows.append(row)
                write_json(args.out / "status.json", {"status": "partial", "completed": len(rows), "expected": len(expected)})
                print(f"saved {label['id']} {system} {row['outcome']}", flush=True)
    finally:
        base.close()
    write_json(args.out / "status.json", {"status": "complete", "completed": len(rows), "expected": len(expected)})
    write_json(args.out / "runtime.json", {s: runtime([r for r in rows if r["system"] == s]) for s in args.systems})
    artifacts = ("manifest.json", "predictions.jsonl", "status.json", "runtime.json", "calls.sqlite", "invocations_started.jsonl")
    write_json(args.out / "EXECUTION.json", {"artifacts": {f: sha256(args.out / f) for f in artifacts},
                                           "label_inference_started": label_execution_marker,
                                           "excluded_retrieval_threads": len(excluded), "promotion": False})
    print("All invocation outcomes recorded. Prepare blinded review before computing useful coverage.")


if __name__ == "__main__":
    main()
