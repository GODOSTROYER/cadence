import hashlib
import json

import pytest

from cadence.eval.archive import archive_inputs, resolve_input, snapshot_dependencies
from cadence.eval.provenance import sha256


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def freeze(root, names):
    directory = root / "results/experiment"
    inputs = {name: sha256(root / name) for name in names}
    write(directory, "manifest.json", json.dumps({"frozen": {"inputs": inputs}}).encode())
    return directory, inputs


def test_old_config_and_labels_resolve_after_active_files_change(tmp_path):
    names = ("config/escalation.yaml", "data/confirmation/labels.jsonl")
    originals = {names[0]: b"route: human\r\n", names[1]: b'{"id":"old","gold":true}\r\n'}
    for name, data in originals.items():
        write(tmp_path, name, data)
    directory, inputs = freeze(tmp_path, names)
    manifest_before = (directory / "manifest.json").read_bytes()
    record = archive_inputs(directory, inputs, root=tmp_path)
    for name, data in originals.items():
        write(tmp_path, name, b"new active policy or labels\n")
        archived = resolve_input(directory, name, inputs[name], root=tmp_path)
        assert archived.read_bytes() == data
        assert record["inputs"][name]["raw_sha256"] == hashlib.sha256(data).hexdigest()
    assert (directory / "manifest.json").read_bytes() == manifest_before
    assert archive_inputs(directory, inputs, root=tmp_path) == record


def test_corrupt_archive_never_falls_back_to_valid_active_config(tmp_path):
    name = "config/policy.json"
    write(tmp_path, name, b'{"escalate":true}\n')
    directory, inputs = freeze(tmp_path, [name])
    archive_inputs(directory, inputs, root=tmp_path)
    path = resolve_input(directory, name, inputs[name], root=tmp_path)
    path.write_text('{"escalate":false}\n')
    with pytest.raises(ValueError, match="Frozen dependency"):
        resolve_input(directory, name, inputs[name], root=tmp_path)


def test_raw_archive_hash_rejects_even_newline_only_mutation(tmp_path):
    name = "config/policy.json"
    write(tmp_path, name, b'{"escalate":true}\r\n')
    directory, inputs = freeze(tmp_path, [name])
    archive_inputs(directory, inputs, root=tmp_path)
    path = resolve_input(directory, name, inputs[name], root=tmp_path)
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    assert sha256(path) == inputs[name]
    with pytest.raises(ValueError, match="bytes changed"):
        resolve_input(directory, name, inputs[name], root=tmp_path)


def test_archive_requires_available_original_bytes_before_migrating(tmp_path):
    name = "config/policy.json"
    write(tmp_path, name, b"old\n")
    directory, inputs = freeze(tmp_path, [name])
    write(tmp_path, name, b"changed\n")
    with pytest.raises(ValueError, match="Frozen dependency"):
        archive_inputs(directory, inputs, root=tmp_path)
    assert not (directory / "INPUT_ARCHIVE.json").exists()
    assert not (tmp_path / "results/input_archive").exists()


def test_shared_archive_deduplicates_config_across_runs(tmp_path):
    name = "config/policy.json"
    write(tmp_path, name, b"policy\n")
    first, inputs = freeze(tmp_path, [name])
    second = tmp_path / "results/other"
    write(second, "manifest.json", (first / "manifest.json").read_bytes())
    archive_inputs(first, inputs, root=tmp_path)
    archive_inputs(second, inputs, root=tmp_path)
    assert resolve_input(first, name, inputs[name], root=tmp_path) == resolve_input(
        second, name, inputs[name], root=tmp_path)


def test_large_corpus_is_not_copied_and_changed_bytes_fail(tmp_path):
    name = "data/processed/corpus.jsonl.gz"
    path = write(tmp_path, name, b"large binary corpus")
    directory, inputs = freeze(tmp_path, [name])
    record = archive_inputs(directory, inputs, root=tmp_path, max_archive_bytes=3)
    assert record["inputs"][name]["storage"] == "verified_root"
    assert resolve_input(directory, name, inputs[name], root=tmp_path) == path
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="Frozen dependency"):
        resolve_input(directory, name, inputs[name], root=tmp_path)


def test_future_snapshot_captures_nested_knowledge_actual_rubric_and_code(tmp_path):
    names = ("src/cadence/agent.py", "config/knowledge/source.json", "config/policy_v2.json",
             "docs/rubrics/new.md", "data/dev/labels.jsonl", "scripts/runner.py")
    for name in names:
        write(tmp_path, name, f"original {name}\n".encode())
    directory = tmp_path / "results/future"
    inputs = snapshot_dependencies(directory, [tmp_path / name for name in names[3:]], root=tmp_path)
    assert set(inputs) == set(names)
    write(directory, "manifest.json", json.dumps({"frozen": {"inputs": inputs}}).encode())
    archive_inputs(directory, inputs, root=tmp_path)
    for name in names:
        write(tmp_path, name, b"new candidate\n")
        assert resolve_input(directory, name, inputs[name], root=tmp_path).read_bytes() == (
            f"original {name}\n".encode())


def test_existing_python_snapshot_beats_new_source_and_cannot_be_overwritten(tmp_path):
    name = "src/cadence/agent.py"
    write(tmp_path, name, b"old = 1\n")
    directory, inputs = freeze(tmp_path, [name])
    archived = write(directory / "source_snapshot", name, b"old = 1\n")
    write(tmp_path, name, b"new = 2\n")
    archive_inputs(directory, inputs, root=tmp_path)
    assert resolve_input(directory, name, inputs[name], root=tmp_path) == archived
    archived.write_bytes(b"corrupt = 3\n")
    with pytest.raises(ValueError, match="Frozen dependency"):
        resolve_input(directory, name, inputs[name], root=tmp_path)


def test_migration_record_is_bound_to_original_manifest(tmp_path):
    name = "config/policy.json"
    write(tmp_path, name, b"policy\n")
    directory, inputs = freeze(tmp_path, [name])
    archive_inputs(directory, inputs, root=tmp_path)
    manifest = directory / "manifest.json"
    manifest.write_text(manifest.read_text() + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="bind this frozen manifest"):
        resolve_input(directory, name, inputs[name], root=tmp_path)


@pytest.mark.parametrize("name", ["../secret", "config/../../secret", "C:/secret", "/secret", "./policy.json"])
def test_resolver_rejects_paths_outside_declared_roots(tmp_path, name):
    with pytest.raises(ValueError, match="repository-relative"):
        resolve_input(tmp_path / "experiment", name, "a" * 64, root=tmp_path)
