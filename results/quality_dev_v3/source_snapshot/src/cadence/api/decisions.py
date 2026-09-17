"""Parser for ``DECISION_LOG.md`` (format in CONTRACT.md §15.6)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HEADING = re.compile(r"^##\s+(\d+)\.\s*(.+?)\s*$")
_FIELD = re.compile(r"^\*\*(Decision|Why):\*\*\s*(.*)$", re.IGNORECASE)
_FIELD_KEYS = {"decision": "decision", "why": "why"}


def parse_decision_log_text(text: str) -> list[dict[str, Any]]:
    """Parse decision-log markdown into ``[{n, title, decision, why}]`` sorted by ``n``.

    A decision starts at a ``## N. Title`` heading; ``**Decision:**`` and ``**Why:**`` paragraphs may
    span several lines and end at the next field, heading or blank line. Text outside those fields
    (intro, horizontal rules) is ignored.
    """
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    field: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = _HEADING.match(line)
        if heading:
            current = {"n": int(heading.group(1)), "title": heading.group(2), "decision": "", "why": ""}
            entries.append(current)
            field = None
            continue
        if current is None:
            continue
        match = _FIELD.match(line)
        if match:
            field = _FIELD_KEYS[match.group(1).lower()]
            current[field] = match.group(2).strip()
            continue
        if not line:
            field = None
            continue
        if field is not None:
            current[field] = f"{current[field]} {line}".strip()
    return sorted(entries, key=lambda e: e["n"])


def parse_decision_log(path: Path) -> list[dict[str, Any]]:
    """Parse the decision log at ``path``; a missing file yields ``[]``."""
    path = Path(path)
    if not path.exists():
        return []
    return parse_decision_log_text(path.read_text(encoding="utf-8"))
