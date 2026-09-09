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
          <strong>Sixty pairs, twenty per system.</strong> A stratified subset of test tweets, each paired with a reply from one of the three judged
          systems (the agent, the nearest-neighbour historical reply, the most common template). You see the tweet, the reply and the retrieved
          evidence; which system wrote the reply is hidden and never shown.
        </li>
        <li>
          <strong>Same rubric as the LLM judge.</strong> Five 1–5 scores (grounded, resolves, tone, safe, overall), three flags, and a verdict: ship
          means post as-is (overall ≥ 4, no flags), edit means a human fixes it first, reject means do not send.
        </li>
        <li>
          <strong>What it feeds.</strong> Your ratings are appended to <code>data/golden/human_ratings.jsonl</code>; the evaluation then reports
          quadratic-weighted Cohen&rsquo;s κ, Spearman ρ, exact and within-1 agreement between you and the judge on overall, plus κ per dimension.
          That is the only check on whether the judge&rsquo;s numbers mean anything.
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
