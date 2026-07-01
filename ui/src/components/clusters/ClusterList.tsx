import { useState } from "react";
import { Network, GitMerge, X } from "lucide-react";
import { useClusters } from "../../hooks/useClusters";
import { useMergeClusters } from "../../hooks/useCuration";
import { type ClusterListParams } from "../../api/clusters";
import { ClusterFilters } from "./ClusterFilters";
import { ClusterTable, type ClusterRow } from "./ClusterTable";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { EmptyState } from "../shared/EmptyState";

interface ApiParams extends ClusterListParams {
  limit?: number;
  offset?: number;
}

interface ApiResponse {
  clusters: ClusterRow[];
  total: number;
  offset: number;
  limit: number;
}

interface ClusterListProps {
  collection: string;
}

export function ClusterList({ collection }: ClusterListProps) {
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(20);
  const [minSize, setMinSize] = useState(2);
  const [search, setSearch] = useState("");
  const [mergeMode, setMergeMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const mergeMut = useMergeClusters(collection);

  const toggleSelect = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  const exitMergeMode = () => {
    setMergeMode(false);
    setSelected(new Set());
  };

  const doMerge = () => {
    const keys = [...selected];
    if (keys.length < 2) return;
    if (!window.confirm(`Merge ${keys.length} clusters into one?`)) return;
    mergeMut.mutate(keys, { onSuccess: exitMergeMode });
  };

  const params: ApiParams = {
    min_size: minSize,
    limit,
    offset,
    ...(search ? { search } : {}),
  };

  const { data: rawData, isLoading, error } = useClusters(collection, params);
  const data = rawData as unknown as ApiResponse | undefined;

  const handleMinSizeChange = (size: number) => {
    setMinSize(size);
    setOffset(0);
  };

  const handleSearchChange = (value: string) => {
    setSearch(value);
    setOffset(0);
  };

  if (error) {
    return (
      <EmptyState
        icon={Network}
        title="Error loading clusters"
        description={
          error instanceof Error ? error.message : "An error occurred"
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <ClusterFilters
          minSize={minSize}
          onMinSizeChange={handleMinSizeChange}
          search={search}
          onSearchChange={handleSearchChange}
        />
        {mergeMode ? (
          <div className="flex items-center gap-2">
            <button
              onClick={doMerge}
              disabled={selected.size < 2 || mergeMut.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
            >
              <GitMerge className="h-3.5 w-3.5" />
              Merge {selected.size > 0 ? `(${selected.size})` : ""}
            </button>
            <button
              onClick={exitMergeMode}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
            >
              <X className="h-3.5 w-3.5" />
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => setMergeMode(true)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
          >
            <GitMerge className="h-3.5 w-3.5" />
            Merge clusters
          </button>
        )}
      </div>

      {mergeMut.isError && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {mergeMut.error instanceof Error ? mergeMut.error.message : "Merge failed"}
        </div>
      )}

      {isLoading ? (
        <LoadingSpinner className="py-12" />
      ) : (
        <ClusterTable
          clusters={data?.clusters ?? []}
          total={data?.total ?? 0}
          limit={limit}
          offset={offset}
          onPageChange={setOffset}
          onLimitChange={setLimit}
          collection={collection}
          selectedKeys={mergeMode ? selected : undefined}
          onToggleSelect={mergeMode ? toggleSelect : undefined}
        />
      )}
    </div>
  );
}
