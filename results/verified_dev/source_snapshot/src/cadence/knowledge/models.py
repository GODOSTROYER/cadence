"""Versioned claims and the source records that authorize them.

Current official sources, local response policy, and historical examples have
different roles. A historical example cannot authorize a current procedure.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClaimScope(BaseModel):
    """Empty dimensions mean the claim states no restriction on that dimension."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    devices: tuple[str, ...] = ()
    plans: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()

    def matches(self, *, device: str | None = None, plan: str | None = None,
                region: str | None = None, issues: Iterable[str] | None = None) -> bool:
        """Restricted claims require a known matching value, never a guess."""
        observed_issues = {issues} if isinstance(issues, str) else set(issues or ())
        issue_matches = not self.issues or bool(set(self.issues) & observed_issues)
        return issue_matches and all(not allowed or (value is not None and value.lower() in
                   {item.lower() for item in allowed})
                   for value, allowed in ((device, self.devices), (plan, self.plans),
                                          (region, self.regions)))


class KnowledgeClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    text: str = Field(min_length=1)
    source_id: str
    scope: ClaimScope = Field(default_factory=ClaimScope)
    limits: tuple[str, ...] = ()
    status: Literal["reviewed", "unavailable"] = "reviewed"


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    role: Literal["current_official", "local_policy", "historical"]
    authority: str
    url: str | None = None
    final_url: str | None = None
    title: str
    snapshot: str
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fetched_at: datetime
    response_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    normalized_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    extraction: str
    verified_on: date
    recheck_on: date
    expires_on: date
    reviewer: str
    reviewer_type: Literal["ai", "human"]
    review_status: Literal["reviewed", "unavailable"]

    @model_validator(mode="after")
    def validate_authority(self) -> KnowledgeSource:
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at needs an explicit timezone")
        if not self.fetched_at.date() <= self.verified_on <= self.recheck_on <= self.expires_on:
            raise ValueError("source dates must be ordered: fetched <= verified <= recheck <= expiry")
        if self.role == "current_official":
            for url in (self.url, self.final_url):
                parts = urlsplit(url or "")
                if parts.scheme != "https" or parts.hostname not in {"support.spotify.com", "www.spotify.com"}:
                    raise ValueError("current official knowledge requires a verified Spotify HTTPS origin")
                if parts.username or parts.password or parts.port not in (None, 443):
                    raise ValueError("source URLs cannot contain credentials or non-HTTPS ports")
            if not self.response_sha256:
                raise ValueError("official knowledge requires the fetched-response hash")
        return self


class KnowledgeRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str
    temporal_contract: str
    sources: tuple[KnowledgeSource, ...]
    claims: tuple[KnowledgeClaim, ...]

    @model_validator(mode="after")
    def validate_ids(self) -> KnowledgeRegistry:
        sources = {s.id for s in self.sources}
        if len(sources) != len(self.sources) or len({c.id for c in self.claims}) != len(self.claims):
            raise ValueError("duplicate source or claim identifier")
        if any(c.source_id not in sources for c in self.claims):
            raise ValueError("claim references an unknown source")
        return self
