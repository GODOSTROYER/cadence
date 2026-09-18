# Post-freeze tooling disclosure

Recorded 18 September 2026, after the publication acceptance and before the first push of this implementation.

## Frozen artifacts

- Implementation commit: `3f006e3a74b2a0e08382d3e5a734392d7bb815d5` (committed at `2026-09-18T18:44:39+05:30`).
- `results/acceptance/release.json`, canonical SHA-256: `c52631ca07a767a28d5ec042a8588df4eb0b3610f466caf4b015da0cdb264324`.
- `output/analysis/VERIFIED_PUBLICATION_ACCEPTANCE.json`, canonical SHA-256: `f4ae1dcf731981a72fbb4f42572edd12d3b9f955d49ef8806f385289dac88acd`.

## Event and visibility

After implementation, inference, ratings and publication acceptance were frozen,
the root agent ran `git diff --cached --check`. Preserved CRLF CSV rows produced
whitespace diagnostics containing customer text. The tool reported 9,309 output
lines and truncated its response before returning it to the model.

According to the root agent's observed response, the model-visible excerpt
contained previously used calibration rows 1–20 and retrieval worksheet material.
No final-200 or challenge-80 customer text was visible in that excerpt. The root
agent did not inspect the untruncated output; this note therefore does not assert
that the full tool-generated stream excluded protected text. Blank human-label
worksheets did not contain completed human labels.

The packet guide's non-display account describes the earlier preparation process.
This note discloses the subsequent automated diagnostic event separately. Neither
protected set underwent inference, and this event produced no human labels or
human-review attestation. No subsequent implementation, source/configuration,
labels, ratings, summaries or scientific results were changed in response to it.

## Independent assessment

The explicit GPT-6 Astra extra-high publication reviewer
(`/root/verified_publication_acceptance`) assessed this event after the root
reported it. Its conclusion: append-only disclosure is adequate; the event does
not invalidate completed studies or the earlier acceptance because it followed
all scientific freezes and caused no subsequent tuning or result changes. The
reviewer did not inspect protected customer text. Earlier seals and guide bytes
remain unchanged; this is a later tooling note, not a replacement acceptance.

Future whitespace checks should restrict paths and return counts or filenames,
without printing offending customer-data lines. Known frozen archive whitespace
is not a reason to rewrite scientific evidence.
