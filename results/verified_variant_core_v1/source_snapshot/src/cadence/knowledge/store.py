"""Offline, fail-closed authority checks for current response claims."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from cadence.config import Paths
from cadence.knowledge.models import KnowledgeClaim, KnowledgeRegistry, KnowledgeSource


def _date(value: date | datetime | str | None) -> date:
    if value is None:
        return datetime.now(UTC).date()
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(value) if isinstance(value, str) else value


class KnowledgeStore:
    """No network fetch or implicit review renewal occurs during an agent call.

    ``get`` checks source integrity/freshness; this alone does not authorize an
    action or elevate local policy to current official evidence. ``get_applicable``
    additionally enforces known scope values, including an intersecting issue,
    and requires current official authority unless another role is explicit.
    The explicit ``as_of`` is for frozen studies; live callers use today's date.
    """

    def __init__(self, registry: KnowledgeRegistry, root: Path):
        self.registry = registry
        self.root = root.resolve()
        self.claims = {claim.id: claim for claim in registry.claims}
        self.sources = {source.id: source for source in registry.sources}

    @classmethod
    def load(cls, path: str | Path | None = None) -> KnowledgeStore:
        path = Path(path) if path is not None else Paths.CONFIG / "knowledge" / "v2.json"
        registry = KnowledgeRegistry.model_validate_json(path.read_text(encoding="utf-8"))
        return cls(registry, path.parent)

    def source_path(self, source: KnowledgeSource) -> Path:
        path = (self.root / source.snapshot).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("source snapshot leaves the knowledge registry directory")
        return path

    def unavailable_reason(self, claim_id: str, as_of: date | datetime | str | None = None) -> str | None:
        claim = self.claims.get(claim_id)
        if claim is None:
            return "unknown_claim"
        source = self.sources[claim.source_id]
        if claim.status != "reviewed" or source.review_status != "reviewed":
            return "unreviewed_source"
        if source.role == "historical":
            return "historical_source_not_current_authority"
        day = _date(as_of)
        if day < source.verified_on:
            return "source_not_yet_verified"
        # Recheck is the scheduled maintenance date; expiry is the hard stop.
        if day >= source.expires_on:
            return "expired_source"
        try:
            raw = self.source_path(source).read_bytes()
        except (OSError, ValueError):
            return "missing_or_invalid_snapshot"
        observed = hashlib.sha256(raw).hexdigest()
        if observed != source.snapshot_sha256:
            return "snapshot_hash_mismatch"
        if source.extraction == "spotify-rendered-article-text-v1" and observed != source.normalized_sha256:
            return "normalized_hash_mismatch"
        return None

    def get(self, claim_id: str, as_of: date | datetime | str | None = None) -> KnowledgeClaim | None:
        return None if self.unavailable_reason(claim_id, as_of) else self.claims[claim_id]

    def get_current(self, claim_id: str, as_of: date | datetime | str | None = None) -> KnowledgeClaim | None:
        """Inspect current official authority without asserting action applicability.

        A clarification can inspect a still-current claim to determine which
        prerequisites are missing. This method does not authorize its procedure:
        release of a procedure still requires ``get_applicable`` and the action
        contract, with genuine observed issue/device/plan/region context.
        """
        claim = self.get(claim_id, as_of)
        if claim is None or self.sources[claim.source_id].role != "current_official":
            return None
        return claim

    def get_applicable(self, claim_id: str, as_of: date | datetime | str | None = None,
                       *, device: str | None = None, plan: str | None = None,
                       region: str | None = None, issues: Iterable[str] | None = None,
                       required_role: Literal["current_official", "local_policy"] = "current_official",
                       ) -> KnowledgeClaim | None:
        claim = self.get(claim_id, as_of)
        if claim is None or self.sources[claim.source_id].role != required_role:
            return None
        return claim if claim.scope.matches(device=device, plan=plan, region=region, issues=issues) else None

    def evidence(self, claim_ids: Iterable[str], as_of: date | datetime | str | None = None) -> list[dict]:
        """EvidenceItem-compatible records. Missing authority emits no evidence."""
        result = []
        for claim_id in dict.fromkeys(claim_ids):
            claim = self.get(claim_id, as_of)
            if claim is None:
                continue
            source = self.sources[claim.source_id]
            result.append({
                "thread_id": ("policy:" if source.role == "local_policy" else "current:") + claim.id,
                "customer_text": f"{source.authority}; source_role={source.role}; "
                f"verified {source.verified_on}; reviewer_type={source.reviewer_type}; "
                f"scope={claim.scope.model_dump()}",
                "brand_reply": claim.text + (" Limits: " + " ".join(claim.limits) if claim.limits else ""),
                "resolved_links": [source.url] if source.url else [],
                "cited": False,
            })
        return result

    def verify(self, as_of: date | datetime | str | None = None) -> dict[str, str | None]:
        return {claim_id: self.unavailable_reason(claim_id, as_of) for claim_id in self.claims}

    def dependency_paths(self) -> list[Path]:
        """Exact snapshot files to bind in a new experiment's dependency manifest."""
        return sorted({self.source_path(source) for source in self.sources.values()})

    def fingerprint(self) -> str:
        """Bind metadata and the actual source bytes, including invalid/missing state."""
        digest = hashlib.sha256(self.registry.model_dump_json().encode("utf-8"))
        for source in sorted(self.sources.values(), key=lambda item: item.id):
            digest.update(source.id.encode("utf-8"))
            try:
                digest.update(self.source_path(source).read_bytes())
            except (OSError, ValueError):
                digest.update(b"MISSING_SNAPSHOT")
        return digest.hexdigest()

    def audit_record(self, claim_id: str, as_of: date | datetime | str | None = None) -> dict:
        claim = self.claims.get(claim_id)
        return {
            "claim": claim.model_dump(mode="json") if claim else None,
            "source": self.sources[claim.source_id].model_dump(mode="json") if claim else None,
            "as_of": _date(as_of).isoformat(),
            "unavailable_reason": self.unavailable_reason(claim_id, as_of),
        }
