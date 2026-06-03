import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useClusterStats } from "../../hooks/useClusters";

interface DistributionChartProps {
  collection: string;
}

// Stable display order for the cluster-size buckets produced by the backend.
const BUCKET_ORDER = ["2", "3", "4", "5", "6-10", "11-20", "21+"];

export function DistributionChart({ collection }: DistributionChartProps) {
  const { data, isLoading } = useClusterStats(collection);

  const distribution = data?.size_distribution ?? {};
  const sizeData = BUCKET_ORDER.filter((b) => b in distribution).map((b) => ({
    range: b,
    count: distribution[b] ?? 0,
  }));

  const summary: Array<{ label: string; value: string }> = [
    { label: "Total clusters", value: fmt(data?.total_clusters) },
    { label: "Total members", value: fmt(data?.total_members) },
    { label: "Avg size", value: fmt(data?.avg_size, 1) },
    { label: "Max size", value: fmt(data?.max_size) },
    { label: "Avg quality", value: fmt(data?.avg_quality, 2) },
  ];

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="mb-4 text-sm font-medium text-gray-700">
          Cluster Size Distribution
        </h3>
        <div className="h-48">
          {isLoading ? (
            <div className="flex h-full items-center justify-center text-xs text-gray-400">
              Loading…
            </div>
          ) : sizeData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-xs text-gray-400">
              No clusters yet — run a pipeline to populate this chart.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sizeData}>
                <XAxis
                  dataKey="range"
                  tick={{ fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  width={40}
                  allowDecimals={false}
                />
                <Tooltip
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: "1px solid #e5e7eb",
                  }}
                />
                <Bar
                  dataKey="count"
                  fill="#6366f1"
                  radius={[4, 4, 0, 0]}
                  maxBarSize={32}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="mb-4 text-sm font-medium text-gray-700">
          Cluster Summary
        </h3>
        <dl className="grid grid-cols-2 gap-4">
          {summary.map((s) => (
            <div key={s.label} className="rounded-md bg-gray-50 p-3">
              <dt className="text-xs text-gray-500">{s.label}</dt>
              <dd className="mt-1 text-lg font-semibold text-gray-900">
                {s.value}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

function fmt(value: number | undefined, decimals = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return decimals > 0
    ? value.toFixed(decimals)
    : Math.round(value).toLocaleString();
}
