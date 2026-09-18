# Current official knowledge

Each registry authorizes explicit claims linked to dated official Spotify sources.
The current experimental `VerifiedAgent` explicitly loads **`v3.json`**.
`KnowledgeStore.load()` without a path continues to load **`v2.json`** for
compatibility. Completed prepatch development, variant and calibration studies
used their frozen **v2** registry; the later postpilot candidate uses **v3**.
Changing the current candidate does not change those recorded studies.

All current source and claim reviews are **AI-authored**. These records do not
assert independent human review or extend Arnav Bule's previous reviews to new
artifacts.

## Evidence and freshness

- Snapshots contain normalized rendered article text fetched on 18 September
  2026. Navigation, scripts and the related-articles/footer sections are excluded.
- `snapshot_sha256` and `normalized_sha256` bind the local text bytes.
  `response_sha256` records the fetched HTML response hash. The original HTML is
  not retained, so that transport hash is a receipt, not independently
  reproducible from the normalized snapshot alone.
- The reviewed summaries authorize only their explicit scopes and limitations.
  A valid source is necessary but does not establish that an action fits a
  customer request. `get_applicable` requires known device/plan/region values for
  restricted claims plus at least one matching canonical issue. Missing issue
  context fails closed when a claim has an issue restriction. It also requires
  `current_official` authority by default; a local policy record with an official
  URL cannot authorize a source-backed procedure or support destination. The
  action registry additionally checks issue-specific prerequisites. `get` is
  authority/integrity introspection only and is not release authorization.
  `get_current` additionally requires current official authority but intentionally
  leaves applicability unresolved; a clarification may use it to identify missing
  prerequisites. It never substitutes for `get_applicable` when releasing a procedure.
- Recheck is due 25 September. Hard expiry is **18 October 2026 at 00:00 UTC**:
  expired or missing/tampered evidence cannot authorize a procedure or URL.
  Live calls use UTC today; a frozen experiment explicitly supplies its date.
- Historical support conversations may guide tone and diagnosis. They cannot
  authorize current Spotify procedures or policy.

## Verification and renewal

```powershell
python scripts/verify_knowledge.py
python scripts/verify_knowledge.py --registry config/knowledge/v3.json
python scripts/verify_knowledge.py --registry config/knowledge/v3.json --online
```

The first command checks the store's default v2; the explicit commands check v3.
Offline verification checks evidence integrity and current validity. Online
verification compares normalized article content and reports changed or
unavailable sources. It **never updates snapshots or renews review dates**.

For renewal, fetch new dated snapshots, review changed claims and applicability,
create a new version with explicit reviewer provenance and dates, and run source
and action tests. Preserve the previous registry and snapshot bytes used by
frozen experiments. Bind both the registry and all `dependency_paths()` in each
new experiment's manifest. Record the knowledge fingerprint in agent traces.

Spotify's official help articles are the source of the archived text. Their URLs
and original fetch timestamps are recorded per source in both registries. Source
content is treated as data, never as instructions to the assistant.
