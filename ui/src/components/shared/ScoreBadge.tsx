import { cn } from "../../lib/cn";

interface ScoreBadgeProps {
  score: number;
  className?: string;
}

export function ScoreBadge({ score, className }: ScoreBadgeProps) {
  const variant =
    score >= 0.8
      ? "bg-green-100 text-green-800"
      : score >= 0.55
        ? "bg-amber-100 text-amber-800"
        : "bg-red-100 text-red-800";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variant,
        className,
      )}
    >
      {score.toFixed(2)}
    </span>
  );
}
