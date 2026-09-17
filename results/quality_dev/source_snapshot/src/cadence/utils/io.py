"""JSON / JSONL helpers. Always UTF-8, gzip-aware, pathlib-based."""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any


def _open(path: Path, mode: str):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, mode + "t", encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def read_json(path: Path) -> Any:
    with _open(Path(path), "r") as f:
        return json.load(f)


def write_json(path: Path, obj: Any, indent: int | None = 2) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _open(path, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
        f.write("\n")


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return
    with _open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(Path(path)))


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]], append: bool = False) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with _open(path, "a" if append else "w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")
            n += 1
    return n
