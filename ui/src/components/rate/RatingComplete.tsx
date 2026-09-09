import { CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { int } from "@/lib/format";

export interface RatingCompleteProps {
  total: number;
}

/** Shown when the blind queue is empty: everything is rated. */
export function RatingComplete({ total }: RatingCompleteProps) {
  return (
    <EmptyState
      icon={<CheckCircle2 />}
      title="Every reply is rated"
      description={
        <>
          All {int(total)} blind ratings are saved to <code className="t-mono text-text">data/golden/human_ratings.jsonl</code>. Run{" "}
          <code className="t-mono text-text">make eval</code> to refresh the judge-agreement numbers, then compare yourself with the judge.
        </>
      }
      action={
        <Link to="/eval" className="btn">
          Open judge agreement
        </Link>
      }
    />
  );
}
