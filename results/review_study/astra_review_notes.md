# Astra blind review notes

- Reviewer: astra-xhigh; model: gpt-6-astra; reasoning effort: xhigh.
- Source: blind_packet.jsonl and rubric.md only. No mapping, existing judge scores, or benchmark report/labels were read.
- Scope: 100 anonymous replies covering 50 paired customer messages.
- Run: holdout_final-b8317d6. Rubric: support-review-v1.
- Recorded at: 2026-09-16T22:38:01Z.
- Status: initial AI review completed; all scores subsequently reviewed and verified unchanged by Arnav Bule on 17 September 2026. See HUMAN_VERIFICATION.json and arnav_verified_summary.json. These remain the original AI-authored rows; the separate human record preserves the two-stage provenance.

## Results

| Verdict | Replies |
| --- | ---: |
| ship | 6 |
| edit | 35 |
| reject | 59 |

Flags overlap: 42 replies have hallucinated_link_or_policy; 16 ask for sensitive information; 23 address the wrong issue.

## Review interpretation

Each reply received an individual rubric assessment and rationale. Structural code assembled and validated the authored entries; it did not assign scores.

Historical product restrictions, promotional prices, account procedures, and team actions were not accepted as current authority. The link/policy flag includes replies that present unresolved placeholders or unverified historical destinations as usable current support guidance; it does not assert that every underlying domain is malicious or nonexistent.

The sensitive-information flag includes account email requests through unsupported DM/account workflows and an email-signup request without a verified destination. A public track link, device version, or conditional error screenshot was not treated as a request for secrets.

Polite requests for missing diagnostic information can be useful next steps. Vague holding replies and acknowledgements can be safe but receive low resolution scores when they leave the actual message unanswered. Claims that a DM was sent, an account will be inspected, or a team has been notified fail the capability constraint.

## Key failures

- Wrong-topic retrieval, such as billing mistaken for the artist TWICE, educational outreach mistaken for artist catalog availability, and a bookmark icon request answered with download troubleshooting.
- Unsupported account lookups, DM actions, team referrals, and developer-work statements.
- Historical feature limits, launch status, payment terms, and timelines presented as current.
- Placeholder links, missing destinations, copied customer names, and truncated replies.
- Safe but unhelpful human-review templates that provide no concrete route or useful clarification.

## Validation

Checked exact coverage of every packet id/alias, exact supplied reply hashes, unique keys, required metadata, integer scores from 1 through 5, Boolean flags, and allowed verdict/response-kind values. Subsequent human verification is complete; the accepted scores and original Astra attribution are recorded separately.
