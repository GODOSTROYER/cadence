"""Nearest-neighbour historical reply (CONTRACT.md §13/§15.1, used by the ``simple`` baseline).

The reply draft is the first brand reply of the BM25 top-1 thread, with the example's own thread
excluded so a golden example can never retrieve itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from cadence.utils.text import normalize_ws


class SupportsSearch(Protocol):
    """The slice of ``cadence.retrieval.index.Retriever`` (§15.2) the baselines rely on."""

    def search(self, query: str, k: int = 6, exclude_thread_ids: set[str] | None = None) -> list[Any]: ...


@dataclass(frozen=True)
class NNReply:
    """Nearest-neighbour reply plus the citation and evidence item that ground it."""

    reply: str = ""
    citations: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)


def nearest_reply(
    retriever: SupportsSearch, text: str, exclude_thread_ids: set[str] | None = None
) -> NNReply:
    """Top-1 historical brand reply for ``text``; empty ``NNReply`` when there is no hit."""
    if not text.strip():
        return NNReply()
    hits = retriever.search(text, k=1, exclude_thread_ids=exclude_thread_ids or set())
    if not hits:
        return NNReply()
    hit = hits[0]
    thread = _hit_attr(hit, "thread") or {}
    thread_id = str(_hit_attr(hit, "thread_id") or thread.get("thread_id") or "")
    reply = normalize_ws(str(thread.get("first_reply_text") or ""))
    return NNReply(
        reply=reply,
        citations=[thread_id] if thread_id else [],
        evidence=[evidence_item(thread_id, float(_hit_attr(hit, "score") or 0.0), thread)],
    )


def evidence_item(thread_id: str, score: float, thread: Mapping[str, Any]) -> dict[str, Any]:
    """An ``EvidenceItem``-shaped dict (§6) built from a processed thread (§3)."""
    replies = thread.get("brand_replies") or []
    first = replies[0] if replies and isinstance(replies[0], Mapping) else {}
    return {
        "thread_id": thread_id,
        "score": round(score, 4),
        "customer_text": str(thread.get("customer_text") or ""),
        "brand_reply": str(thread.get("first_reply_text") or first.get("text") or ""),
        "resolved_links": list(first.get("resolved_links") or []),
        "cited": True,
    }


def _hit_attr(hit: Any, name: str) -> Any:
    """Read a ``Hit`` field whether the retriever returns dataclasses or dicts."""
    if isinstance(hit, Mapping):
        return hit.get(name)
    return getattr(hit, name, None)
