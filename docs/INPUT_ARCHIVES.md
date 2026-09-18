# Frozen experiment inputs

Historical Quality and Balanced runs keep their original manifests, predictions,
labels and reported metrics. `INPUT_ARCHIVE.json` is an append-only migration
record binding each run's original manifest hash to its dependency locations.

- Python uses the run's existing `source_snapshot/` files.
- Small non-Python inputs use `results/input_archive/<frozen hash>/<filename>`.
  These are byte-for-byte copies, shared across runs when their input hash and
  filename agree. The archive's `.gitattributes` disables newline conversion.
- Large unchanged inputs, currently the compressed conversation corpus, remain
  at their repository path and must match the frozen hash on every verification.
  A changed or missing corpus is an explicit error, never a silent substitution.

The manifest's existing portable hash normalizes text newlines. Archive records
also store a raw-byte SHA-256 for the copied non-Python files. An existing corrupt
archive fails verification even if the active repository copy still matches.

## Historical checks

```powershell
python analysis_tools/archive_experiment_inputs.py
python analysis_tools/reproduce_quality.py
python analysis_tools/reproduce_balanced.py
```

The first command is idempotent: once sealed, it verifies the records. It cannot
reconstruct unavailable original bytes or revise a frozen manifest to accept new
inputs. Migration covers the nine existing Quality/Balanced run directories,
including the unexecuted Balanced preflight. The preflight archive is not evidence
that an evaluation was completed.

Only dependencies originally hashed by those historical manifests can be bound
retrospectively. This migration does not claim that missing historical rubric or
knowledge-source hashes were frozen before those runs.

## Future experiments

`cadence.eval.archive.snapshot_dependencies(out, files)` collects all Python source
under `src/cadence`, every nested config file, and explicitly supplied files. Supply
the experiment script, actual rubric text, labels, sampling/review records and data
sources. It returns the repository-relative hash map for `manifest.frozen.inputs`.
After creating that manifest, call `archive_inputs(out, inputs)` to seal the archive
record. Store model settings, policy version, seeds and experiment limits in the
manifest itself as well.

Resolve a frozen dependency with `resolve_input(out, name, digest)`. On experiment
resume, additionally compare the active execution dependencies with the manifest;
the archive resolver deliberately permits active configuration to change when
reproducing *historical* results.
