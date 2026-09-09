import { Fragment } from "react";

import { Tooltip } from "@/components/Tooltip";
import { cx } from "@/lib/cx";
import { pct } from "@/lib/format";
import { intentColor, intentShort } from "@/lib/intents";
import { heatColor } from "@/lib/palette";
import type { IntentId } from "@/lib/types";

export interface ConfusionMatrixProps {
  labels: IntentId[];
  /** `matrix[gold][pred]` counts. */
  matrix: number[][];
  /** Example ids for a (gold, pred) cell, shown in the hover tooltip. */
  examples?: (gold: IntentId, pred: IntentId) => string[] | undefined;
  onCellClick?: (gold: IntentId, pred: IntentId, count: number) => void;
  /** Show row-normalised percentages instead of counts. */
  normalize?: boolean;
  title?: string;
  className?: string;
}

/** Gold × predicted heatmap. Diagonal cells ramp green, errors ramp rose; the grid is a real table. */
export function ConfusionMatrix({ labels, matrix, examples, onCellClick, normalize = false, title, className }: ConfusionMatrixProps) {
  const rowSums = matrix.map((row) => row.reduce((a, b) => a + b, 0));
  const maxDiag = Math.max(1, ...matrix.map((row, i) => row[i] ?? 0));
  const maxErr = Math.max(1, ...matrix.flatMap((row, i) => row.filter((_, j) => j !== i)));
  const total = rowSums.reduce((a, b) => a + b, 0);
  const correct = matrix.reduce((acc, row, i) => acc + (row[i] ?? 0), 0);

  return (
    <div className={cx("min-w-0", className)}>
      {title && <h3 className="t-display-20 mb-3 text-text">{title}</h3>}
      <div className="table-wrap">
        <table className="w-full border-separate border-spacing-0 text-[12px]" aria-label={`Confusion matrix: rows are gold intents, columns are predicted intents. ${correct} of ${total} correct.`}>
          <thead>
            <tr>
              <th scope="col" className="sticky left-0 z-[2] bg-surface px-3 py-2 text-left font-medium text-faint">
                gold ↓ · predicted →
              </th>
              {labels.map((p) => (
                <th key={p} scope="col" className="h-[92px] bg-surface px-0 align-bottom font-normal">
                  <div className="flex h-full items-end justify-center pb-2">
                    <span className="inline-flex origin-bottom-left -rotate-45 items-center gap-1 whitespace-nowrap text-muted" style={{ transform: "rotate(-45deg) translate(6px, 0)" }}>
                      <span aria-hidden="true" className="size-1.5 rounded-full" style={{ background: intentColor(p) }} />
                      {intentShort(p)}
                    </span>
                  </div>
                </th>
              ))}
              <th scope="col" className="bg-surface px-2 pb-2 text-right align-bottom font-normal text-faint">
                n
              </th>
            </tr>
          </thead>
          <tbody>
            {labels.map((g, i) => (
              <tr key={g}>
                <th scope="row" className="sticky left-0 z-[1] bg-surface py-0 pr-3 pl-3 text-left font-normal whitespace-nowrap">
                  <span className="inline-flex items-center gap-2 text-text">
                    <span aria-hidden="true" className="size-1.5 rounded-full" style={{ background: intentColor(g) }} />
                    {intentShort(g)}
                  </span>
                </th>
                {labels.map((p, j) => {
                  const n = matrix[i]?.[j] ?? 0;
                  const diag = i === j;
                  const share = rowSums[i] ? n / (rowSums[i] ?? 1) : 0;
                  const ids = examples?.(g, p) ?? [];
                  const tip = (
                    <span>
                      <span className="t-mono block text-muted">{g} → {p}</span>
                      <span className="block text-text">
                        {n} {n === 1 ? "example" : "examples"} ({pct(share)} of gold {intentShort(g)})
                      </span>
                      {ids.length > 0 && <span className="t-mono mt-1 block text-muted">{ids.slice(0, 4).join(", ")}{ids.length > 4 ? ` +${ids.length - 4}` : ""}</span>}
                    </span>
                  );
                  return (
                    <td key={p} className="p-px">
                      <Tooltip content={tip}>
                        <button
                          type="button"
                          onClick={onCellClick ? () => onCellClick(g, p, n) : undefined}
                          aria-label={`gold ${intentShort(g)}, predicted ${intentShort(p)}: ${n}`}
                          className={cx(
                            "t-mono flex h-8 w-full min-w-9 items-center justify-center rounded-[3px] transition-colors duration-[120ms]",
                            n === 0 ? "text-faint/60" : diag ? "text-text" : "text-text",
                            onCellClick && n > 0 ? "cursor-pointer hover:outline hover:outline-1 hover:outline-border-strong" : "cursor-default",
                          )}
                          style={{ background: heatColor(n, diag ? maxDiag : maxErr, diag ? "diagonal" : "error") }}
                        >
                          {n === 0 ? "·" : normalize ? pct(share) : n}
                        </button>
                      </Tooltip>
                    </td>
                  );
                })}
                <td className="t-mono px-2 text-right text-muted">{rowSums[i]}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" className="sticky left-0 bg-surface px-3 py-2 text-left font-normal text-faint">
                predicted n
              </th>
              {labels.map((_, j) => (
                <Fragment key={j}>
                  <td className="t-mono px-1 py-2 text-center text-muted">{matrix.reduce((acc, row) => acc + (row[j] ?? 0), 0)}</td>
                </Fragment>
              ))}
              <td className="t-mono px-2 py-2 text-right text-text">{total}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="mt-2 text-[12px] text-faint">
        Rows are gold labels, columns are predictions; diagonal (green) is correct, off-diagonal (rose) is the error mass. Hover a cell for examples.
      </p>
    </div>
  );
}
