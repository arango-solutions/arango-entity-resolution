import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface DistributionChartProps {
  collection: string;
}

const clusterSizeData = [
  { range: "2", count: 320 },
  { range: "3", count: 210 },
  { range: "4", count: 145 },
  { range: "5", count: 98 },
  { range: "6-10", count: 72 },
  { range: "11-20", count: 28 },
  { range: "21+", count: 12 },
];

const similarityScoreData = [
  { range: "0.5-0.55", count: 45 },
  { range: "0.55-0.6", count: 89 },
  { range: "0.6-0.65", count: 156 },
  { range: "0.65-0.7", count: 234 },
  { range: "0.7-0.75", count: 312 },
  { range: "0.75-0.8", count: 287 },
  { range: "0.8-0.85", count: 198 },
  { range: "0.85-0.9", count: 143 },
  { range: "0.9-0.95", count: 89 },
  { range: "0.95-1.0", count: 34 },
];

export function DistributionChart({ collection: _collection }: DistributionChartProps) {
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="mb-1 text-sm font-medium text-gray-700">
          Cluster Size Distribution
        </h3>
        <p className="mb-4 text-xs text-gray-400">
          Sample data — connect a real endpoint for live stats
        </p>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={clusterSizeData}>
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
        </div>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="mb-1 text-sm font-medium text-gray-700">
          Similarity Score Distribution
        </h3>
        <p className="mb-4 text-xs text-gray-400">
          Sample data — connect a real endpoint for live stats
        </p>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={similarityScoreData}>
              <XAxis
                dataKey="range"
                tick={{ fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                angle={-30}
                textAnchor="end"
                height={50}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={40}
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
                fill="#10b981"
                radius={[4, 4, 0, 0]}
                maxBarSize={28}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
