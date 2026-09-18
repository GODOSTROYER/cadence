"""Offline, development-only retrieval diagnosis; no model calls or automatic ratings.

Freeze a seeded selection BEFORE opening experiment results, then prepare a blind
review from a completed development run. Only this tool's new output directory is
written. Historical replies are examples, never evidence of current authority or
observed resolution. The lexical re-ranker is an explicit heuristic, not a semantic
retriever. Give reviewers only blind_packet.jsonl, rubric.json and a worksheet;
keep the selection lock, mapping and diagnostics private until ratings are final.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from cadence.agent.request_frame import RequestFrame, validate_frame
from cadence.agent.verified import normalize_input
from cadence.config import Paths
from cadence.eval.provenance import sha256 as logical_sha256
from cadence.retrieval.bm25 import tokenize
from cadence.retrieval.index import CANDIDATE_POOL, Retriever
from cadence.utils.io import read_json, read_jsonl

VERSION = "verified-retrieval-review-v2"
ARMS = ("raw_text", "request_frame", "request_frame_token_rerank")
LOCK_NAME = "SELECTION.lock.json"
RUBRIC = {
    "version": VERSION,
    "issue_relevance": "0=unrelated, 1=partly relevant, 2=same issue; blank means unrated",
    "useful_diagnostic_pattern": "yes/no/uncertain; a useful question or diagnostic pattern, not proof of success",
    "supports_proposed_action": "yes/no/uncertain; judge the exact proposed reply against the current request",
    "current_authority": "yes/unsupported/uncertain; default is unsupported for historical material alone",
    "current_authority_default": "unsupported",
    "positive_authority_evidence": (
        "A yes requires an official current source URL, checked_at, an actual local source snapshot, "
        "its SHA256, a verbatim source excerpt and a rationale connecting it to the proposed action. "
        "The validator checks provenance, not whether the source's claims are true."
    ),
    "missing_context": "Mark context_sufficient=no/uncertain if the available turns cannot support a judgment.",
    "unavailable": "For an unavailable candidate use not_applicable for relevance/pattern/support/context; keep authority unsupported.",
    "historical_limit": "A later brand reply is not an observed resolution. No outcome is inferred from position.",
    "blinding": "No query arm, rank, score, label ID, primary gold, system identity or model frame is shown.",
    "independence": (
        "Independent human or AI reviewers supply judgments; this tool creates blank worksheets and no quality scores. "
        "AI review must be explicitly requested and labeled ai; AI ratings never count as human review."
    ),
}
RATING_FIELDS = (
    "issue_relevance", "useful_diagnostic_pattern", "supports_proposed_action", "current_authority",
    "context_sufficient", "rationale", "reviewer_id", "reviewer_type", "rated_at",
    "current_source_url", "current_checked_at", "current_evidence_path", "current_evidence_sha256",
    "current_source_excerpt", "current_authority_rationale",
)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def raw_sha256(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_new(path: Path, value: object, *, jsonl: bool = False) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        if jsonl:
            for row in value:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _development_labels(path: Path) -> list[dict]:
    rows = read_jsonl(path)
    if not rows or any(row.get("split") != "development" for row in rows):
        raise ValueError("Every label must explicitly have split=development; mixed partitions are refused")
    ids = [row.get("id") for row in rows]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("Development IDs must be nonempty unique strings")
    if any(not isinstance(row.get("text"), str) or not row["text"].strip() for row in rows):
        raise ValueError("Every development label needs text")
    return rows


def excluded_retrieval(threads: list[dict], labels: list[dict]) -> set[str]:
    """Use the experiment's transitive IDs + casefold fuzzy ratio >=85 closure.

    All development labels are passed, including those outside the review subset.
    Loading this helper reads source code only, never confirmation data.
    """
    path = Paths.ROOT / "scripts/25_verified_experiment.py"
    spec = importlib.util.spec_from_file_location("retrieval_review_exclusion", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {str(value) for value in module.excluded_retrieval(threads, labels)}


def _checked_threads(path: Path) -> list[dict]:
    rows = read_jsonl(path)
    ids = [row.get("thread_id") for row in rows]
    if not rows or any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("Corpus thread IDs must be nonempty unique strings")
    if any(not isinstance(row.get("customer_text"), str) for row in rows):
        raise ValueError("Corpus customer_text must be a string")
    return rows


def _require_final_reservation(paths: set[Path]) -> None:
    final_sample = (Paths.DATA / "verified_confirmation/examples.jsonl").resolve()
    if final_sample.exists() and final_sample not in paths:
        raise ValueError("The locked confirmation sample must be supplied as --reserved-sample")


def _reserved_sources(paths: list[Path]) -> tuple[list[dict], list[dict]]:
    """Read reserved text only for local overlap exclusion; return no gold or replies.

    Callers must serialize only the metadata, never the exclusion-only rows.
    Error messages intentionally contain no reserved row values.
    """
    resolved = [Path(path).resolve() for path in paths]
    if len(resolved) != len(set(resolved)) or any(not path.is_file() for path in resolved):
        raise ValueError("Reserved samples must be unique existing files")
    _require_final_reservation(set(resolved))
    metadata, exclusions = [], []
    for path in sorted(resolved, key=str):
        before = raw_sha256(path)
        rows = read_jsonl(path)
        if not rows or any(not isinstance(row, dict) or not isinstance(row.get("text"), str)
                           or not row["text"].strip() for row in rows):
            raise ValueError("Reserved samples require nonempty customer text for local duplicate exclusion")
        for row in rows:
            item = {key: row[key] for key in ("text", "thread_id", "opener_tweet_id") if key in row}
            turns = row.get("turns", [])
            if not isinstance(turns, list) or any(not isinstance(turn, dict) for turn in turns):
                raise ValueError("Reserved sample conversation identities are malformed")
            item["turns"] = [{"tweet_id": turn["tweet_id"]} for turn in turns if "tweet_id" in turn]
            exclusions.append(item)
        if raw_sha256(path) != before:
            raise ValueError("Reserved sample changed during local exclusion loading")
        metadata.append({"path": str(path), "raw_sha256": before,
                         "logical_sha256": logical_sha256(path), "n": len(rows)})
    return metadata, exclusions


def _run_reservation_binding(frozen: dict, payload: dict) -> dict:
    """The diagnostic must protect every reserved input used by the source run."""
    locked = {Path(source["path"]).resolve(): source for source in payload["reserved_samples"]}
    names = frozen.get("reserved_samples", [])
    if not isinstance(names, list) or any(not isinstance(name, str) or not name for name in names):
        raise ValueError("Development run reserved sample declaration is malformed")
    paths = [(Paths.ROOT / name).resolve() for name in names]
    if len(paths) != len(set(paths)):
        raise ValueError("Development run has duplicate reserved sample paths")
    _require_final_reservation(set(paths))
    for name, path in zip(names, paths, strict=True):
        if path not in locked:
            raise ValueError("Development run reservation is missing from diagnostic lock; freeze a protected superset")
        if frozen.get("inputs", {}).get(name) != locked[path]["logical_sha256"]:
            raise ValueError("Development run reserved sample hash differs from the diagnostic lock")
    extra = sorted(str(path) for path in locked.keys() - set(paths))
    return {"comparison": "diagnostic_superset" if extra else "exact",
            "run_reserved_samples": sorted(str(path) for path in paths),
            "diagnostic_only_reserved_samples": extra,
            "limitation": "Extra diagnostic exclusions do not establish that the source run avoided those extra samples."
                          if extra else "Identical reserved inputs protected in source run and diagnostic."}


def _dependencies() -> dict[str, str]:
    files = [Path(__file__), Paths.ROOT / "scripts/25_verified_experiment.py",
             Paths.ROOT / "scripts/26_lock_verified_confirmation.py",
             *[Paths.ROOT / name for name in (
                 "src/cadence/retrieval/index.py", "src/cadence/retrieval/bm25.py",
                 "src/cadence/agent/request_frame.py", "src/cadence/agent/integrity.py",
                 "src/cadence/agent/verified.py", "src/cadence/data/clean.py",
                 "src/cadence/utils/io.py", "src/cadence/utils/text.py", "config/policy_v2.json")]]
    return {str(path.resolve()): raw_sha256(path) for path in files}


def freeze(labels: Path, threads: Path, out: Path, *, sample_size: int = 20,
           seed: int = 2026091806, k: int = 3, reserved_samples: list[Path] | None = None) -> dict:
    """Lock selection, exact input bytes and actual exclusions without reading results."""
    if sample_size < 1 or not 1 <= k <= CANDIDATE_POOL:
        raise ValueError("sample_size must be positive; k must be between 1 and the retriever candidate pool")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Refusing to replace an existing selection or output; use a new empty directory")
    reserved, reserved_rows = _reserved_sources(reserved_samples or [])
    rows = _development_labels(labels)
    corpus = _checked_threads(threads)
    if sample_size > len(rows):
        raise ValueError("sample_size exceeds development population; choose it explicitly")
    ids = sorted(row["id"] for row in rows)
    random.Random(seed).shuffle(ids)
    excluded = sorted(excluded_retrieval(corpus, [*rows, *reserved_rows]))
    payload = {
        "version": VERSION, "phase": "development", "seed": seed, "sample_size": sample_size,
        "selected_ids": ids[:sample_size], "label_count": len(rows), "k": k,
        "labels": {"path": str(labels.resolve()), "raw_sha256": raw_sha256(labels),
                   "logical_sha256": logical_sha256(labels)},
        "corpus": {"path": str(threads.resolve()), "raw_sha256": raw_sha256(threads),
                   "logical_sha256": logical_sha256(threads), "n": len(corpus)},
        "reserved_samples": reserved,
        "dependencies": _dependencies(), "rubric_sha256": digest(RUBRIC),
        "exclusions": {"all_development_labels": True, "all_reserved_samples": True,
                       "reserved_use": "Local overlap exclusion only; reserved text/gold never enter review artifacts",
                       "transitive_components": True,
                       "fuzzy_scorer": "rapidfuzz.fuzz.ratio(casefold)", "fuzzy_cutoff_inclusive": 85,
                       "component_closure_after_fuzzy": True, "thread_ids": excluded,
                       "thread_ids_sha256": digest(excluded)},
        "arms": list(ARMS), "include_reply_text": True, "index_excluded_corpus": False,
        "rerank": {"candidate_k": CANDIDATE_POOL, "issue_weight": 0.5, "slot_weight": 0.5,
                   "formula": "existing_score * (1 + .5*issue_token_recall + .5*known_fact_token_recall)",
                   "target_text": "historical customer opener only", "semantic_claim": False},
        "reply_selection": "first brand reply and last brand reply iff at least two; no outcome inference",
        "absent_later_reply": "empty candidate and explicit unavailable status; never invent a substitute",
        "current_authority_default": "unsupported", "authority_max_age_days": 30,
    }
    record = {"frozen_at": datetime.now(UTC).isoformat(), "payload": payload, "payload_sha256": digest(payload)}
    out.mkdir(parents=True, exist_ok=True)
    _write_new(out / LOCK_NAME, record)
    return record


def load_lock(out: Path) -> tuple[dict, list[dict], list[dict]]:
    record = read_json(out / LOCK_NAME)
    payload = record["payload"]
    if record.get("payload_sha256") != digest(payload) or payload.get("version") != VERSION:
        raise ValueError("Selection lock hash/version changed")
    if payload.get("phase") != "development" or payload.get("rubric_sha256") != digest(RUBRIC):
        raise ValueError("Development phase or rubric changed")
    for source in (payload["labels"], payload["corpus"], *payload["reserved_samples"]):
        if raw_sha256(Path(source["path"])) != source["raw_sha256"]:
            raise ValueError("Frozen input bytes changed: " + source["path"])
    if payload["dependencies"] != _dependencies():
        raise ValueError("Diagnostic implementation changed after selection lock")
    labels = _development_labels(Path(payload["labels"]["path"]))
    threads = _checked_threads(Path(payload["corpus"]["path"]))
    reserved, reserved_rows = _reserved_sources([Path(source["path"]) for source in payload["reserved_samples"]])
    if reserved != payload["reserved_samples"]:
        raise ValueError("Frozen reserved sample metadata changed")
    excluded = sorted(excluded_retrieval(threads, [*labels, *reserved_rows]))
    if excluded != payload["exclusions"]["thread_ids"] or digest(excluded) != payload["exclusions"]["thread_ids_sha256"]:
        raise ValueError("Frozen exclusion set changed")
    ids = sorted(row["id"] for row in labels)
    random.Random(payload["seed"]).shuffle(ids)
    if ids[:payload["sample_size"]] != payload["selected_ids"]:
        raise ValueError("Frozen seeded selection changed")
    return record, labels, threads


def frame_query(frame: RequestFrame) -> str:
    """Only issues, explicitly known slot facts and requested outcome enter this query."""
    return " ".join([*(issue.replace("_", " ") for issue in frame.issues),
                     *(f"{fact.slot.replace('_', ' ')} {fact.value}" for fact in frame.facts),
                     frame.requested_outcome]).strip()


def token_rerank(hits: list, frame: RequestFrame) -> list[tuple[object, dict]]:
    """Transparent lexical overlap over the same frame-query candidate pool."""
    issue_tokens = set(tokenize(" ".join(issue.replace("_", " ") for issue in frame.issues)))
    fact_tokens = set(tokenize(" ".join(fact.value for fact in frame.facts)))
    ranked = []
    for index, hit in enumerate(hits):
        words = set(tokenize(hit.thread["customer_text"]))
        issue_recall = len(words & issue_tokens) / len(issue_tokens) if issue_tokens else 0.0
        fact_recall = len(words & fact_tokens) / len(fact_tokens) if fact_tokens else 0.0
        adjusted = hit.score * (1 + .5 * issue_recall + .5 * fact_recall)
        ranked.append((hit, {"existing_score": hit.score, "issue_token_recall": issue_recall,
                             "known_fact_token_recall": fact_recall, "heuristic_score": adjusted,
                             "original_candidate_rank": index + 1}))
    return sorted(ranked, key=lambda item: (-item[1]["heuristic_score"], item[1]["original_candidate_rank"]))


def reply_views(thread: dict) -> list[dict]:
    """Prespecified first/last selection with only observed preceding conversation turns."""
    replies = thread.get("brand_replies") or []
    turns = thread.get("turns") or []
    views = []
    for kind, index in (("first_brand_reply", 0), ("last_later_brand_reply", len(replies) - 1)):
        available = bool(replies) and (kind == "first_brand_reply" or len(replies) >= 2)
        reply = replies[index] if available else {}
        text = str(reply.get("text") or "")
        available = available and bool(text.strip())
        reply_id = reply.get("tweet_id")
        matches = [i for i, turn in enumerate(turns)
                   if reply_id is not None and str(turn.get("tweet_id")) == str(reply_id)]
        context = []
        if available and len(matches) == 1:
            context = [{"role": str(turn.get("role", "unknown")), "text": str(turn.get("text") or "")}
                       for turn in turns[:matches[0]]]
        views.append({
            "reply_kind": kind, "reply_index": index if available else None,
            "reply_tweet_id": reply_id if available else None, "text": text if available else "",
            "availability": "available" if available else "unavailable",
            "context_status": "available_dataset_turns_only_completeness_unverified" if context else "unavailable",
            "preceding_turns": context,
            "context_note": "Only recorded preceding turns are shown; completeness is not established."
                            if context else "Intermediate context unavailable in the dataset for this candidate.",
            "created_at": reply.get("created_at", "") if available else "",
            "source_reply_sha256": digest(reply) if available else None,
            "resolved_links": reply.get("resolved_links") or [] if available else [],
        })
    return views


def _development_run(run: Path, payload: dict) -> tuple[list[dict], dict]:
    # Read the small phase declaration first; never open non-development predictions.
    manifest = read_json(run / "manifest.json")
    frozen = manifest.get("frozen", {})
    if frozen.get("phase") != "development":
        raise ValueError("Only explicitly development experiment results may be opened")
    execution = read_json(run / "EXECUTION.json")
    artifacts = execution.get("artifacts", {})
    if logical_sha256(run / "manifest.json") != artifacts.get("manifest.json"):
        raise ValueError("Development manifest must match its execution seal")
    if frozen.get("inputs", {}).get(frozen.get("labels")) != payload["labels"]["logical_sha256"]:
        raise ValueError("Development run is not bound to the locked label input")
    corpus_path = Path(payload["corpus"]["path"])
    corpus_key = (corpus_path.relative_to(Paths.ROOT).as_posix()
                  if corpus_path.is_relative_to(Paths.ROOT) else str(corpus_path))
    if frozen.get("inputs", {}).get(corpus_key) != payload["corpus"]["logical_sha256"]:
        raise ValueError("Development run is not bound to the locked retrieval corpus")
    reserved_binding = _run_reservation_binding(frozen, payload)
    if not set(payload["selected_ids"]) <= set(frozen.get("message_ids", [])):
        raise ValueError("Development run omits frozen review IDs")
    ids, systems = frozen.get("message_ids", []), frozen.get("systems", [])
    if not ids or len(ids) != len(set(ids)) or len(ids) != frozen.get("n") or "verified" not in systems:
        raise ValueError("Development manifest needs the exact invocation population")
    if logical_sha256(run / "status.json") != artifacts.get("status.json"):
        raise ValueError("Development status must match its execution seal")
    count = len(ids) * len(systems)
    if read_json(run / "status.json") != {"status": "complete", "completed": count, "expected": count}:
        raise ValueError("Development run is incomplete")
    expected = artifacts.get("predictions.jsonl")
    if not expected or logical_sha256(run / "predictions.jsonl") != expected:
        raise ValueError("Development predictions must be complete and sealed with their exact hash")
    all_rows = read_jsonl(run / "predictions.jsonl")
    keys = [(row.get("id"), row.get("system")) for row in all_rows]
    if len(keys) != len(set(keys)) or set(keys) != {(i, system) for i in ids for system in systems}:
        raise ValueError("Missing or duplicate invocation rows; do not replace the frozen selection")
    rows = [row for row in all_rows if row.get("system") == "verified"]
    provenance = {"run": str(run.resolve()), "manifest_raw_sha256": raw_sha256(run / "manifest.json"),
                  "execution_raw_sha256": raw_sha256(run / "EXECUTION.json"),
                  "predictions_raw_sha256": raw_sha256(run / "predictions.jsonl"),
                  "reserved_binding": reserved_binding}
    return rows, provenance


def prepare(out: Path, run: Path) -> dict:
    """Generate immutable review artifacts; input runs, labels, corpus and index stay untouched."""
    record, labels, threads = load_lock(out)
    payload = record["payload"]
    names = ("blind_packet.jsonl", "private_mapping.jsonl", "private_diagnostics.json", "rubric.json",
             "review_worksheet.jsonl", "review_worksheet.csv", "PACKET.lock.json")
    if any((out / name).exists() for name in names):
        raise ValueError("Review artifacts already exist; refusing to overwrite ratings or selection")
    rows, provenance = _development_run(run, payload)
    label_by_id = {row["id"]: row for row in labels}
    row_by_id = {row["id"]: row for row in rows}
    exclusions = set(payload["exclusions"]["thread_ids"])
    eligible = [thread for thread in threads if thread["thread_id"] not in exclusions]
    if not eligible:
        raise ValueError("No eligible historical corpus remains after frozen exclusions")
    retriever = Retriever.build(eligible, include_reply=payload["include_reply_text"])
    selection_hash = raw_sha256(out / LOCK_NAME)
    run_id = digest({"selection": selection_hash, "source": provenance})
    packet, mapping, diagnostics = [], [], []
    for identity in payload["selected_ids"]:
        label, row = label_by_id[identity], row_by_id[identity]
        raw = label["text"]
        if row.get("input_text") != normalize_input(raw):
            raise ValueError("Prediction customer text differs from the locked label: " + identity)
        frame = None
        frame_error = ""
        try:
            frame = validate_frame(RequestFrame.model_validate(row.get("trace", {}).get("request_frame", {})),
                                   row.get("input_text") or raw)
        except ValueError as exc:
            frame_error = type(exc).__name__ + ": " + str(exc)
        query = frame_query(frame) if frame else ""
        raw_hits = retriever.search(raw, k=payload["k"], exclude_thread_ids=exclusions)
        frame_hits = retriever.search(query, k=CANDIDATE_POOL, exclude_thread_ids=exclusions) if frame else []
        reranked = token_rerank(frame_hits, frame) if frame else []
        arms = {
            "raw_text": [(hit, {"existing_score": hit.score}) for hit in raw_hits],
            "request_frame": [(hit, {"existing_score": hit.score}) for hit in frame_hits[:payload["k"]]],
            "request_frame_token_rerank": reranked[:payload["k"]],
        }
        diagnostics.append({"id": identity, "raw_query": raw, "frame_query": query,
                            "frame_error": frame_error, "prediction_sha256": digest(row),
                            "arms": {arm: {"status": "frame_unavailable" if arm != "raw_text" and frame is None
                                          else "available" if hits else "no_hits",
                                          "thread_ids": [hit.thread_id for hit, _ in hits]}
                                     for arm, hits in arms.items()}})
        for arm, hits in arms.items():
            for rank, (hit, scores) in enumerate(hits, 1):
                if hit.thread_id in exclusions:
                    raise ValueError("Retriever returned an excluded conversation")
                for view in reply_views(hit.thread):
                    alias = digest([run_id, identity, arm, rank, view["reply_kind"]])[:24]
                    candidate = {
                        "review_id": alias, "run_id": run_id, "rubric_version": VERSION,
                        "selection_lock_sha256": selection_hash, "customer_text": raw,
                        "proposed_action": row.get("reply_draft", ""),
                        "historical_customer_opener": hit.thread["customer_text"],
                        "historical_reply": view["text"], "availability": view["availability"],
                        "preceding_turns": view["preceding_turns"], "context_status": view["context_status"],
                        "context_note": view["context_note"], "historical_date": view["created_at"],
                        "historical_links": view["resolved_links"],
                        "authority_default": "unsupported", "outcome": "not_assessed",
                        "evidence_scope": "Historical example only; no resolution or current authority inferred.",
                    }
                    candidate["item_sha256"] = digest(candidate)
                    packet.append(candidate)
                    mapping.append({"review_id": alias, "item_sha256": candidate["item_sha256"],
                                    "id": identity, "arm": arm, "rank": rank, "query": raw if arm == "raw_text" else query,
                                    "thread_id": hit.thread_id, "thread_sha256": digest(hit.thread),
                                    "reply_kind": view["reply_kind"], "reply_index": view["reply_index"],
                                    "reply_tweet_id": view["reply_tweet_id"],
                                    "source_reply_sha256": view["source_reply_sha256"],
                                    "prediction_sha256": digest(row), "scores": scores})
    random.Random(payload["seed"] ^ 0xB11D).shuffle(packet)
    worksheet = [{**{key: item[key] for key in ("review_id", "run_id", "rubric_version", "item_sha256",
                                              "selection_lock_sha256")},
                  "authority_default": "unsupported", **dict.fromkeys(RATING_FIELDS, "")} for item in packet]
    artifacts = {"blind_packet.jsonl": packet, "private_mapping.jsonl": mapping,
                 "private_diagnostics.json": {"source": provenance, "cases": diagnostics,
                                              "limitations": ["Development-only, no independent quality estimates.",
                                                  "Lexical reranking is heuristic; no semantic improvement claim.",
                                                  "No observed resolution inferred from historical reply position.",
                                                  "Missing/invalid frames and missing later replies remain explicit."]},
                 "rubric.json": RUBRIC, "review_worksheet.jsonl": worksheet}
    for name, value in artifacts.items():
        _write_new(out / name, value, jsonl=name.endswith(".jsonl"))
    buffer = io.StringIO(newline="")
    fields = ["review_id", "run_id", "rubric_version", "item_sha256", "selection_lock_sha256",
              "authority_default", *RATING_FIELDS]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(worksheet)
    with (out / "review_worksheet.csv").open("x", encoding="utf-8", newline="") as stream:
        stream.write(buffer.getvalue())
    seal = {"run_id": run_id, "selection_lock_sha256": selection_hash, "source": provenance,
            "prepared_at": datetime.now(UTC).isoformat(),
            "n_selected": len(payload["selected_ids"]), "n_review_items": len(packet), "ratings_supplied": False,
            "artifacts": {name: raw_sha256(out / name) for name in names if name != "PACKET.lock.json"}}
    _write_new(out / "PACKET.lock.json", seal)
    return seal


def validate_ratings(out: Path, submission: Path, *, reviewer_type: str = "human") -> dict:
    """Check explicitly typed external judgments and source snapshots; never synthesize a rating."""
    if reviewer_type not in {"human", "ai"}:
        raise ValueError("Requested reviewer_type must be human or ai")
    seal = read_json(out / "PACKET.lock.json")
    if raw_sha256(out / LOCK_NAME) != seal["selection_lock_sha256"]:
        raise ValueError("Selection lock changed")
    for name, expected in seal["artifacts"].items():
        if raw_sha256(out / name) != expected:
            raise ValueError("Sealed review artifact changed: " + name)
    if submission.suffix == ".csv":
        with submission.open(encoding="utf-8", newline="") as stream:
            ratings = list(csv.DictReader(stream))
    else:
        ratings = read_jsonl(submission)
    expected_items = {item["review_id"]: item for item in read_jsonl(out / "blind_packet.jsonl")}
    seen = set()
    payload = read_json(out / LOCK_NAME)["payload"]
    for row in ratings:
        identity = row.get("review_id")
        if identity not in expected_items or identity in seen:
            raise ValueError("Unknown or duplicate review ID")
        seen.add(identity)
        item = expected_items[identity]
        for key in ("run_id", "rubric_version", "item_sha256", "selection_lock_sha256"):
            if row.get(key) != item[key]:
                raise ValueError("Review provenance mismatch: " + key)
        reviewer_id = row.get("reviewer_id")
        if row.get("reviewer_type") != reviewer_type or not isinstance(reviewer_id, str) or not reviewer_id.strip():
            raise ValueError(f"An explicit {reviewer_type} reviewer identity matching the requested type is required")
        rated = _timestamp(row.get("rated_at", ""))
        if not _timestamp(seal["prepared_at"]) <= rated <= datetime.now(UTC):
            raise ValueError("Review timestamp must follow packet preparation and cannot be future-dated")
        unavailable = item["availability"] == "unavailable"
        relevant_values = {"not_applicable"} if unavailable else {"0", "1", "2"}
        judgment_values = {"not_applicable"} if unavailable else {"yes", "no", "uncertain"}
        if str(row.get("issue_relevance")) not in relevant_values:
            raise ValueError("Every review needs issue_relevance=0/1/2")
        for key in ("useful_diagnostic_pattern", "supports_proposed_action", "context_sufficient"):
            if row.get(key) not in judgment_values:
                raise ValueError("Missing/invalid judgment: " + key)
        rationale = row.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError("A reviewer rationale is required")
        authority = row.get("current_authority")
        if authority not in {"yes", "unsupported", "uncertain"}:
            raise ValueError("Explicit current_authority is required; historical default is unsupported")
        if unavailable and authority != "unsupported":
            raise ValueError("An absent historical reply cannot have current authority")
        if authority == "yes":
            evidence = Path(row.get("current_evidence_path", ""))
            if not evidence.is_absolute():
                evidence = submission.parent / evidence
            url = urlparse(row.get("current_source_url", ""))
            if url.scheme != "https" or not url.hostname or not (
                    url.hostname == "spotify.com" or url.hostname.endswith(".spotify.com")):
                raise ValueError("Current authority needs an official HTTPS Spotify source")
            if not evidence.is_file() or raw_sha256(evidence) != row.get("current_evidence_sha256"):
                raise ValueError("Current authority needs an actual source snapshot and matching SHA256")
            excerpt = row.get("current_source_excerpt", "")
            if not excerpt.strip() or excerpt not in evidence.read_text(encoding="utf-8"):
                raise ValueError("Current evidence excerpt must appear in the source snapshot")
            checked = _timestamp(row.get("current_checked_at", ""))
            age = (rated - checked).total_seconds() / 86400
            if not 0 <= age <= payload["authority_max_age_days"]:
                raise ValueError("Current evidence is future-dated or outside the prespecified freshness window")
            if not row.get("current_authority_rationale", "").strip():
                raise ValueError("Explain why current evidence supports this proposed action")
    if seen != set(expected_items):
        raise ValueError("Submission must cover the complete frozen packet")
    return {"valid": True, "n_ratings": len(ratings), "reviewer_type": reviewer_type,
            "human_review": reviewer_type == "human",
            "attribution": "AI development ratings; these are not human review." if reviewer_type == "ai"
                           else "Externally supplied human ratings; reviewer identity is self-attested.",
            "limitation": "Structural validation does not establish reviewer identity, source authenticity or semantic correctness."}


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError("An ISO timestamp with timezone is required") from exc
    if parsed.tzinfo is None:
        raise ValueError("An ISO timestamp with timezone is required")
    return parsed.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    frozen = sub.add_parser("freeze", help="Lock development sample before reading experiment results")
    frozen.add_argument("--labels", type=Path, required=True)
    frozen.add_argument("--threads", type=Path, default=Paths.THREADS)
    frozen.add_argument("--out", type=Path, required=True)
    frozen.add_argument("--sample-size", type=int, default=20)
    frozen.add_argument("--seed", type=int, default=2026091806)
    frozen.add_argument("--k", type=int, default=3)
    frozen.add_argument("--reserved-sample", type=Path, action="append", default=[],
                        help="Repeat for protected future samples; read only for local overlap exclusion, never shown")
    packet = sub.add_parser("prepare", help="Read only a sealed development run and make blank review materials")
    packet.add_argument("--out", type=Path, required=True)
    packet.add_argument("--run", type=Path, required=True)
    ratings = sub.add_parser("validate-ratings", help="Read-only validation of an externally completed worksheet copy")
    ratings.add_argument("--out", type=Path, required=True)
    ratings.add_argument("--submission", type=Path, required=True)
    ratings.add_argument("--reviewer-type", choices=("human", "ai"), default="human",
                         help="Require this exact reviewer type on every rating; AI ratings never count as human review")
    args = parser.parse_args()
    if args.command == "freeze":
        result = freeze(args.labels, args.threads, args.out, sample_size=args.sample_size, seed=args.seed, k=args.k,
                        reserved_samples=args.reserved_sample)
        print(f"Locked {len(result['payload']['selected_ids'])} development IDs; no experiment results opened.")
    elif args.command == "prepare":
        result = prepare(args.out, args.run)
        print(f"Prepared {result['n_review_items']} blinded items; worksheets are blank, no ratings or resolution claims.")
    else:
        print(json.dumps(validate_ratings(args.out, args.submission, reviewer_type=args.reviewer_type), indent=2))


if __name__ == "__main__":
    main()
