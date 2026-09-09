import { MetricTile, type MetricTileProps } from "@/components/MetricTile";

import { isNum, type Maybe } from "./maybe";

export interface StatTileProps extends Omit<MetricTileProps, "value" | "format"> {
  /** The statistic, which the eval module writes as `null` when undefined on the data. */
  value: Maybe<number>;
  format: (v: number) => string;
}

/** MetricTile that renders an em dash (and skips the CI) when the statistic is missing. */
export function StatTile({ value, format, ci, sub, ...rest }: StatTileProps) {
  const has = isNum(value);
  return (
    <MetricTile
      {...rest}
      value={has ? value : 0}
      format={has ? format : () => "—"}
      ci={has ? ci : undefined}
      sub={has ? sub : <span className="text-faint">not computed for this run</span>}
    />
  );
}
