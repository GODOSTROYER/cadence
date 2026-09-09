import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { Skeleton } from "@/components/Skeleton";
import { cx } from "@/lib/cx";

export type SortDir = "asc" | "desc";

export interface Column<Row> {
  id: string;
  header: ReactNode;
  cell: (row: Row) => ReactNode;
  /** Enables sorting when provided. */
  sortValue?: (row: Row) => string | number | boolean | null | undefined;
  align?: "left" | "right" | "center";
  width?: string | number;
  /** Mono tabular numerals. */
  mono?: boolean;
  /** Hide below the `sm` breakpoint. */
  hideOnMobile?: boolean;
}

export interface SortState {
  id: string;
  dir: SortDir;
}

export interface DataTableProps<Row> {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  /** Row click / Enter / Space. Rows become focusable when set. */
  onRowClick?: (row: Row) => void;
  selectedKey?: string | null;
  initialSort?: SortState;
  /** Rendered inside the body when there are no rows. */
  empty?: ReactNode;
  /** Visually-hidden caption for screen readers. */
  caption?: string;
  maxHeight?: number | string;
  density?: "compact" | "default";
  loading?: boolean;
  skeletonRows?: number;
  className?: string;
}

function compare(a: unknown, b: unknown): number {
  if (a === b) return 0;
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (typeof a === "boolean" && typeof b === "boolean") return Number(a) - Number(b);
  return String(a).localeCompare(String(b));
}

/** Sortable table with sticky header, mono numerals, hover rows and keyboard row navigation. */
export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  onRowClick,
  selectedKey,
  initialSort,
  empty,
  caption,
  maxHeight,
  density = "default",
  loading = false,
  skeletonRows = 8,
  className,
}: DataTableProps<Row>) {
  const [sort, setSort] = useState<SortState | null>(initialSort ?? null);
  const bodyRef = useRef<HTMLTableSectionElement | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.id === sort.id);
    if (!col?.sortValue) return rows;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => compare(col.sortValue!(a), col.sortValue!(b)) * dir);
  }, [rows, sort, columns]);

  const toggleSort = (col: Column<Row>) => {
    if (!col.sortValue) return;
    setSort((s) => (s?.id === col.id ? (s.dir === "asc" ? { id: col.id, dir: "desc" } : null) : { id: col.id, dir: "asc" }));
  };

  const onRowKey = (e: KeyboardEvent<HTMLTableRowElement>, row: Row, index: number) => {
    if (!onRowClick) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onRowClick(row);
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = index + (e.key === "ArrowDown" ? 1 : -1);
      const tr = bodyRef.current?.querySelectorAll<HTMLTableRowElement>("tr[tabindex]")[next];
      tr?.focus();
    }
  };

  const pad = density === "compact" ? "[&_td]:py-1.5 [&_th]:py-2" : "";

  return (
    <div className={cx("table-wrap", className)} style={maxHeight ? { maxHeight } : undefined}>
      <table className={cx("table", pad)}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr>
            {columns.map((c) => {
              const active = sort?.id === c.id;
              const sortable = Boolean(c.sortValue);
              return (
                <th
                  key={c.id}
                  scope="col"
                  style={c.width ? { width: c.width } : undefined}
                  aria-sort={active ? (sort?.dir === "asc" ? "ascending" : "descending") : sortable ? "none" : undefined}
                  className={cx(c.align === "right" && "text-right", c.align === "center" && "text-center", c.hideOnMobile && "hidden sm:table-cell", sortable && "group")}
                >
                  {sortable ? (
                    <button
                      type="button"
                      onClick={() => toggleSort(c)}
                      className={cx("inline-flex items-center gap-1 hover:text-text", active && "text-text", c.align === "right" && "flex-row-reverse")}
                    >
                      {c.header}
                      <span aria-hidden="true" className={cx("[&>svg]:size-3.5", active ? "text-green" : "text-faint opacity-0 transition-opacity group-hover:opacity-100")}>
                        {active ? (sort?.dir === "asc" ? <ChevronUp /> : <ChevronDown />) : <ChevronsUpDown />}
                      </span>
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody ref={bodyRef}>
          {loading &&
            Array.from({ length: skeletonRows }, (_, i) => (
              <tr key={`sk-${i}`}>
                {columns.map((c) => (
                  <td key={c.id} className={cx(c.hideOnMobile && "hidden sm:table-cell")}>
                    <Skeleton height={13} width={`${55 + ((i * 17 + c.id.length * 7) % 40)}%`} />
                  </td>
                ))}
              </tr>
            ))}
          {!loading && sorted.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="!p-0">
                {empty ?? <p className="px-4 py-10 text-center text-[13px] text-muted">No rows match.</p>}
              </td>
            </tr>
          )}
          {!loading &&
            sorted.map((row, i) => {
              const key = rowKey(row);
              return (
                <tr
                  key={key}
                  tabIndex={onRowClick ? 0 : undefined}
                  aria-selected={selectedKey === key || undefined}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={(e) => onRowKey(e, row, i)}
                  className={cx(onRowClick && "cursor-pointer focus-visible:outline-offset-[-2px]")}
                >
                  {columns.map((c) => (
                    <td
                      key={c.id}
                      className={cx(c.mono && "num", c.align === "right" && "text-right", c.align === "center" && "text-center", c.hideOnMobile && "hidden sm:table-cell")}
                    >
                      {c.cell(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
        </tbody>
      </table>
    </div>
  );
}
