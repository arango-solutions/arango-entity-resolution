import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getThresholds, optimizeThresholds } from "../../api/review";
import { LoadingSpinner } from "../shared/LoadingSpinner";

interface ThresholdBannerProps {
  collection: string;
}

interface ThresholdResponse {
  low_threshold?: number;
  high_threshold?: number;
  low?: number;
  high?: number;
  source?: string;
  sample_count?: number;
}

export function ThresholdBanner({ collection }: ThresholdBannerProps) {
  const [optimizing, setOptimizing] = useState(false);

  const { data, refetch, isLoading } = useQuery({
    queryKey: ["thresholds", collection],
    queryFn: () => getThresholds(collection),
    enabled: !!collection,
  });

  const raw = data as ThresholdResponse | undefined;
  const low = raw?.low_threshold ?? raw?.low ?? 0.55;
  const high = raw?.high_threshold ?? raw?.high ?? 0.8;

  async function handleOptimize() {
    setOptimizing(true);
    try {
      await optimizeThresholds(collection);
      await refetch();
    } finally {
      setOptimizing(false);
    }
  }

  if (isLoading) {
    return (
      <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-4">
        <LoadingSpinner size="sm" />
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-indigo-100 bg-indigo-50 px-5 py-3">
      <div className="space-y-0.5">
        <p className="text-sm font-medium text-indigo-900">
          Current thresholds: Low{" "}
          <span className="font-mono">{low.toFixed(2)}</span> | High{" "}
          <span className="font-mono">{high.toFixed(2)}</span>
        </p>
        <p className="text-xs text-indigo-700">
          Pairs below the low threshold are auto-rejected; above the high
          threshold are auto-accepted. Pairs in between require review.
        </p>
      </div>

      <button
        onClick={handleOptimize}
        disabled={optimizing}
        className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
      >
        {optimizing ? (
          <>
            <LoadingSpinner size="sm" className="text-white" />
            Optimizing…
          </>
        ) : (
          "Optimize Thresholds"
        )}
      </button>
    </div>
  );
}
