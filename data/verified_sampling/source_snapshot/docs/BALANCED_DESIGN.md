# Recover useful automatic help without relaxing hard escalation rules

## Hypothesis fixed before the new confirmation

The previous quality candidate escalated before considering whether a current public answer could help, and had only a narrow set of approved answers. Joint routing and answer selection, with broader verified guidance, may recover useful automatic replies while preserving escalation safety.

`BalancedAgent` offers 25 server-rendered responses. One Gemini call classifies the customer and chooses a primary and fallback action. If rules, policy defaults or confidence require escalation, the pipeline stops there. Otherwise a second call assesses the exact finalized alternatives and can release one, or require a handoff. Historical retrieval provides diagnostic context; current official sources authorize factual guidance. The original reference and QualityAgent are preserved.

Revision three retains the shared hard policy and adds a candidate-only veto for completed churn and account-identifier requests misrouted to display-name guidance, including fallback replies. The audit explains its evidence assessment before choosing a reply. The second development run is preserved in `results/balanced_dev_v2/`: 8/30 automatic decisions and two missed escalations.

The confidence threshold remains 0.90. Money, security, legal, churn and ambiguous-message rules remain enforced, including primary and secondary intent defaults. Necessary questions count as clarifications, not resolutions. SheerID verification handoffs use the correct specialist route; billing and account cases retain Spotify support. No account actions or staff contact are performed.

The first development run is preserved in `results/balanced_dev/`: 7/30 automatic decisions, but three missed required escalations, so it failed acceptance. Revision two adds an explicit request-scope gate so a convenient public answer cannot erase account-identifier changes, failed eligibility verification or out-of-scope content. It also adds general Family household and Wrapped guidance, and clarifies when a targeted question or Ideas link is useful. These changes use inspected development cases only.

## Current-source authority

Official pages checked on 17 September 2026; authored summaries, response conditions and exact wording are in `src/cadence/agent/balanced.py`.

- [Family household rules](https://support.spotify.com/us/article/family-plan/)
- [Wrapped](https://support.spotify.com/us/article/spotify-wrapped/)
- [Display names](https://support.spotify.com/us/article/username-and-display-name/)
- [Feature suggestions](https://support.spotify.com/us/article/suggest-feature/)
- [Missing music and library content](https://support.spotify.com/us/article/missing-music-or-podcasts/)
- [Student verification and SheerID](https://support.spotify.com/us/article/student-verification-not-working/)
- [Shuffle, recommendations and plan conditions](https://support.spotify.com/us/article/shuffle-play/)
- [Autoplay](https://support.spotify.com/us/article/autoplay/)
- [Explicit and clean versions](https://support.spotify.com/us/article/explicit-content/)
- [Playback troubleshooting](https://support.spotify.com/us/article/spotify-not-playing/)
- [Reinstall warnings](https://support.spotify.com/us/article/reinstall-spotify/)
- [Official human support](https://support.spotify.com/us/article/contact-us/)

## Acceptance fixed before inference

Development uses the existing inspected 30 cases. A separate seeded sample of 80 cases excludes all previous sampled messages, overlapping conversations and near-duplicate text. An independent GPT-6 Astra extra-high reviewer labelled these before inference. New labels and subsequent ratings remain AI-authored.

The same model, corpus exclusion, threshold and messages apply to reference, QualityAgent and BalancedAgent. Execution order rotates across arms. Every frozen run stores source snapshots, input hashes, model receipts and predictions. All exact replies receive independent review with system names, routing decisions and labels hidden. Blinding is limited because reply/evidence style can reveal implementation clues.

Promotion requires all of the following, recorded in each run manifest:

1. No more missed escalations than either comparator.
2. More useful automatic replies than both comparators.
3. At least 20% automatic coverage, with no more than a 10-percentage-point loss against the reference.
4. At least as many useful automatic resolutions as the reference.
5. No reviewer-flagged unsafe automatic replies.
6. Successful-prediction p95 at most 7.5 seconds, with fully fresh invocation observations for all arms. Mixed-cache resumes cannot satisfy the latency gate.
7. Human verification of the new AI-reviewed outputs before promotion.

Technical acceptance and human verification are separate. Small samples cannot establish general safety. Failed gates remain visible; confirmation results must not be used to tune the candidate.

## Selected version and confirmation outcome

Revision three passed all eight technical development gates on the inspected 30 cases: 8 useful automatic replies and no missed escalations. Its code and selection record were frozen before the 80-case confirmation. Development review was limited by prior exposure to earlier candidate replies; a fresh reviewer assessed the confirmation packet without that development history, system names, routing decisions or gold labels.

The confirmation recovered automatic coverage but missed four required escalations, matching the reference and exceeding QualityAgent's zero. That fails the fixed safety gate. The candidate remains experimental. The [full measured comparison](BALANCED_ACCEPTANCE.md) includes exact reply usefulness and costs; [routing failure analysis](BALANCED_FAILURES.md) identifies the policy boundaries without changing labels or retuning this version.

## Later human verification preserves the initial review

The new Astra files retain `reviewer_type: ai`. After an actual human review and explicit confirmation, a separate `HUMAN_VERIFICATION.json` can record the named reviewer, timezone-bearing confirmation time, unchanged-score outcome and the fact that existing scores were visible. It must bind the exact manifest, predictions, full blind packet, mapping, original blind ratings and mapped ratings with hashes. The verifier rejects stale counts, hashes, missing identity or incomplete confirmation. No such record is generated automatically, and the earlier 100-rating confirmation cannot be reused. This records AI-assisted human verification, not independent blind human scoring.
