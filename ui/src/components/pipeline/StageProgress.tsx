import { Circle, Loader2, CheckCircle, XCircle } from "lucide-react";
import { cn } from "../../lib/cn";
import { formatStageName } from "../../hooks/usePipelineWs";

interface StageProgressProps {
  name: string;
  status: "waiting" | "running" | "complete" | "error";
  progress?: number;
  result?: Record<string, unknown>;
  startedAt?: string;
  completedAt?: string;
}

function formatResultSummary(
  _name: string,
  result?: Record<string, unknown>,
): string | null {
  if (!result) return null;

  const entries = Object.entries(result);
  if (entries.length === 0) return null;

  const parts: string[] = [];
  for (const [key, value] of entries) {
    if (typeof value === "number") {
      const label = key.replace(/_/g, " ");
      parts.push(`${value.toLocaleString()} ${label}`);
    }
  }
  return parts.join(" · ") || null;
}

function formatElapsed(startedAt?: string, completedAt?: string): string | null {
  if (!startedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  const seconds = (end - start) / 1000;
  if (seconds < 0.1) return null;
  return `${seconds.toFixed(1)}s`;
}

const statusIcons = {
  waiting: Circle,
  running: Loader2,
  complete: CheckCircle,
  error: XCircle,
} as const;

const statusColors = {
  waiting: "text-gray-400",
  running: "text-blue-500",
  complete: "text-green-500",
  error: "text-red-500",
} as const;

export function StageProgress({
  name,
  status,
  progress,
  result,
  startedAt,
  completedAt,
}: StageProgressProps) {
  const Icon = statusIcons[status];
  const elapsed = formatElapsed(startedAt, completedAt);
  const resultSummary = formatResultSummary(name, result);

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-gray-200 bg-white px-4 py-3">
      <div className="flex items-center gap-3">
        <Icon
          className={cn(
            "h-5 w-5 shrink-0",
            statusColors[status],
            status === "running" && "animate-spin",
          )}
        />

        <span className="min-w-[120px] text-sm font-medium text-gray-900">
          {formatStageName(name)}
        </span>

        <div className="flex-1">
          {(status === "running" || status === "complete") &&
            progress != null && (
              <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-300",
                    status === "complete" ? "bg-green-500" : "bg-blue-500",
                  )}
                  style={{ width: `${Math.min(progress * 100, 100)}%` }}
                />
              </div>
            )}
        </div>

        <div className="flex items-center gap-3 text-xs text-gray-500">
          {progress != null && status === "running" && (
            <span>{Math.round(progress * 100)}%</span>
          )}
          {status === "complete" && <span>Done</span>}
          {elapsed && <span>({elapsed})</span>}
        </div>
      </div>

      {resultSummary && status === "complete" && (
        <p className="ml-8 text-xs text-gray-500">{resultSummary}</p>
      )}
    </div>
  );
}
