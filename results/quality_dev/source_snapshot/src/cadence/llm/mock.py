"""Deterministic offline `LLMClient` used by tests and by `CADENCE_LLM=mock` runs.

Without a responder the mock synthesises a valid instance of the requested schema purely from
the pydantic model: defaults and examples win, otherwise each type gets a fixed placeholder.
"""

from __future__ import annotations

import types
import typing
from collections.abc import Callable
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from cadence.llm.base import CallMeta, LLMError, SchemaT

Responder = Callable[[str, type[BaseModel]], dict[str, Any]]
_UNION_ORIGINS: tuple[Any, ...] = (Union, types.UnionType)
_SEQUENCE_ORIGINS: tuple[Any, ...] = (list, set, frozenset, tuple, typing.Sequence, typing.Iterable)


def _min_items(metadata: list[Any]) -> int:
    """Smallest allowed length from a field's constraint metadata (0 when unconstrained)."""
    for item in metadata:
        value = getattr(item, "min_length", None)
        if isinstance(value, int):
            return value
    return 0


def _fill_type(annotation: Any, name: str, min_items: int = 0) -> Any:
    """Placeholder value for a type annotation; raises LLMError for types the mock cannot synthesise."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is Annotated:
        return _fill_type(args[0], name, max(min_items, _min_items(list(args[1:]))))
    if origin is Literal:
        return args[0]
    if origin in _UNION_ORIGINS:
        if type(None) in args:
            return None
        return _fill_type(args[0], name, min_items)
    if origin in _SEQUENCE_ORIGINS:
        if min_items < 1:
            return []
        item_type = args[0] if args else str
        return [_fill_type(item_type, name)]
    if origin is dict:
        return {}
    if annotation is Any:
        return f"mock-{name}"
    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            return fill_schema(annotation)
        if issubclass(annotation, Enum):
            return next(iter(annotation))
        if annotation is bool:
            return False
        if annotation is int:
            return 1
        if annotation is float:
            return 0.5
        if annotation is str:
            return f"mock-{name}"
    raise LLMError(f"MockClient cannot synthesise a value for field {name!r} of type {annotation!r}")


def _fill_field(name: str, field: FieldInfo) -> Any:
    if field.default is not PydanticUndefined:
        return field.default
    if field.default_factory is not None:
        return field.get_default(call_default_factory=True)
    if field.examples:
        return field.examples[0]
    return _fill_type(field.annotation, name, _min_items(list(field.metadata)))


def fill_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """Deterministic plain-dict payload that validates against `schema`."""
    return {name: _fill_field(name, field) for name, field in schema.model_fields.items()}


class MockClient:
    """`LLMClient` that never touches the network and records every call in `.calls`.

    `responder(prompt, schema) -> dict` lets a test script exact outputs; without one, the payload
    comes from `fill_schema`. Either way the result is validated into `schema`.
    """

    model: str = "mock"

    def __init__(self, responder: Responder | None = None, model: str = "mock") -> None:
        self.responder = responder
        self.model = model
        self.calls: list[dict[str, Any]] = []

    def generate_json(
        self,
        prompt: str,
        schema: type[SchemaT],
        *,
        system: str | None = None,
        temperature: float | None = None,
        cache: bool = True,
    ) -> tuple[SchemaT, CallMeta]:
        """Return a validated `schema` instance; the `cache` flag is accepted for interface parity and ignored."""
        payload = self.responder(prompt, schema) if self.responder is not None else fill_schema(schema)
        try:
            obj = schema.model_validate(payload)
        except ValidationError as exc:
            raise LLMError(f"MockClient payload does not satisfy {schema.__name__}: {exc}") from exc
        self.calls.append({"prompt": prompt, "schema": schema.__name__, "system": system, "temperature": temperature})
        response_json = obj.model_dump_json()
        meta = CallMeta(
            model=self.model,
            cached=False,
            latency_ms=1,
            prompt_tokens=max(len(prompt) // 4, 1),
            output_tokens=max(len(response_json) // 4, 1),
            attempts=1,
        )
        return obj, meta

    def __repr__(self) -> str:
        return f"MockClient(model={self.model!r}, calls={len(self.calls)})"


__all__ = ["MockClient", "Responder", "fill_schema"]
