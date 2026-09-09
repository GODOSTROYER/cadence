import type { ChipTone } from "@/components/Chip";
import type { Sentiment, Verdict } from "@/lib/types";

/** Chip tone for a sentiment label: anger rose, frustration amber, praise green. */
export function sentimentTone(sentiment: Sentiment): ChipTone {
  switch (sentiment) {
    case "angry":
      return "rose";
    case "frustrated":
      return "amber";
    case "positive":
      return "green";
    default:
      return "neutral";
  }
}

/** Chip tone for a judge verdict. */
export function verdictTone(verdict: Verdict): ChipTone {
  return verdict === "ship" ? "green" : verdict === "edit" ? "amber" : "rose";
}
