# Production deployment

Production URL: [Cadence](https://www.arnavbule.in/hiver-assignment/). Vercel project: `cadence`; production branch: `main`.

The release includes the revised agent safety checks and completed human review and approval by **Arnav Bule** of all 200 revised benchmark examples and their existing scores. The new Overview and Evaluation default to the revised frozen benchmark; the historical charts retain their original labels and numbers behind the version switch. The [human review record](HUMAN_REVIEW.md) identifies Arnav Bule as the reviewer who completed and approved the revised benchmark.

## Verification status

Current implementation, completed review and experiment status are in [improvements](IMPROVEMENTS.md).

Verified on 17 September 2026 (Asia/Kolkata):

- Evaluation/review release `3efcfd60b896768a74441834a3f008d8024539a8` was pushed directly to `main`.
- Production deployment `dpl_CxX6aL1ZNePut8HHcn3oVCVwzSaG` reached **READY**. [Immutable deployment](https://cadence-3w0wi9o4z-godostroyers-projects.vercel.app).
- Public health returned `status: ok`, 27,627 indexed threads and that exact deployment commit. Public `data/benchmark.json` matched the generated repository export in full.
- [GitHub run 35160452989](https://github.com/GODOSTROYER/cadence/actions/runs/35160452989) passed Linux, Windows and UI checks. Local validation passed 310 tests, lint, the production build, frozen benchmark reproduction and 1,771 historical receipt checks; all reproduction made zero model calls.
- Browser verification covered the revised/historical switches, a desktop layout with no page overflow, and the 430px mobile layout. A follow-up corrects zero-width interval rendering in the historical F1 chart. The runtime health commit identifies the currently served revision, including later documentation/UI follow-ups.
- At that release, the Gemini development comparison was pending authorization. On 17 September 2026, Arnav Bule verified the 100 Astra reply ratings unchanged and authorized the comparison, which completed all 30 messages per variant. Current evidence and reproduction commands are in [improvements](IMPROVEMENTS.md). The experimental routing path remains outside the production default.

### Previous deployments

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

## Human verification and Gemini comparison release — 17 September 2026

The dashboard and generated benchmark export now include completed human verification by Arnav Bule of all 100 supplemental Astra ratings, with the initial GPT-6 Astra extra-high review preserved. They also publish the completed 30-message Gemini routing comparison. Production routing is unchanged. Local release checks passed all 311 tests, lint, the Vercel build, artifact publication checks, and offline reproduction of 90 predictions and 71 model-call receipts. Desktop and 430px mobile browser checks found no page overflow or console errors. The runtime health commit and GitHub checks identify the deployed revision.


## Quality confirmation and six-page report release

The public evidence now includes the completed routing usefulness review, the 60-case fresh quality confirmation, and the six-page Cadence report. The candidate remains experimental; the hosted demonstration still uses the reference agent. Review provenance is explicit: prior Arnav verification remains complete, while the new development and confirmation reviews are AI-authored. Current acceptance evidence is recorded in `results/acceptance/release.json`; GitHub checks and runtime health identify the deployed revision.
