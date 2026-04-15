const BACKENDS = [
  "auto",
  "python_union_find",
  "python_dfs",
  "python_sparse",
  "aql_graph",
  "gae_wcc",
] as const;

interface ClusteringSectionProps {
  backend: string;
  minClusterSize: number;
  storeResults: boolean;
  onBackendChange: (value: string) => void;
  onMinClusterSizeChange: (value: number) => void;
  onStoreResultsChange: (value: boolean) => void;
}

export function ClusteringSection({
  backend,
  minClusterSize,
  storeResults,
  onBackendChange,
  onMinClusterSizeChange,
  onStoreResultsChange,
}: ClusteringSectionProps) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700">
          Backend
        </label>
        <select
          value={backend}
          onChange={(e) => onBackendChange(e.target.value)}
          className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
        >
          {BACKENDS.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700">
          Min Cluster Size
        </label>
        <input
          type="number"
          value={minClusterSize}
          onChange={(e) =>
            onMinClusterSizeChange(parseInt(e.target.value) || 1)
          }
          min={1}
          className="mt-1 block w-32 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
        />
      </div>

      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={storeResults}
          onChange={(e) => onStoreResultsChange(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
        />
        <span className="text-sm font-medium text-gray-700">
          Store Results
        </span>
      </label>
    </div>
  );
}
