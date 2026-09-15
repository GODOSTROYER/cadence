# Production deployment

Production URL: [Cadence](https://www.arnavbule.in/hiver-assignment/). Vercel project: `cadence`; production branch: `main`.

The release includes the revised agent safety checks and completed human review and approval by **Arnav Bule** of all 200 revised benchmark examples and their existing scores. Dashboard charts retain their historical labels and numerical results. Original frozen benchmark files describe execution-time provenance; [human review](HUMAN_REVIEW.md) records the subsequent approval.

## Verification status

Verified on 16 September 2026 (Asia/Kolkata):

- [PR #1](https://github.com/GODOSTROYER/cadence/pull/1) merged into `main` at `ee6c9dba389b50f065d851c2e1689b016dd037e7`.
- Vercel deployment `dpl_Wm1zRRv2RsUizEfw5XFHXKD1F5Eo` reached **READY**, target **production**. Build logs identify `main`, commit `ee6c9db`.
- [Immutable release URL](https://cadence-4es2hfxot-godostroyers-projects.vercel.app) and public proxy belong to the existing `cadence` project.
- The public Overview and Method pages render Arnav Bule’s completed human review and approval of all 200 revised benchmark examples and their existing scores. Historical charts remain labelled separately.
- Public `/hiver-assignment/api/health` returned HTTP 200 and `status: ok`, with 27,627 indexed threads. Live inference is configured; this verification made no new model calls.
- The new deployment’s runtime error log query returned no entries in the inspected ten-minute window. This is a release smoke check, not sustained monitoring.
- All PR CI checks passed on Linux, Windows and UI. Local verification passed 283 Python tests, ruff, the production UI build, frozen benchmark replay and 1,771 historical receipt checks.

A release follow-up clarifies that archived repository receipts are separate from the empty deployed visitor cache and labels the footer SHA as the historical evaluation revision. It preserves all scores and review attribution. The earlier read-only deployment measurements in the engineering audit describe the previous deployment, not this release.
