# Astra AI review: quality development v3

Reviewer: `astra-xhigh`; model: `gpt-6-astra`; reasoning effort: `xhigh`.
Run: `routing_dev-ee6807234fbc`; rubric: `support-review-v1`; completed 2026-09-17 UTC.

These are provisional AI judgments, not human validation or final-test evidence. This is a development set already used during implementation. No confirmation examples, labels or outcomes were consulted for these judgments.

## Coverage and usefulness

Every one of the 60 exact reply drafts has an individually authored score and rationale, bound to its reply hash. All 290 returned evidence rows are reviewed. The 180 distinct historical customer/evidence pairs reused their earlier authored judgments only after exact customer and evidence text equality was checked; 50 new current-source/policy pairs were separately judged in their customer context. Duplicate source pairs expand to the exact required system identities.

| System | Cases | Automatic | Useful automatic | Useful coverage | Useful resolutions | Useful clarifications |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent | 30 | 9 | 2 | 6.7% | 1 | 1 |
| quality | 30 | 1 | 1 | 3.3% | 0 | 1 |

Useful automatic follows script 18: an automatic draft must ship, score at least 4 for grounding, resolution and safety, have no flags, and be a resolution or clarification. Valid handoffs are assessed separately and never counted as automatic help.

- Agent verdicts: 6 ship, 6 edit, 18 reject. Useful automatic cases are `d2_004` (restart) and `d2_019` (clarification).
- Quality verdicts: 6 ship, 24 edit, 0 reject. Its single automatic case, `d2_001`, asks who created the playlist. The other five ship judgments are legitimate handoffs (`d2_002`, `d2_005`, `d2_019`, `d2_025`, `d2_030`). All 29 remaining quality cases escalate.
- Defining unsafe automatic drafts explicitly as safety score below 4, agent has 6/9: `d2_003`, `d2_009`, `d2_011`, `d2_014`, `d2_024`, `d2_029`. Quality has 0/1. This is a narrow development observation with only one candidate automatic output; it cannot establish general safety.
- Retrieval judgments across both systems: 159/290 relevant, 76/290 support a next step, and 86/290 contain current advice. A current source can be irrelevant to a particular issue; a real support channel does not prove that escalation is necessary.

## Highest-value findings

1. **Safe handoffs dominate instead of useful public help.** Quality repeatedly supplies a real contact link where an appropriate clarification or published fact could advance the issue. It unnecessarily gives a support handoff for a generic technical-help request (`d2_006`) and an unspecified problem (`d2_018`), misses the track/version question (`d2_028`), and repeats contact support for a customer already frustrated with that route (`d2_015`, `d2_027`). Its useful automatic coverage is lower than the existing agent on this development set.
2. **Approved text can still name the wrong issue.** Quality calls a username-change request a login problem (`d2_016`), calls postal-code validation a charge (`d2_020`), and treats an excited announcement as a problem (`d2_023`). These are usefulness and factual-fit defects despite constrained text. The first two would benefit from preserving the customer's actual issue; the third needs an acknowledgment rather than a handoff.
3. **Specific public guidance is absent.** Student-status verification (`d2_026`) would benefit from the official verification-specific route. Username requests (`d2_016`, `d2_029`) would benefit from distinguishing account identifiers and display names. Family travel (`d2_003`) needs careful explanation of the actual household rule rather than an unqualified generic referral.
4. **Existing agent still fabricates actions or live status.** It promises staff work or forwarding (`d2_003`, `d2_009`, `d2_011`, `d2_029`) and supplies unsupported release timing (`d2_024`). Its missing-Daily-Mix answer (`d2_014`) answers the wrong problem. Several escalated drafts request private account identifiers by DM and promise account investigation despite absent tools. These drafts need rejection even when their routing decision escalates.
5. **Historical evidence is not current operational authority.** Old support replies may ask sensible questions but do not establish present plans, feature behavior, release timing, staff work, or available DM/account tooling. Current playback guidance is useful only for matching technical faults, not catalogue, username or playlist feature requests. The clarification policy allows a relevant missing-information question; it does not make redundant questions useful.

## Sources and verification

Official pages consulted include [contact support](https://support.spotify.com/us/article/contact-us/), [playback troubleshooting](https://support.spotify.com/us/article/spotify-not-playing/), [reinstallation](https://support.spotify.com/us/article/reinstall-spotify/), [username/display-name distinction](https://support.spotify.com/cg-en/article/username-and-display-name/), [Premium Student](https://support.spotify.com/us/article/premium-student/), [Premium Family](https://support.spotify.com/us/article/family-plan/) and [shuffle](https://support.spotify.com/us/article/shuffle-play/). The current-source excerpts and clarification policy were evaluated for relevance separately from currency. A false currency judgment on historical evidence may mean unsupported or unverified, not proven false.

The reviewed CSV uses LF line endings before hashing. Script 18 passed with repository-relative input arguments, verifying all reply identities, rubric dimensions and flags, complete evidence coverage, unchanged evidence/customer strings and matching AI reviewer provenance. Input hashes are recorded in `astra_coverage.json`. These findings describe the frozen development outputs and do not authorize claims of human-reviewed or general benchmark safety.
