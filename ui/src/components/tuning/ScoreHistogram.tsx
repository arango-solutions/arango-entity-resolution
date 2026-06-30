import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { ScoreBucket } from "../../api/metrics";

interface ScoreHistogramProps {
  buckets: ScoreBucket[];
  low: number;
  high: number;
}

/**
 * Similarity-score histogram with low/high threshold reference lines. Bars are
 * tinted by the band the bucket falls into: below low = no-match (red), between
 * = review (amber), at/above high = match (green).
 */
export function ScoreHistogram({ buckets, low, high }: ScoreHistogramProps) {
  const data = buckets.map((b) => ({
    label: b.lo.toFixed(2),
    mid: (b.lo + b.hi) / 2,
    count: b.count,
  }));

  function colorFor(mid: number): string {
    if (mid >= high) return "#10b981"; // match
    if (mid >= low) return "#f59e0b"; // review band
    return "#ef4444"; // no-match
  }

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <XAxis dataKey="label" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={44} allowDecimals={false} />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e5e7eb" }}
            formatter={(v: number) => [v, "pairs"]}
            labelFormatter={(l: string) => `score ${l}+`}
          />
          <ReferenceLine x={low.toFixed(2)} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: "low", fontSize: 10, fill: "#b45309" }} />
          <ReferenceLine x={high.toFixed(2)} stroke="#059669" strokeDasharray="3 3" label={{ value: "high", fontSize: 10, fill: "#047857" }} />
          <Bar dataKey="count" radius={[3, 3, 0, 0]} maxBarSize={28}>
            {data.map((d, i) => (
              <Cell key={i} fill={colorFor(d.mid)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
