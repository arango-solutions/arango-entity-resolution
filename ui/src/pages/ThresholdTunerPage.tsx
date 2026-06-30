import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { SlidersHorizontal, Check, Loader2 } from "lucide-react";
import { useSelectedCollection } from "../contexts/CollectionContext";
import { useScoreDistribution, useBoundaryPairs } from "../hooks/useMetrics";
import { applyThreshold } from "../api/metrics";
import { ScoreHistogram } from "../components/tuning/ScoreHistogram";
import { PairComparison } from "../components/review/PairComparison";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import { EmptyState } from "../components/shared/EmptyState";

export function ThresholdTunerPage() {
  const { selectedCollection } = useSelectedCollection();
  const [low, setLow] = useState(0.55);
  const [high, setHigh] = useState(0.8);
  const [applied, setApplied] = useState(false);

  const dist = useScoreDistribution(selectedCollection);
  const boundary = useBoundaryPairs(selectedCollection, high, 0.05, 6);

  const buckets = useMemo(() => dist.data?.buckets ?? [], [dist.data]);

  const deltas = useMemo(() => {
    let match = 0,
      review = 0,
      noMatch = 0;
    for (const b of buckets) {
      const mid = (b.lo + b.hi) / 2;
      if (mid >= high) match += b.count;
      else if (mid >= low) review += b.count;
      else noMatch += b.count;
    }
    return { match, review, noMatch, total: match + review + noMatch };
  }, [buckets, low, high]);

  const mutation = useMutation({
    mutationFn: () =>
      applyThreshold(selectedCollection!, {
        low_threshold: low,
        high_threshold: high,
      }),
    onSuccess: () => {
      setApplied(true);
      setTimeout(() => setApplied(false), 2500);
    },
  });

  function onLow(v: number) {
    setLow(Math.min(v, high));
  }
  function onHigh(v: number) {
    setHigh(Math.max(v, low));
  }

  if (!selectedCollection) {
    return (
      <EmptyState
        icon={SlidersHorizontal}
        title="No collection selected"
        description="Select a collection from the sidebar to tune its match thresholds."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">Threshold Tuner</h1>
        <p className="mt-1 text-sm text-gray-500">
          Set the low/high decision bands against the live score distribution.
          Pairs at or above <span className="font-medium text-green-600">high</span> auto-match,
          below <span className="font-medium text-red-600">low</span> auto-reject, and the
          <span className="font-medium text-amber-600"> band</span> between is routed to review.
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        {dist.isLoading ? (
          <div className="py-16">
            <LoadingSpinner size="lg" />
          </div>
        ) : buckets.length === 0 ? (
          <EmptyState
            icon={SlidersHorizontal}
            title="No similarity edges yet"
            description="Run the pipeline for this collection to generate scored pairs to tune against."
          />
        ) : (
          <>
            <ScoreHistogram buckets={buckets} low={low} high={high} />

            <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2">
              <label className="block">
                <span className="text-sm font-medium text-amber-700">
                  Low (review floor): {low.toFixed(2)}
                </span>
                <input
                  type="range" min={0} max={1} step={0.01} value={low}
                  onChange={(e) => onLow(parseFloat(e.target.value))}
                  className="mt-2 w-full accent-amber-500"
                />
              </label>
              <label className="block">
                <span className="text-sm font-medium text-green-700">
                  High (auto-match): {high.toFixed(2)}
                </span>
                <input
                  type="range" min={0} max={1} step={0.01} value={high}
                  onChange={(e) => onHigh(parseFloat(e.target.value))}
                  className="mt-2 w-full accent-green-600"
                />
              </label>
            </div>

            <div className="mt-6 grid grid-cols-3 gap-4">
              <Stat label="Auto-match" value={deltas.match} tone="green" />
              <Stat label="Needs review" value={deltas.review} tone="amber" />
              <Stat label="Auto-reject" value={deltas.noMatch} tone="red" />
            </div>

            <div className="mt-6 flex items-center gap-3">
              <button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending}
                className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
              >
                {mutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : applied ? (
                  <Check className="h-4 w-4" />
                ) : null}
                {applied ? "Applied" : "Apply thresholds"}
              </button>
              {mutation.isError && (
                <span className="text-sm text-red-600">
                  {mutation.error instanceof Error ? mutation.error.message : "Apply failed"}
                </span>
              )}
            </div>
          </>
        )}
      </div>

      {buckets.length > 0 && (
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-gray-900">
            Boundary pairs near the high handle ({high.toFixed(2)})
          </h2>
          <p className="mt-1 mb-4 text-xs text-gray-500">
            What the match cutoff currently captures — review these to sanity-check the threshold.
          </p>
          {boundary.isLoading ? (
            <LoadingSpinner />
          ) : (boundary.data?.pairs.length ?? 0) === 0 ? (
            <p className="py-4 text-sm text-gray-400">No pairs within ±0.05 of {high.toFixed(2)}.</p>
          ) : (
            <div className="space-y-4">
              {boundary.data!.pairs.map((p, i) => (
                <PairComparison
                  key={`${p.key_a}-${p.key_b}`}
                  collection={selectedCollection}
                  index={i}
                  pair={{ key_a: p.key_a, key_b: p.key_b, score: p.score, status: "boundary" }}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: "green" | "amber" | "red" }) {
  const tones: Record<string, string> = {
    green: "text-green-700 bg-green-50",
    amber: "text-amber-700 bg-amber-50",
    red: "text-red-700 bg-red-50",
  };
  return (
    <div className={`rounded-md p-3 ${tones[tone]}`}>
      <div className="text-xs">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value.toLocaleString()}</div>
    </div>
  );
}
