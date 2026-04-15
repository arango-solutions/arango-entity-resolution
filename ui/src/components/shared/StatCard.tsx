import { type LucideIcon, TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "../../lib/cn";

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  trend?: { value: number; label: string };
  accent?: "indigo" | "green" | "amber" | "red";
}

const accentColors = {
  indigo: "text-indigo-600 bg-indigo-50",
  green: "text-green-600 bg-green-50",
  amber: "text-amber-600 bg-amber-50",
  red: "text-red-600 bg-red-50",
};

export function StatCard({
  label,
  value,
  icon: Icon,
  trend,
  accent = "indigo",
}: StatCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-gray-500">{label}</p>
        {Icon && (
          <div className={cn("rounded-md p-2", accentColors[accent])}>
            <Icon className="h-4 w-4" />
          </div>
        )}
      </div>
      <p className="mt-2 text-3xl font-semibold tracking-tight text-gray-900">
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
      {trend && (
        <div className="mt-2 flex items-center gap-1 text-xs">
          {trend.value >= 0 ? (
            <TrendingUp className="h-3 w-3 text-green-500" />
          ) : (
            <TrendingDown className="h-3 w-3 text-red-500" />
          )}
          <span
            className={trend.value >= 0 ? "text-green-600" : "text-red-600"}
          >
            {trend.value > 0 ? "+" : ""}
            {trend.value}%
          </span>
          <span className="text-gray-400">{trend.label}</span>
        </div>
      )}
    </div>
  );
}
