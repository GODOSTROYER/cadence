/** Current interpretation of immutable historical results; never rewrite the archived scores. */
export const HISTORICAL_CAVEATS = [
  "Both annotation passes were AI-produced. Their agreement does not estimate or bound human agreement. Human validation is unavailable.",
  "These 200 test examples were inspected across three runs. They now form a regression set, not an untouched holdout. The separate 200-example AI-reviewed benchmark has not completed inference.",
  "The 0.9 confidence threshold achieved 0.85 recall on the 50-example development set, missing the 0.9 target; the selector used its F2 fallback. Test recall and auto-handle coverage must be read together.",
  "The original zero-shot baseline changes prompt and policy as well as retrieval. It is not a controlled retrieval ablation. New paired development experiments found no classification gain; draft-quality evidence remains exploratory.",
  "The agent and judge are from the same model family. No judge–human agreement has been measured. New development judging agreed across candidate order on only 70% of 20 pairs.",
  "Citation membership does not prove that a reply follows from relevant evidence. Most conversations date to 2017; they do not establish current policy or incident status. Own-thread exclusion alone did not eliminate near-duplicate leakage.",
  "Offline reproduction recalculates recorded results and verifies receipts. It does not execute the revised agent or measure live endpoint latency. Gemini quotas are per project, not per API key.",
];
