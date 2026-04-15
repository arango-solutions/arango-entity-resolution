import { Link } from "react-router-dom";
import { History } from "lucide-react";
import { Badge } from "../shared/Badge";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { EmptyState } from "../shared/EmptyState";
import { usePipelineHistory } from "../../hooks/usePipeline";

function formatRelativeTime(timestamp: string | number | undefined): string {
  if (!timestamp) return "—";
  const ms =
    typeof timestamp === "number"
      ? timestamp > 1e12
        ? timestamp
        : timestamp * 1000
      : new Date(timestamp).getTime();

  const diff = Date.now() - ms;
  if (diff < 0) return "just now";
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function statusVariant(status: string) {
  switch (status) {
    case "completed":
      return "success" as const;
    case "running":
      return "info" as const;
    case "failed":
      return "danger" as const;
    default:
      return "default" as const;
  }
}

function formatDuration(
  startedAt: string | number | undefined,
  completedAt: string | number | undefined,
): string {
  if (!startedAt) return "—";
  const start =
    typeof startedAt === "number"
      ? startedAt > 1e12
        ? startedAt
        : startedAt * 1000
      : new Date(startedAt).getTime();

  if (!completedAt) return "running...";
  const end =
    typeof completedAt === "number"
      ? completedAt > 1e12
        ? completedAt
        : completedAt * 1000
      : new Date(completedAt).getTime();

  const seconds = (end - start) / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

interface PipelineHistoryProps {
  limit?: number;
}

export function PipelineHistory({ limit = 5 }: PipelineHistoryProps) {
  const { data, isLoading, error } = usePipelineHistory();

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  if (error) {
    return (
      <p className="py-4 text-center text-sm text-red-500">
        Failed to load pipeline history
      </p>
    );
  }

  const runs = Array.isArray(data)
    ? data
    : (data as unknown as { runs?: unknown[] } | undefined)?.runs ?? [];
  const display = runs.slice(0, limit);

  if (display.length === 0) {
    return (
      <EmptyState
        icon={History}
        title="No pipeline runs yet"
        description="Run your first pipeline to see history here."
      >
        <Link
          to="/pipeline"
          className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:text-indigo-700"
        >
          Run Pipeline →
        </Link>
      </EmptyState>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
              Time
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
              Status
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
              Clusters
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
              Duration
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {display.map((run, i) => {
            const r = run as Record<string, unknown>;
            const key = (r["_key"] as string | undefined) ?? (r["run_id"] as string | undefined) ?? String(i);
            const status = (r["status"] as string | undefined) ?? "unknown";
            const clusters = r["clusters_found"] ?? r["cluster_count"];
            const result = r["result"] as Record<string, unknown> | undefined;
            const clustersFromResult =
              clusters ??
              (result
                ? (result["clusters_found"] ??
                  result["cluster_count"])
                : undefined);

            return (
              <tr key={key} className="hover:bg-gray-50">
                <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                  {formatRelativeTime(r["started_at"] as string | number | undefined)}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <Badge variant={statusVariant(status)}>{status}</Badge>
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                  {typeof clustersFromResult === "number"
                    ? clustersFromResult.toLocaleString()
                    : "—"}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                  {formatDuration(
                    r["started_at"] as string | number | undefined,
                    r["completed_at"] as string | number | undefined,
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
