# Astra development reply and retrieval review

**Provisional AI review, not human verification.** Reviewer astra-xhigh; model gpt-6-astra; reasoning effort xhigh. Run routing_dev-52ea832b86ce; rubric support-review-v1; recorded 2026-09-17T03:46:52Z. Human review remains outstanding. This development sample does not establish benchmark or production safety.

## Coverage

| System | Replies | Automatic | Useful automatic | Useful coverage |
| --- | ---: | ---: | ---: | ---: |
| trained_tfidf_lr | 30 | 24 | 2 | 6.7% |
| agent | 30 | 8 | 2 | 6.7% |
| selective | 30 | 11 | 1 | 3.3% |

Useful automatic cases: trained_tfidf_lr d2_019 (clarification), d2_020 (incognito check); agent d2_004 (device restart), d2_019 (clarification); selective d2_001 (playlist ownership clarification). An appropriate reply can still accompany a separately incorrect routing decision; this metric does not replace routing evaluation.

Reviewed all 90 exact replies and all 276 evidence rows. There are 180 distinct customer/evidence pairs: identical repeated contents across systems received the same individually authored judgment, then were expanded to their original row identities. No heuristic assigned ratings. Exact reply hashes, original evidence content, unique complete coverage, reviewer identity, scores and Boolean judgments passed scripts/18_review_coverage.py. Run identity uses the repository's normalized-text hash, including CRLF normalization.

Retrieval: 137/276 relevant (49.6%); 43/276 support a useful next step (15.6%); 39/276 qualify as current advice (14.1%). Dimensions are separate: an off-topic example may contain a safely reusable diagnostic question. Current advice requires usable present guidance; a false value can mean unverified, incomplete, historical, or unsupported by the assistant's capabilities, rather than proven factually false.

## Highest-value defects

1. **Unsupported current actions:** d2_009, d2_010 and d2_013 repeat 2017 active-development promises; d2_003 and d2_029 promise feedback forwarding; d2_024 promises release timing. Removing DM requests alone leaves these failures.
2. **Meaning changes during synthesis:** selective d2_007 turns a restriction on Spotify-created playlists into a restriction on user-created playlists. d2_014 answers a missing Daily Mix with recommendation-tuning advice. Topic words alone do not establish issue fit.
3. **Safe but unhelpful deferral:** the generic human-review template offers no actual handoff destination or targeted question. It also misreads the celebratory d2_023 announcement as a fault.
4. **Broken or empty information delivery:** d2_012 says information exists but supplies none; nearest-neighbor replies retain placeholders, copied names and truncation. Do not silently remove a link while leaving its surrounding promise.
5. **Unusable account workflows:** agent repeatedly requests emails/usernames through unavailable DMs and claims backstage access. Retrieved precedents are not authorization or capability.
6. **Historical evidence quality:** the matching shuffle source t_1299103 ignores its original customer's self-harm statement. Historical brand replies require quality checks before reuse, even when topic matching is strong.

## Current-source checks

- The Family household condition remains supported, but this does not validate promises to forward feedback or resolve a temporary study-abroad case: [Spotify Family plan](https://support.spotify.com/us/article/family-plan/).
- Spotify currently says it does not offer phone support, supporting the phone-request clarification replies: [Contact us](https://support.spotify.com/us/article/contact-us/).
- Current guidance distinguishes an account identifier from an editable display name: [Username and display name](https://support.spotify.com/cg-en/article/username-and-display-name/).
- Recommendation controls depend on plan and shuffle mode; a blanket prohibition for user playlists is unsupported: [Shuffle play](https://support.spotify.com/us/article/shuffle-play/).
- Student verification is renewed yearly with a four-year limit, and eligibility issues have a provider support route: [Premium Student](https://support.spotify.com/us/article/premium-student/), [Charged too much](https://support.spotify.com/us/article/charged-too-much/).

These checks assess currency; they do not retroactively turn historical retrieval records into current sources. Frozen predictions and the original blank retrieval CSV were not modified.
