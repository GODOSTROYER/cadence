"""Hash-verified experiment dependencies, independent of mutable active configuration.

Frozen manifest hashes retain the project's portable CRLF-normalized convention.
Small non-Python inputs are copied byte-for-byte into one shared content-addressed
archive; their raw hashes are recorded as well. Large data files may stay at their
original location, but are always checked against the frozen hash before use.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath

from cadence.config import Paths
from cadence.eval.provenance import sha256

ARCHIVE_RECORD = "INPUT_ARCHIVE.json"
ARCHIVE_ROOT = "results/input_archive"
DEFAULT_MAX_ARCHIVE_BYTES = 2_000_000


def _relative(name: str) -> Path:
    normalized = name.replace("\\", "/")
    value = PurePosixPath(normalized)
    if (not normalized or value.is_absolute() or ".." in value.parts
            or ":" in normalized or normalized != value.as_posix()):
        raise ValueError(f"Dependency must be a normalized repository-relative path: {name}")
    return Path(*value.parts)


def _inside(root: Path, name: str) -> Path:
    path = root / _relative(name)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Dependency escapes its root: {name}")
    return path


def _archive_name(name: str, digest: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError(f"Invalid frozen digest for {name}")
    return f"{ARCHIVE_ROOT}/{digest}/{_relative(name).name}"


def _checked(path: Path, digest: str, name: str, raw_digest: str | None = None) -> Path:
    if not path.is_file() or sha256(path) != digest:
        raise ValueError(f"Frozen dependency missing or changed: {name} ({path})")
    if raw_digest is not None and hashlib.sha256(path.read_bytes()).hexdigest() != raw_digest:
        raise ValueError(f"Archived dependency bytes changed: {name}")
    return path


def _record(directory: Path) -> dict | None:
    path = directory / ARCHIVE_RECORD
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    manifest = directory / "manifest.json"
    if (record.get("version") != 1 or not manifest.is_file()
            or record.get("manifest_sha256") != sha256(manifest)):
        raise ValueError("Input archive record does not bind this frozen manifest")
    return record


def resolve_input(directory: Path, name: str, digest: str, *, root: Path = Paths.ROOT) -> Path:
    """Resolve an input against its frozen hash, preferring archived bytes.

    An existing snapshot or sealed archive record must be valid; corruption never
    silently falls through to a fresh copy in the mutable repository root.
    """
    relative = _relative(name)
    archive_name = _archive_name(name, digest)
    record = _record(directory)
    if record is not None:
        item = record.get("inputs", {}).get(name)
        if not isinstance(item, dict) or item.get("sha256") != digest:
            raise ValueError(f"Input archive record differs from frozen dependency: {name}")
        storage = item.get("storage")
        if storage == "shared_archive":
            if item.get("path") != archive_name or not item.get("raw_sha256"):
                raise ValueError(f"Invalid archived dependency location: {name}")
            return _checked(_inside(root, archive_name), digest, name, item["raw_sha256"])
        if storage == "source_snapshot" and relative.suffix == ".py":
            return _checked(_inside(directory / "source_snapshot", name), digest, name)
        if storage == "verified_root":
            return _checked(_inside(root, name), digest, name)
        raise ValueError(f"Unknown archived dependency storage: {name}")

    snapshot = _inside(directory / "source_snapshot", name)
    if snapshot.exists():
        return _checked(snapshot, digest, name)
    shared = _inside(root, archive_name)
    if shared.exists():
        return _checked(shared, digest, name)
    return _checked(_inside(root, name), digest, name)


def _copy_exact(source: Path, target: Path, digest: str, name: str) -> None:
    if target.exists():
        _checked(target, digest, name)
        return
    data = source.read_bytes()
    # Check immediately before copying to reject a dependency changed mid-freeze.
    _checked(source, digest, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    _checked(target, digest, name)


def _save_input(directory: Path, name: str, digest: str, root: Path, limit: int) -> dict:
    source = resolve_input(directory, name, digest, root=root)
    if _relative(name).suffix == ".py":
        target = _inside(directory / "source_snapshot", name)
        _copy_exact(source, target, digest, name)
        return {"sha256": digest, "storage": "source_snapshot"}
    if source.stat().st_size > limit:
        # Large dependencies use the original path only when its bytes still match.
        _checked(_inside(root, name), digest, name)
        return {"sha256": digest, "storage": "verified_root", "size_bytes": source.stat().st_size}
    archive_name = _archive_name(name, digest)
    target = _inside(root, archive_name)
    _copy_exact(source, target, digest, name)
    return {"sha256": digest, "storage": "shared_archive", "path": archive_name,
            "raw_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "size_bytes": target.stat().st_size}


def _archive_attributes(root: Path) -> None:
    path = root / ARCHIVE_ROOT / ".gitattributes"
    content = b"# Preserve the exact dependency bytes recorded in INPUT_ARCHIVE.json.\n* -text\n"
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("Shared archive byte-preservation attributes changed")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)


def archive_inputs(directory: Path, inputs: Mapping[str, str], *, root: Path = Paths.ROOT,
                   max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES) -> dict:
    """Seal existing manifest dependencies without altering the manifest or outputs.

    Idempotent, append-only migration. Missing or changed historical bytes fail
    before any input is copied; current bytes cannot masquerade as old inputs.
    """
    if max_archive_bytes < 0:
        raise ValueError("Archive size limit must be nonnegative")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("frozen", {}).get("inputs") != dict(inputs):
        raise ValueError("Archive inputs must exactly match the frozen manifest")
    existing = _record(directory)
    for name, digest in inputs.items():
        resolve_input(directory, name, digest, root=root)
    if existing is not None:
        if set(existing.get("inputs", {})) != set(inputs):
            raise ValueError("Archive record has a different dependency inventory")
        return existing
    _archive_attributes(root)
    record = {"version": 1, "manifest_sha256": sha256(manifest_path),
              "hash_convention": "cadence.eval.provenance.sha256 (portable text newlines)",
              "inputs": {name: _save_input(directory, name, digest, root, max_archive_bytes)
                         for name, digest in sorted(inputs.items())}}
    with (directory / ARCHIVE_RECORD).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return record


def snapshot_dependencies(directory: Path, files: Iterable[Path], *, root: Path = Paths.ROOT,
                          max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES) -> dict[str, str]:
    """Snapshot future runs' source, recursive config/knowledge and explicit inputs.

    Include the experiment script, labels, actual rubric text and data sources in
    ``files``. All Python source and every file beneath config are also included,
    so nested knowledge and rubric files cannot be silently left mutable. Create
    the manifest from the returned map, then call :func:`archive_inputs` to seal
    its inventory. This does not rewrite an existing manifest or archive record.
    """
    if (directory / ARCHIVE_RECORD).exists():
        raise ValueError("Experiment dependencies are already sealed")
    if max_archive_bytes < 0:
        raise ValueError("Archive size limit must be nonnegative")
    watched = {*root.glob("src/cadence/**/*.py"),
               *(path for path in (root / "config").rglob("*") if path.is_file()),
               *(path if path.is_absolute() else root / path for path in files)}
    inputs = {}
    for path in sorted(watched):
        name = path.resolve().relative_to(root.resolve()).as_posix()
        inputs[name] = sha256(path)
    directory.mkdir(parents=True, exist_ok=True)
    _archive_attributes(root)
    for name, digest in inputs.items():
        _save_input(directory, name, digest, root, max_archive_bytes)
    return inputs
