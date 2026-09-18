"""Lock unseen cases and import independently entered human labels before inference.

An explicit exposure registry is mandatory. Paths resolve relative to the registry:
{"version": 1, "all_inspected_sets_included": true,
 "corpus": {"path": "threads.jsonl.gz", "sha256": "..."},
 "exposures": [{"id": "golden", "path": "golden.jsonl", "sha256": "...",
                "n": 250, "state": "locked"}, ...]}

Bootstrap with prepare-calibration, add its examples to the registry, then import an
independently authored boundary suite with prepare-challenge and add it too. Finally,
prepare requires every REQUIRED_EXPOSURES entry. This tool makes no model
calls and does not supply labels. Human authorship and independence are self-attested,
not something software can independently establish.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz, process

from cadence.config import SENTIMENTS, Paths
from cadence.eval.provenance import sha256
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl

REQUIRED_EXPOSURES = {
    "original_candidates": None,
    "golden": None,
    "taxonomy_calibration": None,
    "holdout": None,
    "routing_dev": None,
    "quality_confirmation": None,
    "balanced_confirmation": 80,
    "verified_calibration": 100,
    "verified_challenge": 80,
}
PRIOR_EXPOSURES = set(REQUIRED_EXPOSURES) - {"verified_calibration", "verified_challenge"}
CHALLENGE_CATEGORIES = {
    "risk_morphology", "mixed_intent", "missing_context", "known_context", "operational_failure",
    "negation", "unsupported_action", "stale_procedure",
}
REQUIRED_CHALLENGE_CATEGORIES = {
    "risk_morphology", "mixed_intent", "missing_context", "known_context", "operational_failure",
}
CHALLENGE_FAILURES = {
    "provider_timeout", "provider_error", "malformed_extraction", "malformed_audit",
    "expired_knowledge", "missing_knowledge", "context_budget", "deadline_exhausted", "retrieval_error",
}
FIELDS = [
    "id", "text", "intent", "secondary_intent", "should_escalate",
    "escalation_reason_code", "sentiment", "notes", "annotator", "label_source",
]


def _packet_fields(partition: str) -> list[str]:
    return [*FIELDS, "scenario_setup"] if partition == "challenge" else FIELDS


def _scenario_setup(example: dict) -> str:
    return json.dumps(example.get("setup", {}), sort_keys=True, ensure_ascii=False)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Timestamp must be an ISO timestamp with timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must have timezone")
    return parsed.astimezone(UTC)


def _checked_rows(path: Path, digest: str, count: int | None = None) -> list[dict]:
    if not path.is_file() or sha256(path) != digest:
        raise ValueError(f"Missing or changed source: {path}")
    rows = read_jsonl(path)
    if not rows or (count is not None and len(rows) != count):
        raise ValueError(f"Empty or incorrect source count: {path}")
    return rows


def load_registry(path: Path, required_exposures: set[str] | None = None) -> tuple[dict, list[dict], list[dict]]:
    """Verify all named inspected partitions and exact corpus bytes before sampling."""
    registry = read_json(path)
    if registry.get("version") != 1 or registry.get("all_inspected_sets_included") is not True:
        raise ValueError("Registry v1 must explicitly attest all inspected sets are included")
    corpus = registry.get("corpus", {})
    corpus_path = path.parent / corpus.get("path", "")
    threads = _checked_rows(corpus_path, corpus.get("sha256", ""))
    seen, names = [], set()
    entries = registry.get("exposures", [])
    if not isinstance(entries, list):
        raise ValueError("Registry exposures must be a list")
    for entry in entries:
        name = entry.get("id")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Exposure IDs must be nonempty and unique")
        names.add(name)
        if entry.get("state") != "locked":
            raise ValueError(f"Exposure partition is not locked: {name}")
        count = entry.get("n")
        if type(count) is not int or count < 1:
            raise ValueError(f"Exposure count must be positive: {name}")
        minimum = REQUIRED_EXPOSURES.get(name)
        if minimum is not None and count < minimum:
            raise ValueError(f"Exposure {name} needs at least {minimum} locked cases")
        rows = _checked_rows(path.parent / entry.get("path", ""), entry.get("sha256", ""), count)
        for row in rows:
            if not isinstance(row.get("text", row.get("customer_text")), str):
                raise ValueError(f"Exposure lacks customer text: {name}")
            if not row.get("thread_id") and row.get("origin") != "synthetic":
                raise ValueError(f"Real exposure lacks thread_id: {name}")
        seen.extend(rows)
    missing = (set(REQUIRED_EXPOSURES) if required_exposures is None else required_exposures) - names
    if missing:
        raise ValueError(f"Registry omits inspected or planned partitions: {sorted(missing)}")
    return registry, threads, seen


def _tokens(row: dict) -> set[str]:
    # Include the opener identity, even if absent from turns. Tweet IDs are global.
    tokens = {str(row["thread_id"])} if row.get("thread_id") is not None else set()
    if row.get("opener_tweet_id") is not None:
        tokens.add(str(row["opener_tweet_id"]))
    thread_id = str(row.get("thread_id", ""))
    if thread_id.startswith("t_") and thread_id[2:].isdigit():
        tokens.add(thread_id[2:])
    for turn in row.get("turns", []):
        if turn.get("tweet_id") is not None:
            tokens.add(str(turn["tweet_id"]))
    return tokens


def _components(threads: list[dict]) -> dict[str, str]:
    """Union *all* rows first so an indirect A--B--C overlap also excludes C."""
    parent: dict[str, str] = {}

    def find(token: str) -> str:
        parent.setdefault(token, token)
        while parent[token] != token:
            parent[token] = parent[parent[token]]
            token = parent[token]
        return token

    for row in threads:
        tokens = sorted(_tokens(row))
        if not tokens:
            raise ValueError("Corpus row has no conversation identity")
        root = find(tokens[0])
        for token in tokens[1:]:
            parent[find(token)] = root
    return {token: find(token) for token in parent}


def select_examples(threads: list[dict], seen: list[dict], n: int, seed: int,
                    split: str = "confirmation", id_prefix: str = "v5") -> list[dict]:
    if type(n) is not int or n < 1:
        raise ValueError("n must be positive")
    ids = [str(row.get("thread_id", "")) for row in threads]
    if "" in ids or len(ids) != len(set(ids)):
        raise ValueError("Corpus thread IDs must be present and unique")
    components = _components(threads)
    blocked = {components[token] for row in seen for token in _tokens(row) if token in components}
    texts = [row.get("text", row.get("customer_text", "")).casefold() for row in seen]
    candidates = sorted(threads, key=lambda row: str(row["thread_id"]))
    random.Random(seed).shuffle(candidates)
    chosen = []
    for row in candidates:
        root = components[str(row["thread_id"])]
        text = row.get("customer_text")
        if root in blocked or row.get("language") != "en" or not row.get("brand_replies"):
            continue
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Eligible corpus row lacks customer_text")
        if process.extractOne(text.casefold(), texts, scorer=fuzz.ratio, score_cutoff=85):
            continue
        chosen.append({"id": f"{id_prefix}_{len(chosen) + 1:03d}", "thread_id": row["thread_id"],
                       "text": text, "split": split})
        blocked.add(root)
        texts.append(text.casefold())
        if len(chosen) == n:
            return chosen
    raise ValueError(f"Insufficient independent cases: found {len(chosen)}, need {n}")


def prepare(exposure_registry: Path, out: Path, policy: Path, n: int = 200,
            seed: int = 2026091805) -> dict:
    if out.exists():
        raise ValueError("Refusing to replace an existing confirmation directory")
    registry, threads, seen = load_registry(exposure_registry)
    examples = select_examples(threads, seen, n, seed)
    return _write_partition(exposure_registry, registry, out, policy, examples, "confirmation", seed)


def prepare_calibration(exposure_registry: Path, out: Path, policy: Path, n: int = 100,
                        seed: int = 2026091806) -> dict:
    """Lock a development partition first; labels may later be AI-authored with attribution."""
    if out.exists():
        raise ValueError("Refusing to replace an existing calibration directory")
    registry, threads, seen = load_registry(exposure_registry, PRIOR_EXPOSURES)
    examples = select_examples(threads, seen, n, seed, split="calibration", id_prefix="vc5")
    return _write_partition(exposure_registry, registry, out, policy, examples, "calibration", seed)


def _write_partition(exposure_registry: Path, registry: dict, out: Path, policy: Path,
                     examples: list[dict], partition: str, seed: int | None,
                     extras: dict[str, bytes] | None = None, metadata: dict | None = None) -> dict:
    if out.exists():
        raise ValueError("Refusing to replace an existing partition directory")
    policy_bytes = policy.read_bytes()
    intents_bytes = (Paths.CONFIG / "intents.yaml").read_bytes()
    reasons_bytes = (Paths.CONFIG / "escalation.yaml").read_bytes()
    # No output directory is created until inputs and sampling have succeeded.
    out.mkdir(parents=True)
    write_jsonl(out / "examples.jsonl", examples)
    (out / "policy.snapshot.yaml").write_bytes(policy_bytes)
    (out / "intents.snapshot.yaml").write_bytes(intents_bytes)
    (out / "reasons.snapshot.yaml").write_bytes(reasons_bytes)
    (out / "EXPOSURE_REGISTRY.json").write_bytes(exposure_registry.read_bytes())
    for name, content in (extras or {}).items():
        (out / name).write_bytes(content)
    with (out / "human_labels.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=_packet_fields(partition))
        writer.writeheader()
        writer.writerows({"id": row["id"], "text": row["text"],
                          **({"scenario_setup": _scenario_setup(row)} if partition == "challenge" else {})}
                         for row in examples)
    lock = {
        "version": 1, "created_at": _now(), "n": len(examples), "seed": seed, "partition": partition,
        "sampler_sha256": sha256(Path(__file__)),
        "status": ("development partition; optional human packet, AI labels require explicit attribution"
                   if partition == "calibration" else "awaiting independent human labels; inference forbidden"),
        "population": "English brand-replied corpus threads, excluding all declared inspected sets",
        "sampling": "seeded order; transitive tweet components and casefold fuzzy ratio >=85 excluded",
        "limitations": "Distinct complaint sample, not traffic-weighted; registry completeness is attested",
        "corpus_sha256": registry["corpus"]["sha256"],
        "files": {name: sha256(out / name) for name in [
            "examples.jsonl", "policy.snapshot.yaml", "intents.snapshot.yaml",
            "reasons.snapshot.yaml", "EXPOSURE_REGISTRY.json", *(extras or {})]},
        **(metadata or {}),
    }
    write_json(out / "SAMPLE.lock.json", lock)
    return lock


def prepare_challenge(exposure_registry: Path, out: Path, policy: Path, cases: Path,
                      author_id: str, author_type: str, n: int = 80,
                      attest_independent_authoring: bool = False) -> dict:
    """Import authored boundaries, never relabel a random natural sample as a challenge.

    Required JSONL fields: id, text, origin (real/synthetic), category. Real rows also
    need exact corpus thread_id/text. Optional contrast_pair_id explicitly links
    near-duplicate counterfactuals within this suite; at least one must be synthetic.
    Operational setup is {"inject": one of CHALLENGE_FAILURES}; no other payload is allowed. The
    runner must actually implement that setup before claiming the case was tested.
    """
    if out.exists():
        raise ValueError("Refusing to replace an existing challenge directory")
    if not attest_independent_authoring or not author_id.strip() or author_type not in {"human", "ai"}:
        raise ValueError("Named author/type and independent boundary authoring attestation required")
    registry, threads, seen = load_registry(exposure_registry, PRIOR_EXPOSURES | {"verified_calibration"})
    if type(n) is not int or n < len(REQUIRED_CHALLENGE_CATEGORIES):
        raise ValueError("Challenge count must cover every required boundary category")
    rows = read_jsonl(cases)
    if len(rows) != n or any(not isinstance(row.get("id"), str) or not row["id"].strip() for row in rows):
        raise ValueError("Authored challenge count/IDs are invalid")
    if len({row["id"] for row in rows}) != n:
        raise ValueError("Challenge IDs must be unique")
    components = _components(threads)
    by_id = {str(row["thread_id"]): row for row in threads}
    if len(by_id) != len(threads):
        raise ValueError("Corpus thread IDs must be unique")
    blocked = {components[token] for row in seen for token in _tokens(row) if token in components}
    texts = [row.get("text", row.get("customer_text", "")).casefold() for row in seen]
    examples, categories = [], set()
    allowed_fields = {"id", "text", "origin", "category", "thread_id", "contrast_pair_id", "setup"}
    for row in rows:
        if set(row) - allowed_fields:
            raise ValueError("Challenge input must contain only case identity, text, origin and boundary setup")
        text, origin, category = row.get("text"), row.get("origin"), row.get("category")
        if not isinstance(text, str) or not text.strip() or origin not in {"real", "synthetic"}:
            raise ValueError("Challenge requires customer text and explicit real/synthetic origin")
        if category not in CHALLENGE_CATEGORIES:
            raise ValueError("Unknown boundary category")
        categories.add(category)
        pair = row.get("contrast_pair_id")
        if pair is not None and (not isinstance(pair, str) or not pair.strip()):
            raise ValueError("contrast_pair_id must be nonempty when supplied")
        if category == "operational_failure":
            setup = row.get("setup")
            if (not isinstance(setup, dict) or set(setup) != {"inject"}
                    or not isinstance(setup["inject"], str) or setup["inject"] not in CHALLENGE_FAILURES):
                raise ValueError("Operational failure setup must contain only a supported inject control")
        elif "setup" in row:
            raise ValueError("Execution setup is only supported for operational_failure cases")
        if origin == "real":
            corpus_row = by_id.get(str(row.get("thread_id")))
            if corpus_row is None or text != corpus_row.get("customer_text"):
                raise ValueError("Real challenge text/thread must match the corpus exactly")
            root = components[str(row["thread_id"])]
            if root in blocked:
                raise ValueError("Challenge overlaps an inspected or already selected conversation")
            blocked.add(root)
        elif row.get("thread_id") is not None:
            raise ValueError("Synthetic cases must not claim a corpus thread_id")
        if process.extractOne(text.casefold(), texts, scorer=fuzz.ratio, score_cutoff=85):
            raise ValueError("Challenge is a near-duplicate of a prior/calibration exposure")
        for previous in examples:
            if fuzz.ratio(text.casefold(), previous["text"].casefold()) < 85:
                continue
            contrast = pair and pair == previous.get("contrast_pair_id") and (
                origin == "synthetic" or previous["origin"] == "synthetic")
            if not contrast or text.casefold() == previous["text"].casefold():
                raise ValueError("Near-duplicate challenge cases require an explicit synthetic contrast pair")
        examples.append({**row, "split": "challenge"})
    if REQUIRED_CHALLENGE_CATEGORIES - categories:
        raise ValueError("Challenge omits a required boundary category")
    pairs = Counter(row["contrast_pair_id"] for row in examples if row.get("contrast_pair_id"))
    if any(count < 2 for count in pairs.values()):
        raise ValueError("Every declared contrast pair must contain at least two cases")
    return _write_partition(exposure_registry, registry, out, policy, examples, "challenge", None,
                            extras={"submitted_challenge_cases.jsonl": cases.read_bytes()}, metadata={
        "population": "Independently authored boundary scenarios; real and synthetic counts reported separately",
        "sampling": "Authored cases validated against all prior/calibration exposure; no random boundary claim",
        "limitations": "Oversampled boundary suite; not a representative coverage estimate; paired cases dependent",
        "author_id": author_id, "author_type": author_type, "independent_authoring_attested": True,
        "origin_counts": dict(Counter(row["origin"] for row in examples)),
        "category_counts": dict(Counter(row["category"] for row in examples)),
        "contrast_group_count": len(pairs),
        "execution_note": "Operational setup must be applied by the runner; locking a case is not execution",
    })


def _validate_lock(directory: Path, policy_path: Path) -> tuple[dict, list[dict]]:
    lock = read_json(directory / "SAMPLE.lock.json")
    if lock.get("partition") not in {"confirmation", "calibration", "challenge"}:
        raise ValueError("Unknown locked partition")
    required = {"examples.jsonl", "policy.snapshot.yaml", "intents.snapshot.yaml",
                "reasons.snapshot.yaml", "EXPOSURE_REGISTRY.json"}
    if lock.get("partition") == "challenge":
        required.add("submitted_challenge_cases.jsonl")
    if lock.get("version") != 1 or set(lock.get("files", {})) != required:
        raise ValueError("Unsupported or incomplete sample lock")
    for name, digest in lock["files"].items():
        if not (directory / name).is_file() or sha256(directory / name) != digest:
            raise ValueError(f"Locked file changed: {name}")
    if sha256(policy_path) != lock["files"]["policy.snapshot.yaml"]:
        raise ValueError("Policy differs from locked labeling policy")
    examples = read_jsonl(directory / "examples.jsonl")
    if len(examples) != lock.get("n") or len({row["id"] for row in examples}) != len(examples):
        raise ValueError("Locked sample count/IDs invalid")
    return lock, examples


def _labels_from_submission(directory: Path, submission: bytes, reviewer_id: str,
                            examples: list[dict]) -> list[dict]:
    partition = read_json(directory / "SAMPLE.lock.json").get("partition")
    fields = _packet_fields(partition)
    reader = csv.DictReader(io.StringIO(submission.decode("utf-8-sig"), newline=""))
    if reader.fieldnames is None or len(reader.fieldnames) != len(fields) or set(reader.fieldnames) != set(fields):
        raise ValueError("Submission must have exactly the human labeling packet columns")
    rows = list(reader)
    if len(rows) != len(examples) or {row.get("id") for row in rows} != {row["id"] for row in examples}:
        raise ValueError("Missing, duplicate or extra human label IDs")
    intents = {row["id"] for row in yaml.safe_load(
        (directory / "intents.snapshot.yaml").read_text(encoding="utf-8"))["intents"]}
    reasons = {row["id"] for row in yaml.safe_load(
        (directory / "reasons.snapshot.yaml").read_text(encoding="utf-8"))["reason_codes"]}
    by_id, result = {row["id"]: row for row in rows}, []
    for example in examples:
        row = by_id[example["id"]]
        if set(row) != set(fields) or any(value is None for value in row.values()):
            raise ValueError("Submission columns must match the human labeling packet")
        if row["text"] != example["text"]:
            raise ValueError(f"Customer text changed: {example['id']}")
        if partition == "challenge" and row["scenario_setup"] != _scenario_setup(example):
            raise ValueError(f"Boundary scenario setup changed: {example['id']}")
        if row["label_source"] != "human" or row["annotator"] != reviewer_id:
            raise ValueError("Every row requires matching named human annotator and label_source=human")
        if row["intent"] not in intents or row["secondary_intent"] not in intents | {""}:
            raise ValueError("Invalid intent")
        if row["sentiment"] not in SENTIMENTS or row["should_escalate"].lower() not in {"true", "false"}:
            raise ValueError("Valid sentiment and explicit true/false decision required")
        escalate = row["should_escalate"].lower() == "true"
        if (escalate and row["escalation_reason_code"] not in reasons) or (
            not escalate and row["escalation_reason_code"]):
            raise ValueError("Reason must agree with escalation decision")
        if not row["notes"].strip():
            raise ValueError("Human labeling rationale is required")
        result.append({**example, "label_source": "human", "annotator": reviewer_id, "gold": {
            "intent": row["intent"], "secondary_intent": row["secondary_intent"] or None,
            "should_escalate": escalate, "escalation_reason_code": row["escalation_reason_code"] or None,
            "sentiment": row["sentiment"], "notes": row["notes"],
        }})
    return result


def import_labels(out: Path, submission: Path, reviewer_id: str, reviewed_at: str,
                  policy: Path, attest_independent_human_labeling: bool = False) -> dict:
    if not attest_independent_human_labeling or not reviewer_id.strip():
        raise ValueError("Named reviewer must attest independent human labeling without AI labels/outputs")
    forbidden = ["LABEL_REVIEW.json", "labels.jsonl", "submitted_human_labels.csv", "INFERENCE_STARTED.json"]
    if any((out / name).exists() for name in forbidden) or any(out.rglob("*predictions*.jsonl")):
        raise ValueError("Refusing to replace labels or import after recorded inference")
    lock, examples = _validate_lock(out, policy)
    imported_at = _now()
    if not _date(lock["created_at"]) <= _date(reviewed_at) <= _date(imported_at):
        raise ValueError("Human review must occur after sample lock and before import")
    raw = submission.read_bytes()
    labels = _labels_from_submission(out, raw, reviewer_id, examples)
    (out / "submitted_human_labels.csv").write_bytes(raw)
    write_jsonl(out / "labels.jsonl", labels)
    review = {
        "version": 1, "n": len(labels), "reviewer_id": reviewer_id, "reviewer_type": "human",
        "provenance": "independent human labels; authorship and independence self-attested",
        "ai_labels_visible": False, "system_outputs_visible": False,
        "independent_human_labeling_attested": True,
        "reviewed_at": reviewed_at, "imported_at": imported_at,
        "sample_lock_sha256": sha256(out / "SAMPLE.lock.json"),
        "examples_sha256": sha256(out / "examples.jsonl"), "policy_sha256": sha256(policy),
        "labels_sha256": sha256(out / "labels.jsonl"),
        "submission_sha256": sha256(out / "submitted_human_labels.csv"),
    }
    write_json(out / "LABEL_REVIEW.json", review)
    return review


def validate_confirmation(labels_path: Path, policy_path: Path, expected_n: int = 200) -> dict[str, Any]:
    """Fail closed on incomplete, changed or post-inference human labeling records."""
    return validate_partition(labels_path, policy_path, expected_n, "confirmation")


def validate_challenge(labels_path: Path, policy_path: Path, expected_n: int = 80) -> dict[str, Any]:
    """Require human policy labels for the separately reported boundary suite."""
    return validate_partition(labels_path, policy_path, expected_n, "challenge")


def validate_partition(labels_path: Path, policy_path: Path, expected_n: int,
                       partition: str) -> dict[str, Any]:
    labels_path, policy_path = Path(labels_path), Path(policy_path)
    directory = labels_path.parent
    if labels_path.name != "labels.jsonl":
        raise ValueError("Use imported labels.jsonl")
    lock, examples = _validate_lock(directory, policy_path)
    if lock.get("partition") != partition:
        raise ValueError(f"Expected {partition} partition, got {lock.get('partition')}")
    review = read_json(directory / "LABEL_REVIEW.json")
    if review.get("version") != 1 or review.get("n") != expected_n or lock["n"] != expected_n:
        raise ValueError("Confirmation count differs from prespecified count")
    if review.get("reviewer_type") != "human" or not review.get("reviewer_id", "").strip():
        raise ValueError("Named human label review is required")
    if (review.get("independent_human_labeling_attested") is not True
            or review.get("ai_labels_visible") is not False or review.get("system_outputs_visible") is not False):
        raise ValueError("Independent human labels before outputs are required")
    paths = {"sample_lock_sha256": directory / "SAMPLE.lock.json", "examples_sha256": directory / "examples.jsonl",
             "policy_sha256": policy_path, "labels_sha256": labels_path,
             "submission_sha256": directory / "submitted_human_labels.csv"}
    for key, path in paths.items():
        if not path.is_file() or review.get(key) != sha256(path):
            raise ValueError(f"Human review binding changed: {key}")
    labels = _labels_from_submission(directory, (directory / "submitted_human_labels.csv").read_bytes(),
                                     review["reviewer_id"], examples)
    if read_jsonl(labels_path) != labels:
        raise ValueError("Imported labels differ from original human submission")
    if not _date(lock["created_at"]) <= _date(review["reviewed_at"]) <= _date(review["imported_at"]) <= datetime.now(UTC):
        raise ValueError("Invalid human review chronology")
    marker = directory / "INFERENCE_STARTED.json"
    if marker.exists():
        started = read_json(marker)
        if (_date(started["started_at"]) <= _date(review["imported_at"])
                or started.get("labels_sha256") != review["labels_sha256"]):
            raise ValueError("Human label import must precede first inference on these exact labels")
    return review


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command, count, seed in (("prepare", 200, 2026091805), ("prepare-calibration", 100, 2026091806)):
        sample = commands.add_parser(command)
        sample.add_argument("--exposure-registry", type=Path, required=True)
        sample.add_argument("--out", type=Path, required=True)
        sample.add_argument("--policy", type=Path, required=True)
        sample.add_argument("--n", type=int, default=count)
        sample.add_argument("--seed", type=int, default=seed)
    challenge = commands.add_parser("prepare-challenge")
    challenge.add_argument("--exposure-registry", type=Path, required=True)
    challenge.add_argument("--out", type=Path, required=True)
    challenge.add_argument("--policy", type=Path, required=True)
    challenge.add_argument("--cases", type=Path, required=True)
    challenge.add_argument("--author-id", required=True)
    challenge.add_argument("--author-type", choices=["human", "ai"], required=True)
    challenge.add_argument("--n", type=int, default=80)
    challenge.add_argument("--attest-independent-authoring", action="store_true")
    imported = commands.add_parser("import-labels")
    imported.add_argument("--out", type=Path, required=True)
    imported.add_argument("--submission", type=Path, required=True)
    imported.add_argument("--reviewer-id", required=True)
    imported.add_argument("--reviewed-at", required=True)
    imported.add_argument("--policy", type=Path, required=True)
    imported.add_argument("--attest-independent-human-labeling", action="store_true")
    validate = commands.add_parser("validate")
    validate.add_argument("--labels", type=Path, required=True)
    validate.add_argument("--policy", type=Path, required=True)
    validate.add_argument("--expected-n", type=int, default=200)
    validate.add_argument("--partition", choices=["confirmation", "calibration", "challenge"], default="confirmation")
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    if command in {"prepare", "prepare-calibration", "prepare-challenge"}:
        function = {"prepare": prepare, "prepare-calibration": prepare_calibration,
                    "prepare-challenge": prepare_challenge}[command]
        result = function(**args)
        print(f"Locked {result['n']} {result['partition']} cases; human_labels.csv is blank. No inference performed.")
    elif command == "import-labels":
        result = import_labels(**args)
        print(f"Imported {result['n']} human labels with exact provenance bindings.")
    else:
        result = validate_partition(args["labels"], args["policy"], args["expected_n"], args["partition"])
        print(f"Validated {result['n']} independently human-labeled {args['partition']} cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
