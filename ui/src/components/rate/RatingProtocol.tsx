import { Callout } from "@/components/Callout";

export interface RatingProtocolProps {
  /** Static builds cannot post ratings; the last bullet says how to get a live server. */
  mode: "static" | "live";
  className?: string;
}

/** The blind-rating protocol (CONTRACT §13), written for the person about to do the rating. */
export function RatingProtocol({ mode, className }: RatingProtocolProps) {
  return (
    <Callout tone="sky" eyebrow="protocol" title="Blind, one reply at a time" className={className}>
      <ul>
        <li>
          <strong>Matched messages across systems.</strong> The revised queue uses twenty messages and both the agent and keyword baseline replies: forty ratings per reviewer.
          The historical fallback has three systems. You see the tweet, the reply and the retrieved
          evidence; which system wrote the reply is hidden and never shown.
        </li>
        <li>
          <strong>Five scores and a verdict.</strong> Five 1–5 scores (grounded, resolves, tone, safe, overall), three flags, and a verdict: ship
          means post as-is (overall ≥ 4, no flags), edit means a human fixes it first, reject means do not send.
        </li>
        <li>
          <strong>What it feeds.</strong> Your ratings are appended to <code>data/golden/human_ratings.jsonl</code>; the evaluation then reports
          quadratic-weighted Cohen&rsquo;s κ, Spearman ρ, exact and within-1 agreement. Run the review-study script with <code>--api-ratings</code> to compare your ratings with both judge orders.
          Your reviewer name and the exact reply identity are saved with each rating. A holding reply is a handoff, not a resolution.
        </li>
        {mode === "static" ? (
          <li>
            <strong>Disabled in this build.</strong> Static builds read exported results and cannot post. Start the API with <code>make serve</code>{" "}
            and open <code>/rate</code> there to rate for real.
          </li>
        ) : (
          <li>
            <strong>Keyboard.</strong> Digits 1–5 score the focused dimension and move on; Tab walks the form; S / E / R pick the verdict; ⌘ or Ctrl +
            Enter submits and loads the next pair. A rating cannot be undone once saved, so read the evidence first.
          </li>
        )}
      </ul>
    </Callout>
  );
}
