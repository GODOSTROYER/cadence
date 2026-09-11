"""Comparative LLM judge (CONTRACT.md §7, §13, §15.5).

One call per golden example scores the reply drafts of every judged system at once. Candidates are
anonymised as A/B/C in an order drawn from ``random.Random(SEED + index)`` (position-bias
mitigation) and de-anonymised into one ``JudgeScore`` row per ``(id, system)``.
"""

from __future__ import annotations

import random
import threading
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from cadence.config import JUDGED_SYSTEMS, SEED, models_config
from cadence.utils.log import get_logger
from cadence.utils.text import normalize_ws, truncate

log = get_logger(__name__)

LABELS: tuple[str, ...] = ("A", "B", "C")
Label = Literal["A", "B", "C"]
Verdict = Literal["ship", "edit", "reject"]
MAX_EVIDENCE = 3
MAX_SNIPPET_CHARS = 320

RUBRIC = (
    "Rubric (1–5 ints): **grounded** (every claim/step/link traceable to evidence or general brand "
    "practice; 1 = invented policy), **resolves** (addresses the actual issue with a concrete next step; "
    "1 = irrelevant), **tone** (SpotifyCares voice: warm, brief, ≤1 emoji, no grovelling, ≤280 chars), "
    "**safe** (no refund/compensation promises, no legal commitments, asks only for a DM — never "
    "passwords/card numbers), **overall** (holistic). Verdict: ship (overall ≥4, no flags) / edit / reject."
)
"""The §7 rubric, verbatim — the judge prompt states it word for word."""

SYSTEM_PROMPT = (
    "You are a meticulous quality reviewer for @SpotifyCares, Spotify's customer-support Twitter account. "
    "You grade candidate public replies to a customer tweet. Be strict, consistent and evidence-driven: "
    "reward replies that stay within what the brand has historically said and done, and penalise invented "
    "links, policies or promises. Return only the requested JSON."
)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------
class JudgeScores(BaseModel):
    """The five rubric dimensions, integers 1–5."""

    grounded: int = Field(description="1-5; every claim/step/link traceable to evidence or brand practice")
    resolves: int = Field(description="1-5; addresses the actual issue with a concrete next step")
    tone: int = Field(
        description="1-5; SpotifyCares voice: warm, brief, <=1 emoji, no grovelling, <=280 chars"
    )
    safe: int = Field(
        description="1-5; no refund/legal promises, asks only for a DM, never passwords or card numbers"
    )
    overall: int = Field(description="1-5; holistic quality")


class JudgeFlags(BaseModel):
    """Hard failure flags."""

    hallucinated_link_or_policy: bool = Field(description="reply invents a link, policy, feature or promise")
    asks_sensitive_info: bool = Field(
        description="reply asks for a password, card number or other sensitive data"
    )
    wrong_issue: bool = Field(description="reply addresses a different issue than the customer raised")


class JudgeCandidate(BaseModel):
    """Assessment of one anonymised candidate reply."""

    label: Label
    scores: JudgeScores
    flags: JudgeFlags
    verdict: Verdict
    rationale: str = Field(description="one sentence explaining the scores")


class JudgeOutput(BaseModel):
    """Structured judge response for one customer message."""

    candidates: list[JudgeCandidate] = Field(min_length=1, description="one assessment per candidate label")
    ranking: list[str] = Field(min_length=1, description="candidate labels ordered best to worst")


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
def _as_dict(row: Any) -> dict[str, Any]:
    return row.model_dump() if hasattr(row, "model_dump") else dict(row)


def _evidence_snippets(agent_row: dict[str, Any] | None) -> list[dict[str, str]]:
    if not agent_row:
        return []
    snippets = []
    for ev in (agent_row.get("evidence") or [])[:MAX_EVIDENCE]:
        snippets.append(
            {
                "thread_id": str(ev.get("thread_id", "")),
                "customer": truncate(normalize_ws(str(ev.get("customer_text") or "")), MAX_SNIPPET_CHARS),
                "brand": truncate(normalize_ws(str(ev.get("brand_reply") or "")), MAX_SNIPPET_CHARS),
            }
        )
    return snippets


def build_judge_prompt(
    golden_row: dict[str, Any],
    labelled: Sequence[tuple[str, dict[str, Any]]],
    evidence: Sequence[dict[str, str]],
) -> str:
    """Compose the comparative judging prompt for one golden example.

    ``labelled`` is ``[(label, prediction_row), ...]`` in the shuffled presentation order.
    """
    labels = [lab for lab, _ in labelled]
    lines: list[str] = [
        "Grade the candidate public replies to the customer tweet below.",
        "",
        RUBRIC,
        "",
        "Flags (booleans per candidate): hallucinated_link_or_policy, asks_sensitive_info, wrong_issue.",
        "",
        "## Customer message",
        normalize_ws(str(golden_row.get("text") or "")) or "(empty)",
        "",
        "## Historical brand reply (reference for how the brand handles this — NOT ground truth)",
        normalize_ws(str(golden_row.get("historical_brand_reply") or "")) or "(none recorded)",
        "",
        "## Evidence retrieved from the brand's past conversations (use to check groundedness)",
    ]
    if evidence:
        for i, ev in enumerate(evidence, start=1):
            lines.append(f"{i}. customer: {ev['customer'] or '(empty)'}")
            lines.append(f"   brand: {ev['brand'] or '(empty)'}")
    else:
        lines.append("(no evidence available — judge groundedness against general brand practice)")
    lines += ["", "## Candidate replies"]
    for lab, row in labelled:
        draft = normalize_ws(str(row.get("reply_draft") or ""))
        lines.append(f"Reply {lab}: {draft or '(empty reply)'}")
    lines += [
        "",
        "## Instructions",
        f"Score every candidate ({', '.join(labels)}) on all five dimensions with integers 1-5, set the three "
        "flags, give a verdict (ship / edit / reject) and a one-sentence rationale. Then provide `ranking`: "
        f"the labels ordered best to worst, containing each of {', '.join(labels)} exactly once. "
        "Judge each reply on its own merits; the order of presentation carries no information.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# De-anonymisation
# ---------------------------------------------------------------------------
def _clamp_score(value: Any) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 1


def _ranks(output: JudgeOutput, labels: Sequence[str]) -> dict[str, int]:
    """Map label -> rank (1 = best); falls back to overall-score order when the ranking is incomplete."""
    ranking = [lab for lab in output.ranking if lab in labels]
    ranking = list(dict.fromkeys(ranking))
    if len(ranking) != len(labels):
        by_overall = sorted(output.candidates, key=lambda c: (-c.scores.overall, c.label))
        ranking = list(dict.fromkeys([c.label for c in by_overall if c.label in labels] + list(labels)))
    return {lab: i + 1 for i, lab in enumerate(ranking)}


def deanonymise(
    golden_id: str,
    labelled: Sequence[tuple[str, str]],
    output: JudgeOutput,
    *,
    rater: str,
    rated_at: str,
) -> list[dict[str, Any]]:
    """Turn a ``JudgeOutput`` into §7 ``JudgeScore`` rows, one per ``(id, system)``.

    ``labelled`` is ``[(label, system), ...]``. Candidates the model omitted are logged and skipped;
    duplicate labels keep the first occurrence. ``rank`` (1 = best) is added from the ranking.
    """
    label_to_system = dict(labelled)
    ranks = _ranks(output, [lab for lab, _ in labelled])
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for cand in output.candidates:
        if cand.label not in label_to_system or cand.label in seen:
            continue
        seen.add(cand.label)
        rows.append(
            {
                "id": golden_id,
                "system": label_to_system[cand.label],
                "rater": rater,
                "scores": {k: _clamp_score(v) for k, v in cand.scores.model_dump().items()},
                "flags": {k: bool(v) for k, v in cand.flags.model_dump().items()},
                "verdict": cand.verdict,
                "rationale": normalize_ws(cand.rationale),
                "rated_at": rated_at,
                "rank": ranks[cand.label],
            }
        )
    missing = set(label_to_system) - seen
    if missing:
        log.warning("judge omitted candidates %s for %s", sorted(missing), golden_id)
    return rows


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def _resolve_client(client: Any | None) -> Any:
    if client is not None:
        return client
    try:
        from cadence.llm import get_client
    except ImportError as exc:
        raise RuntimeError(
            "no LLM client passed and cadence.llm is unavailable; pass a client (e.g. a MockClient) explicitly"
        ) from exc
    return get_client("judge")


def _rater_name(client: Any, meta: Any) -> str:
    name = getattr(meta, "model", None) or getattr(client, "model", None)
    return str(name) if name else "judge"


def judged_ids(existing_rows: Iterable[dict[str, Any]], systems: Sequence[str]) -> set[str]:
    """Ids that already have a judge row for every system in ``systems`` (resume support)."""
    seen: dict[str, set[str]] = {}
    for row in existing_rows:
        seen.setdefault(str(row.get("id")), set()).add(str(row.get("system")))
    required = set(systems)
    return {gid for gid, systems_seen in seen.items() if required <= systems_seen}


def run_judge(
    golden_rows: Sequence[dict[str, Any]],
    predictions: dict[str, Sequence[Any]],
    client: Any | None = None,
    systems: tuple[str, ...] = JUDGED_SYSTEMS,
    *,
    skip_ids: Iterable[str] | None = None,
    sink: Callable[[list[dict[str, Any]]], None] | None = None,
    temperature: float | None = None,
    workers: int = 1,
) -> list[dict[str, Any]]:
    """Judge the reply drafts of ``systems`` for every golden row with one comparative call each.

    Args:
        golden_rows: golden examples (§7); ``index`` for the shuffle seed is the position in this list.
        predictions: ``{system: [AgentResponse | dict, ...]}`` aligned to the golden set by ``id``.
        client: an ``LLMClient``; defaults to ``cadence.llm.get_client("judge")``.
        systems: which systems to compare (a system without a prediction for an id is skipped).
        skip_ids: ids already judged (resume) — they are not re-sent to the model.
        sink: optional callback receiving each example's rows as soon as they exist (incremental
            persistence).
        temperature: sampling temperature; defaults to ``judge_temperature`` in ``config/models.yaml``.

    Returns:
        JudgeScore rows (§7) with an extra ``rank`` field, for all examples judged in this call.
    """
    llm = _resolve_client(client)
    if temperature is None:
        temperature = float(models_config().get("judge_temperature", 0.0))
    skip = set(skip_ids or ())
    by_system: dict[str, dict[str, dict[str, Any]]] = {}
    for system, rows in predictions.items():
        if system in systems:
            by_system[system] = {str(_as_dict(r).get("id")): _as_dict(r) for r in rows}
    results: list[dict[str, Any]] = []
    emit_lock = threading.Lock()

    def judge_one(index: int, golden: dict[str, Any]) -> list[dict[str, Any]]:
        gid = str(golden.get("id"))
        candidates = [(s, by_system[s][gid]) for s in systems if gid in by_system.get(s, {})]
        if not candidates:
            log.warning("no predictions to judge for %s; skipping", gid)
            return []
        order = list(range(len(candidates)))
        random.Random(SEED + index).shuffle(order)
        labelled = [(LABELS[i], candidates[j][1]) for i, j in enumerate(order)]
        label_to_system = [(LABELS[i], candidates[j][0]) for i, j in enumerate(order)]
        prompt = build_judge_prompt(golden, labelled, _evidence_snippets(by_system.get("agent", {}).get(gid)))
        output, meta = llm.generate_json(prompt, JudgeOutput, system=SYSTEM_PROMPT, temperature=temperature)
        rows = deanonymise(
            gid,
            label_to_system,
            output,
            rater=_rater_name(llm, meta),
            rated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        with emit_lock:
            results.extend(rows)
            if sink is not None and rows:
                sink(rows)
        log.info("judged %s (%d candidates, cached=%s)", gid, len(rows), getattr(meta, "cached", None))
        return rows

    todo = [(index, golden) for index, golden in enumerate(golden_rows) if str(golden.get("id")) not in skip]
    if workers <= 1:
        for index, golden in todo:
            judge_one(index, golden)
    else:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in [pool.submit(judge_one, index, golden) for index, golden in todo]:
                future.result()
    return results
