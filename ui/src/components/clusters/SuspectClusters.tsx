import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { useSuspectClusters } from "../../hooks/useCuration";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { EmptyState } from "../shared/EmptyState";

const REASON_LABELS: Record<string, string> = {
  no_intra_edges: "No internal edges",
  low_coherence: "Low coherence",
  bridge_no_clean_split: "Weak bridge",
};

export function SuspectClusters({ collection }: { collection: string }) {
  const { data, isLoading, error } = useSuspectClusters(collection);

  if (isLoading) return <LoadingSpinner className="py-12" />;
  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Error loading suspect clusters"
        description={error instanceof Error ? error.message : "An error occurred"}
      />
    );
  }
  const clusters = data?.clusters ?? [];
  if (clusters.length === 0) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="No suspect clusters"
        description="The cluster repair queue is empty. Run repair analysis to flag low-quality clusters."
      />
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            {["Cluster", "Reason", "Mean edge score", "Members", ""].map((h) => (
              <th key={h} className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {clusters.map((c) => (
            <tr key={c.cluster_key} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-mono text-gray-700">{c.cluster_key}</td>
              <td className="px-4 py-3">
                <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
                  <AlertTriangle className="h-3 w-3" />
                  {REASON_LABELS[c.reason] ?? c.reason}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-700">
                {c.mean_edge_score != null ? c.mean_edge_score.toFixed(2) : "—"}
              </td>
              <td className="px-4 py-3 text-gray-500">{c.members?.length ?? 0}</td>
              <td className="px-4 py-3">
                <Link
                  to={`/clusters/${collection}/${c.cluster_key}`}
                  className="rounded-md px-2.5 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50"
                >
                  Inspect
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
