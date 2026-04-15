import { useState } from "react";
import { Network } from "lucide-react";
import { useClusters } from "../../hooks/useClusters";
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
      <ClusterFilters
        minSize={minSize}
        onMinSizeChange={handleMinSizeChange}
        search={search}
        onSearchChange={handleSearchChange}
      />

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
        />
      )}
    </div>
  );
}
