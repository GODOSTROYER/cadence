"""Reviewed article destinations. Attach only when historical evidence names the procedure."""

from functools import cache

from cadence.config import Paths
from cadence.utils.io import read_json


@cache
def canonical_links() -> list[dict]:
    return read_json(Paths.CONFIG / "canonical_links.json")


def links_for_evidence(reply: str) -> list[str]:
    return [r["url"] for r in canonical_links() if any(p in reply.lower() for p in r["phrases"])]
