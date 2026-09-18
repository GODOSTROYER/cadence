"""Scoped, auditable operational faults for matched challenge experiments.

Faults run at the structured-client boundary, after provider retries would have
failed. They are synthetic failures, not billed provider attempts or live latency
measurements. A stage skipped by an agent is explicitly ``not_reached``. A
historical agent without a separate audit or versioned knowledge is explicitly
``not_applicable`` for those controls; it has not passed such a challenge.

Only instance-owned dependencies are replaced. No historical agent code, module
globals, shared source files, or persisted provider cache is changed.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from cadence.knowledge.models import KnowledgeRegistry, KnowledgeSource
from cadence.knowledge.store import KnowledgeStore
from cadence.llm.base import LLMError

CHALLENGE_FAILURES = frozenset({
    "provider_timeout", "provider_error", "malformed_extraction", "malformed_audit",
    "expired_knowledge", "missing_knowledge", "context_budget", "deadline_exhausted", "retrieval_error",
})
_SYSTEMS = frozenset({"agent", "quality", "balanced", "verified"})
_AUDIT_SCHEMAS = frozenset({"ReleaseReview", "Audit", "ResponseAudit"})


class ChallengeContextBudgetError(LLMError):
    """The provider rejected a request that exceeds its context limit."""


def validate_setup(scenario_setup: Mapping | None, systems: Iterable[str] | None = None) -> dict:
    """Reject unknown controls, extra payload and systems before any inference.

    The return value is a fresh, JSON-compatible dictionary. The caller must
    decode CSV JSON before calling; strings are not silently treated as no-op.
    """
    if scenario_setup is None:
        scenario_setup = {}
    if not isinstance(scenario_setup, Mapping):
        raise ValueError("Challenge setup must be an object")
    if scenario_setup and (
        set(scenario_setup) != {"inject"}
        or not isinstance(scenario_setup.get("inject"), str)
        or scenario_setup["inject"] not in CHALLENGE_FAILURES
    ):
        raise ValueError("Challenge setup must contain exactly one supported inject control")
    if systems is not None and (isinstance(systems, str) or not set(systems) <= _SYSTEMS):
        raise ValueError("Unknown challenge comparison system")
    return dict(scenario_setup)


def _trigger(record: dict, stage: str) -> None:
    record["triggered"] = True
    record["stage"] = stage
    record["events"].append({"stage": stage, "inject": record["inject"]})


class _ClientFault:
    def __init__(self, wrapped: Any, record: dict):
        self.wrapped, self.record, self.calls = wrapped, record, 0

    def __getattr__(self, key):
        return getattr(self.wrapped, key)

    def generate_json(self, prompt, schema, **kwargs):
        self.calls += 1
        inject = self.record["inject"]
        audit = schema.__name__ in _AUDIT_SCHEMAS
        target = audit if inject == "malformed_audit" else self.calls == 1
        if not target:
            return self.wrapped.generate_json(prompt, schema, **kwargs)
        stage = "response_audit" if audit else "initial_structured_call"
        _trigger(self.record, stage)
        if inject == "provider_timeout":
            raise TimeoutError("Injected structured-provider timeout")
        if inject == "provider_error":
            raise LLMError("Injected structured-provider unavailability")
        if inject == "context_budget":
            raise ChallengeContextBudgetError("Injected provider context-limit rejection")
        if inject == "deadline_exhausted":
            # Expire actual active request budgets, when available, before the
            # next provider/cache invocation. No wall-clock sleeping is needed.
            request = getattr(self.wrapped, "_request", None)
            for budget in getattr(request, "budgets", ()):
                budget.deadline = 0.0
                budget.deadline_exceeded = True
            raise TimeoutError("Injected request deadline exhaustion")
        # Exercise the real structured schema parser with malformed JSON. This
        # raises its normal ValidationError, rather than inventing a usable
        # object or returning an invalid object past the client contract.
        return schema.model_validate_json("{malformed challenge JSON"), None


class _RetrievalFault:
    def __init__(self, wrapped: Any, record: dict):
        self.wrapped, self.record = wrapped, record

    def __getattr__(self, key):
        return getattr(self.wrapped, key)

    def search(self, *args, **kwargs):
        _trigger(self.record, "retrieval")
        raise OSError("Injected historical-retrieval unavailability")


def _knowledge_fault(store: KnowledgeStore, agent: Any, inject: str) -> KnowledgeStore:
    """Build a separate validated registry; source bytes remain untouched."""
    if inject == "missing_knowledge":
        sources = tuple(s for s in store.registry.sources if s.role != "current_official")
        retained = {s.id for s in sources}
        claims = tuple(c for c in store.registry.claims if c.source_id in retained)
    else:
        day = getattr(agent, "as_of", None) or datetime.now(UTC).date()
        cutoff = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        sources = []
        for source in store.registry.sources:
            if source.role != "current_official":
                sources.append(source)
                continue
            payload = source.model_dump()
            payload.update(expires_on=day, recheck_on=min(source.recheck_on, day),
                           verified_on=min(source.verified_on, day), fetched_at=min(source.fetched_at, cutoff))
            sources.append(KnowledgeSource.model_validate(payload))
        claims = store.registry.claims
    registry = KnowledgeRegistry.model_validate({
        **store.registry.model_dump(), "sources": sources, "claims": claims,
    })
    return KnowledgeStore(registry, store.root)


@contextmanager
def challenge_setup(agent: Any, client: Any, scenario_setup: Mapping | None) -> Iterator[dict]:
    """Apply one setup for one invocation, yielding mutable execution metadata.

    Use the agent's existing observed client as ``client``. When it is the
    runner's InvocationClient, insert below its observation layer so exceptions
    remain recorded. The metadata is final after leaving the context, even when
    the invocation raises. All replacements are restored in ``finally``.
    """
    setup = validate_setup(scenario_setup)
    inject = setup.get("inject")
    record = {"inject": inject, "applicable": bool(inject), "triggered": False,
              "status": "pending" if inject else "not_requested", "stage": None,
              "synthetic": bool(inject), "events": [], "note": ""}
    changes = []

    def replace(obj, name, value):
        changes.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    try:
        if inject in {"expired_knowledge", "missing_knowledge"}:
            store = getattr(agent, "knowledge", None)
            if not isinstance(store, KnowledgeStore):
                record.update(applicable=False, status="not_applicable",
                              note="This historical comparator has no versioned current-knowledge dependency.")
            else:
                replace(agent, "knowledge", _knowledge_fault(store, agent, inject))
                _trigger(record, "knowledge_registry")
                record["knowledge_sha256"] = agent.knowledge.fingerprint()
        elif inject == "malformed_audit" and not any(
            cls.__name__ in {"QualityAgent", "BalancedAgent", "VerifiedAgent"} for cls in type(agent).__mro__
        ):
            record.update(applicable=False, status="not_applicable",
                          note="This comparator has no separate response-audit structured call.")
        elif inject == "retrieval_error":
            if not hasattr(agent, "retriever"):
                raise ValueError("Retrieval challenge requires an agent retriever")
            replace(agent, "retriever", _RetrievalFault(agent.retriever, record))
        elif inject:
            if getattr(agent, "client", None) is not client:
                raise ValueError("Challenge client must be the agent's observed client")
            if hasattr(client, "client") and isinstance(getattr(client, "calls", None), list):
                replace(client, "client", _ClientFault(client.client, record))
            else:
                replace(agent, "client", _ClientFault(client, record))
        yield record
    finally:
        for obj, name, original in reversed(changes):
            setattr(obj, name, original)
        if record["applicable"]:
            record["status"] = "applied" if record["triggered"] else "not_reached"
            if not record["triggered"]:
                record["note"] = "The invocation never reached the targeted dependency/stage; no fault coverage claimed."
