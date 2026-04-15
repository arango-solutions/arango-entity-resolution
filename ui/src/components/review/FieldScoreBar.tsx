import { cn } from "../../lib/cn";

interface FieldScoreBarProps {
  fieldName: string;
  score: number;
}

function scoreColor(score: number): string {
  if (score >= 0.8) return "bg-green-500";
  if (score >= 0.55) return "bg-amber-500";
  return "bg-red-500";
}

export function FieldScoreBar({ fieldName, score }: FieldScoreBarProps) {
  const pct = Math.max(0, Math.min(100, score * 100));

  return (
    <div className="flex items-center gap-3">
      <span className="w-24 shrink-0 text-xs font-medium text-gray-600 truncate">
        {fieldName}
      </span>
      <div className="relative h-5 flex-1 rounded-full bg-gray-100">
        <div
          className={cn("h-full rounded-full transition-all", scoreColor(score))}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-10 shrink-0 text-right text-xs font-mono tabular-nums text-gray-700">
        {score.toFixed(2)}
      </span>
    </div>
  );
}
