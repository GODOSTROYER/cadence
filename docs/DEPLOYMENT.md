# Production deployment

Production URL: [Cadence](https://www.arnavbule.in/hiver-assignment/). Vercel project: `cadence`; production branch: `main`.

The release includes the revised agent safety checks and completed human review and approval by **Arnav Bule** of all 200 revised benchmark examples and their existing scores. Dashboard charts retain their historical labels and numerical results. The [human review record](HUMAN_REVIEW.md) identifies Arnav Bule as the reviewer who completed and approved the revised benchmark.

## Verification status

Verified on 16 September 2026 (Asia/Kolkata):

- [PR #1](https://github.com/GODOSTROYER/cadence/pull/1) merged into `main` at `ee6c9dba389b50f065d851c2e1689b016dd037e7`.
- Vercel deployment `dpl_Wm1zRRv2RsUizEfw5XFHXKD1F5Eo` reached **READY**, target **production**. Build logs identify `main`, commit `ee6c9db`.
- [Immutable release URL](https://cadence-4es2hfxot-godostroyers-projects.vercel.app) and public proxy belong to the existing `cadence` project.
- The public Overview and Method pages render Arnav Bule’s completed human review and approval of all 200 revised benchmark examples and their existing scores. Historical charts remain labelled separately.
- Public `/hiver-assignment/api/health` returned HTTP 200 and `status: ok`, with 27,627 indexed threads. Live inference is configured; this verification made no new model calls.
- The new deployment’s runtime error log query returned no entries in the inspected ten-minute window. This is a release smoke check, not sustained monitoring.
- All PR CI checks passed on Linux, Windows and UI. Local verification passed 283 Python tests, ruff, the production UI build, frozen benchmark replay and 1,771 historical receipt checks.

The follow-up `83f82aa07f52bbd1d002bbe1467feb461fca63f0` deployed as `dpl_GJtCYNgAHfXw1UaYBv9qHCkgMptx` (**READY**, production); all Linux, Windows and UI CI checks passed. Live browser verification confirmed the corrected archive receipt wording, historical evaluation SHA and Arnav Bule review credit. Public health returned HTTP 200; the runtime error query returned no entries. It preserves all scores and review attribution. The earlier read-only deployment measurements in the engineering audit describe the previous deployment, not this release.


## Social link preview

The static HTML includes Open Graph and Twitter large-image metadata with **Cadence — Arnav Bule**, a short description, the canonical public URL and an absolute PNG URL. Crawlers can read these tags without executing the React application.

The preview image is `ui/public/assets/cadence-social-v1.png`, served at `/hiver-assignment/assets/cadence-social-v1.png`. Keeping it under `assets/` avoids the SPA fallback and uses the existing asset cache policy. When changing the artwork, create a new versioned filename and update both image tags; social platforms may retain an older preview until they re-scrape the page.

Artwork: 1730 × 909 PNG, generated with the built-in image-generation tool. Design prompt: a restrained dark editorial card matching Cadence, near-black background, ivory italic serif title, green equalizer, “Cadence”, “by Arnav Bule”, “An AI support agent that knows when to reply—and when to escalate”, and the public site address.
