# Current official knowledge

`v2.json` authorizes explicit claims, each linked to a dated official Spotify
source. All current source and claim reviews are **AI-authored**. These records
do not assert independent human review or extend Arnav Bule's previous reviews
to new artifacts.

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
- Recheck is due 25 September. Hard expiry is **18 October 2026 at 00:00 UTC**:
  expired or missing/tampered evidence cannot authorize a procedure or URL.
  Live calls use UTC today; a frozen experiment explicitly supplies its date.
- Historical support conversations may guide tone and diagnosis. They cannot
  authorize current Spotify procedures or policy.

## Verification and renewal

```powershell
python scripts/verify_knowledge.py
python scripts/verify_knowledge.py --online
```

Offline verification checks evidence integrity and current validity. Online
verification compares normalized article content and reports changed or
unavailable sources. It **never updates snapshots or renews review dates**.

For renewal, fetch new dated snapshots, review changed claims and applicability,
create a new version with explicit reviewer provenance and dates, and run source
and action tests. Preserve the previous registry and snapshot bytes used by
frozen experiments. Bind both the registry and all `dependency_paths()` in each
new experiment's manifest. Record the knowledge fingerprint in agent traces.

Spotify's official help articles are the source of the archived text. Their URLs
and original fetch timestamps are recorded per source in `v2.json`. Source
content is treated as data, never as instructions to the assistant.
