# Decision log

The non-obvious calls I made while building Cadence, and why. Format is parsed by the API (`GET /api/decisions`).

## 1. Brand: @SpotifyCares, not the biggest account
**Decision:** Build for SpotifyCares (43k brand tweets, 26k conversation openers) rather than AmazonHelp or AppleSupport.
**Why:** Spotify's public replies contain real resolutions (clean-reinstall steps, "log out everywhere", help-article links) instead of an immediate "please DM us", so "grounded in how the brand historically resolved it" is testable. The product domain is bounded enough for a 10–12 intent taxonomy, and the auto-handle vs. escalate split is natural: how-to fixes are safe to automate, billing and hacked accounts are not.

## 2. One structured LLM call does classify + draft + decide
**Decision:** Retrieval runs first (BM25, no LLM), then a single Gemini call with a JSON schema returns intent, confidence, reply, citations and a decision proposal.
**Why:** The free tier is ~250 requests/day on the main model; a three-call design would triple the cost and add three points of failure. Sharing one context also keeps the reply consistent with the intent the model actually committed to. The trade-off is that intent classification cannot be evaluated free of retrieval noise, which I accept and measure via the zero-shot baseline.

## 3. Escalation is a hybrid: deterministic rules can veto the model, never the other way round
**Decision:** Regex rules for money, security, legal, churn/abuse and media-only messages force `escalate`; the LLM can only add escalations, and a confidence threshold adds a third guard.
**Why:** Missed escalations are the expensive error for a brand (a public promise about a refund is a policy commitment). Rules are auditable and cheap; the model handles the long tail. The stated reason is always the rule's when a rule fires, so reviewers can see exactly why a case was routed.

## 4. "Auto-handle" means "post without a human reading it"
**Decision:** Define the decision strictly: auto-handle only when the drafted public reply is complete, grounded, and needs no account access, money movement, policy exception or PR judgement.
**Why:** A looser definition ("the bot drafted something") would inflate the auto-handle rate and make the headline number meaningless. The strict definition also makes gold labelling reproducible because it maps to written policy, not taste.

## 5. Judge model differs from agent model, and judging is comparative
**Decision:** The judge is a different Gemini model than the agent, and one judge call scores all three candidate replies (agent, nearest-neighbour, template) for the same message with anonymised, shuffled labels.
**Why:** Same-model judging inflates scores (self-preference). Comparative scoring on one rubric gives consistent calibration across systems and cuts the call count by two thirds; shuffling counters position bias. The remaining risk (same model family) is disclosed in the report.

## 6. Ship the LLM cache so the headline reproduces without an API key
**Decision:** Every Gemini call is cached in a committed SQLite file keyed by model + prompts + schema + temperature; `make reproduce` replays it.
**Why:** "Reproduce in under 15 minutes" is impossible if reproduction means 600 rate-limited free-tier calls. Replay makes the numbers auditable byte-for-byte; a `--fresh` flag re-runs live for anyone who wants to.

## 7. Dev/test split inside the golden set
**Decision:** Hold out ~50 golden examples as `dev` for threshold tuning and prompt iteration; report every number on the remaining `test` examples only.
**Why:** Tuning the confidence threshold on the same examples you report is silent overfitting. With only ~200 examples the split costs statistical power, so all headline metrics carry bootstrap confidence intervals.

## 8. Retrieval is lexical (BM25), with a "usefulness" re-rank
**Decision:** BM25 over customer messages with a multiplier for threads whose brand reply is substantive (has a resolved help link or real steps) and a penalty for DM-only replies; no dense embeddings.
**Why:** Tweets are short and vocabulary-driven ("offline", "family plan", "web player"), where BM25 is strong, deterministic and dependency-free. The re-rank matters more than the embedding model: the point is to surface threads that show how the issue was resolved, not just similar complaints. Dense hybrid retrieval is the first item on the next-week list.

## 9. The example's own thread is excluded from retrieval during evaluation
**Decision:** When evaluating a golden example, its historical thread is removed from the retrieval candidates.
**Why:** Otherwise the agent would see the actual brand reply to the exact tweet it is answering — a leak that would inflate groundedness and reply-quality scores.

## 10. Golden labels via two independent passes plus adjudication
**Decision:** Every candidate is labelled twice from the same written guide; disagreements are adjudicated and recorded; inter-annotator kappa is reported next to model accuracy.
**Why:** A single labeller's accuracy ceiling is unknown. Kappa tells the reader how much of the model's error is label noise, and the adjudication log doubles as documentation of the hard boundary cases.

## 11. Resolve the brand's t.co links once and store them
**Decision:** Follow the top ~150 shortened links from brand replies to their final URLs and page titles, and attach them to threads.
**Why:** Opaque t.co links make grounding impossible to verify. With resolved titles ("Downloads unexpectedly removed") the agent can cite a real help article and the judge can check that the cited article exists in the evidence rather than being invented.

## 12. Anonymised handles are normalised, Spotify's own handles removed
**Decision:** `@115888`, `@117168`, `@117153` and `@SpotifyCares` are stripped; every other handle becomes `@user`; agent initials like ` /JI` are captured and removed from reply text.
**Why:** The dataset anonymised customers to numbers and Spotify's own accounts to a few fixed ids; leaving them in would let the classifier and retriever learn artefacts. Initials are brand voice signal, but the agent must sign as ` /AI`, never as a human agent.

## 13. Intents are defined from the data, then frozen before labelling
**Decision:** The taxonomy came from TF-IDF clustering plus reading several hundred openers, was written down with boundary rules, and was not changed once golden labelling started.
**Why:** Changing labels mid-way silently invalidates earlier annotations and agreement statistics. The boundary rules ("charged but no Premium" is billing, not plans) are what make two annotators agree.

## 14. Models chosen by probing the free tier, not by reputation
**Decision:** Agent and zero-shot baseline = `gemini-3.5-flash-lite`; judge = `gemini-3.1-flash-lite`.
**Why:** On the day of the run, new free-tier keys could not call any `gemini-2.5-*` model ("no longer available to new users"), every Pro model answered 429 before the first request, and the thinking Flash models (3.5, 3.6, 3.8) turned out to carry a free-tier cap of about 20 requests per day per key per model: the first agent run on `gemini-3.5-flash` died after 79 calls across five keys. A 475-call evaluation therefore has to run on the Lite models, which have far higher daily headroom. Using the same Lite model for the agent and the no-retrieval zero-shot baseline makes that comparison a clean ablation of retrieval plus the policy layer; the judge is a different model so it does not grade its own style. The 85 thinking-model predictions are kept as `results/ablation_agent_gemini-3.5-flash_partial.jsonl` and discussed, not reported as a headline.

## 15. Pool several free keys instead of waiting a day between runs
**Decision:** The client takes a list of keys, keeps a per-key rate limiter and daily counter, puts a key on cooldown when it answers 429 and tries the next one; runners use one worker thread per key.
**Why:** The full evaluation is roughly 250 agent calls, 25 zero-shot calls and 200 judge calls. One free key at ~5 requests/minute makes that a multi-hour, possibly multi-day job; five keys run it in well under an hour. Every response is cached by prompt hash, so the pooling changes throughput, never results.

## 16. One round of failure-driven fixes, with the "before" kept on disk
**Decision:** After the first full evaluation I read every error, fixed three concrete defects (the agent copied `<url>` placeholders and bare home-page links from the evidence into public replies; the judge was docking points for the policy-mandated ` /AI` signature; the churn rule missed "switching to @user"-style threats), archived the first run under `results/v1/`, and re-ran the agent and judge. The report shows both rows.
**Why:** The assignment values the proof over the system, and a failure analysis that never changes anything is just a list. Keeping v1 makes the effect of each fix measurable rather than asserted, and stops the iteration from quietly becoming test-set tuning: every change is a specific bug with a named cause, not a prompt tweak chasing a number.

## 17. The dev-set threshold rule may never pick "escalate everything"
**Decision:** `choose_threshold` picks the highest auto-handle rate whose dev recall is ≥ 0.9; if no threshold below 1.0 qualifies it falls back to the best recall-weighted F2 on dev. A threshold of 1.0 is excluded outright, and the numeric threshold is not embedded in the prompt (so changing it never invalidates the replay cache).
**Why:** With only 50 dev examples the original "highest recall" fallback selected 1.0 on the second run, which escalates every message: perfect recall, 2% auto-handle, and literally the trivial baseline. A rule that can degenerate into a baseline is not a rule. The F2 fallback still favours recall (a missed escalation is the costly error) but keeps the agent doing work.

## 18. The UI puts the caveats next to the headline numbers
**Decision:** The overview page renders "What is misleading about these numbers" directly under the metric tiles, from the same results file.
**Why:** A dashboard that shows only favourable numbers is marketing. The assignment asks for the proof more than the system; the caveats are part of the proof.
