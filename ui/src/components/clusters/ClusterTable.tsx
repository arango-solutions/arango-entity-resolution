import { useState, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  AlertTriangle,
  Eye,
} from "lucide-react";
import { ScoreBadge } from "../shared/ScoreBadge";
import { cn } from "../../lib/cn";

export interface ClusterRow {
  cluster_id: string;
  size: number;
  representative?: string;
  quality_score: number | null;
  average_similarity: number | null;
  density: number | null;
}

interface ClusterTableProps {
  clusters: ClusterRow[];
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
  onLimitChange: (limit: number) => void;
  collection: string;
}

type SortKey = "cluster_id" | "size" | "quality_score" | "average_similarity" | "density";
type SortDir = "asc" | "desc";

const COLUMNS: { key: SortKey; label: string; sortable: boolean }[] = [
  { key: "cluster_id", label: "Representative Key", sortable: true },
  { key: "size", label: "Size", sortable: true },
  { key: "quality_score", label: "Quality Score", sortable: true },
  { key: "average_similarity", label: "Avg Similarity", sortable: true },
  { key: "density", label: "Density", sortable: true },
];

export function ClusterTable({
  clusters,
  total,
  limit,
  offset,
  onPageChange,
  onLimitChange,
  collection,
}: ClusterTableProps) {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const handleSort = useCallback(
    (key: SortKey) => {
      if (sortKey === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("desc");
      }
    },
    [sortKey],
  );

  const sorted = useMemo(() => {
    if (!sortKey) return clusters;
    return [...clusters].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      const cmp = va < vb ? -1 : va > vb ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [clusters, sortKey, sortDir]);

  const canPrev = offset > 0;
  const canNext = offset + limit < total;
  const showingStart = total === 0 ? 0 : offset + 1;
  const showingEnd = Math.min(offset + limit, total);

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    "px-4 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase",
                    col.sortable &&
                      "cursor-pointer select-none hover:text-gray-700",
                  )}
                  onClick={col.sortable ? () => handleSort(col.key) : undefined}
                >
                  <div className="flex items-center gap-1">
                    {col.label}
                    {col.sortable && (
                      <span className="inline-flex">
                        {sortKey === col.key ? (
                          sortDir === "asc" ? (
                            <ChevronUp className="h-3.5 w-3.5" />
                          ) : (
                            <ChevronDown className="h-3.5 w-3.5" />
                          )
                        ) : (
                          <ChevronsUpDown className="h-3.5 w-3.5 text-gray-300" />
                        )}
                      </span>
                    )}
                  </div>
                </th>
              ))}
              <th className="px-4 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {sorted.length === 0 ? (
              <tr>
                <td
                  colSpan={COLUMNS.length + 1}
                  className="px-4 py-8 text-center text-gray-400"
                >
                  No clusters found
                </td>
              </tr>
            ) : (
              sorted.map((row) => {
                const lowQuality =
                  row.quality_score != null && row.quality_score < 0.55;
                return (
                  <tr
                    key={row.cluster_id}
                    className="cursor-pointer transition-colors hover:bg-gray-50"
                    onClick={() =>
                      navigate(`/clusters/${collection}/${row.cluster_id}`)
                    }
                  >
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-sm text-gray-700">
                      <div className="flex items-center gap-1.5">
                        {lowQuality && (
                          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
                        )}
                        {row.representative ?? row.cluster_id}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                      {row.size}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      {row.quality_score != null ? (
                        <ScoreBadge score={row.quality_score} />
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                      {row.average_similarity != null
                        ? row.average_similarity.toFixed(2)
                        : "—"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                      {row.density != null ? row.density.toFixed(2) : "—"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(
                            `/clusters/${collection}/${row.cluster_id}`,
                          );
                        }}
                        className="inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
                      >
                        <Eye className="h-3.5 w-3.5" />
                        View
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-gray-500">
        <div className="flex items-center gap-2">
          <span>Rows per page:</span>
          <select
            value={limit}
            onChange={(e) => {
              onLimitChange(Number(e.target.value));
              onPageChange(0);
            }}
            className="rounded border border-gray-300 px-1 py-0.5 text-sm"
          >
            {[10, 20, 50].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <span>
            {total === 0
              ? "0 of 0"
              : `${showingStart}–${showingEnd} of ${total}`}
          </span>
          <div className="flex gap-1">
            <button
              disabled={!canPrev}
              onClick={() => onPageChange(Math.max(0, offset - limit))}
              className="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
            >
              Prev
            </button>
            <button
              disabled={!canNext}
              onClick={() => onPageChange(offset + limit)}
              className="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
