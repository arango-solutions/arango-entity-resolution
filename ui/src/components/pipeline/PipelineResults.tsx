import { Link } from "react-router-dom";
import { ArrowRight, Download, Network, ClipboardCheck } from "lucide-react";

interface PipelineResultsProps {
  summary: Record<string, unknown>;
  collection: string;
}

function getNumeric(obj: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const val = obj[key];
    if (typeof val === "number") return val;
  }
  for (const key of keys) {
    const val = obj[key];
    if (typeof val === "object" && val !== null) {
      const nested = val as Record<string, unknown>;
      for (const k of keys) {
        if (typeof nested[k] === "number") return nested[k] as number;
      }
    }
  }
  return null;
}

export function PipelineResults({ summary, collection: _collection }: PipelineResultsProps) {
  const result =
    typeof summary["result"] === "object" && summary["result"] !== null
      ? (summary["result"] as Record<string, unknown>)
      : summary;

  const runtime = getNumeric(summary, "total_runtime_seconds");
  const clusters = getNumeric(
    result,
    "clusters_found",
    "cluster_count",
    "clusters",
  );
  const edges = getNumeric(result, "edges_created", "edge_count", "edges");
  const candidates = getNumeric(
    result,
    "candidates_found",
    "candidate_count",
    "candidates",
  );

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-green-200 bg-green-50 p-4">
        <h3 className="text-sm font-semibold text-green-800">
          Pipeline Complete
        </h3>
        {runtime != null && (
          <p className="mt-1 text-sm text-green-700">
            Finished in {runtime.toFixed(1)} seconds
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {candidates != null && (
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <p className="text-xs font-medium text-gray-500">Candidates</p>
            <p className="mt-1 text-2xl font-semibold text-gray-900">
              {candidates.toLocaleString()}
            </p>
          </div>
        )}
        {edges != null && (
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <p className="text-xs font-medium text-gray-500">
              Similarity Edges
            </p>
            <p className="mt-1 text-2xl font-semibold text-gray-900">
              {edges.toLocaleString()}
            </p>
          </div>
        )}
        {clusters != null && (
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <p className="text-xs font-medium text-gray-500">Clusters Found</p>
            <p className="mt-1 text-2xl font-semibold text-gray-900">
              {clusters.toLocaleString()}
            </p>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-3">
        {clusters != null && (
          <Link
            to="/clusters"
            className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50"
          >
            <Network className="h-4 w-4" />
            View {clusters.toLocaleString()} clusters
            <ArrowRight className="h-3 w-3" />
          </Link>
        )}
        <Link
          to="/review"
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50"
        >
          <ClipboardCheck className="h-4 w-4" />
          Review pairs
          <ArrowRight className="h-3 w-3" />
        </Link>
        <Link
          to="/export"
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50"
        >
          <Download className="h-4 w-4" />
          Export results
        </Link>
      </div>

      {Object.keys(result).length > 0 && (
        <details className="rounded-lg border border-gray-200 bg-white">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-gray-700">
            Raw results
          </summary>
          <pre className="overflow-x-auto border-t border-gray-200 px-4 py-3 text-xs text-gray-600">
            {JSON.stringify(result, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
