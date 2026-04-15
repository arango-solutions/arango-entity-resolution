import { useState, useMemo } from "react";
import { ClipboardCheck, ChevronLeft, ChevronRight } from "lucide-react";
import { useReviewQueue, useReviewStats } from "../../hooks/useReview";
import { type ReviewFilters as ReviewFiltersType } from "../../api/review";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { EmptyState } from "../shared/EmptyState";
import { ReviewFilters } from "./ReviewFilters";
import { PairComparison } from "./PairComparison";

interface ReviewQueueProps {
  collection: string;
}

const PAGE_SIZE = 10;

interface RawVerdict {
  key_a: string;
  key_b: string;
  score: number;
  decision?: string;
  status?: string;
  source?: string;
  llm_verdict?: string;
  llm_confidence?: number;
  confidence?: number;
  field_scores?: Record<string, number>;
}

interface QueueRawResponse {
  pairs?: RawVerdict[];
  verdicts?: RawVerdict[];
  items?: RawVerdict[];
  total?: number;
  page?: number;
  page_size?: number;
  offset?: number;
  limit?: number;
}

export function ReviewQueue({ collection }: ReviewQueueProps) {
  const [status, setStatus] = useState("");
  const [minScore, setMinScore] = useState("");
  const [maxScore, setMaxScore] = useState("");
  const [source, setSource] = useState("");
  const [page, setPage] = useState(0);

  const filters = useMemo(() => {
    const f: Record<string, string | number> = {};
    if (status) f.status = status;
    if (minScore) f.min_score = parseFloat(minScore);
    if (maxScore) f.max_score = parseFloat(maxScore);
    if (source) f.source = source;
    f.offset = page * PAGE_SIZE;
    f.limit = PAGE_SIZE;
    return f as unknown as ReviewFiltersType;
  }, [status, minScore, maxScore, source, page]);

  const { data, isLoading, isError } = useReviewQueue(collection, filters);

  const statsQuery = useReviewStats(collection);

  const raw = data as QueueRawResponse | undefined;
  const items = raw?.pairs ?? raw?.verdicts ?? raw?.items ?? [];
  const total = raw?.total ?? 0;

  const pairs = items.map((v) => ({
    key_a: v.key_a,
    key_b: v.key_b,
    score: v.score ?? 0,
    status: v.status ?? v.decision ?? "pending",
    llm_verdict: v.llm_verdict,
    llm_confidence: v.llm_confidence ?? v.confidence,
  }));

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const statsRaw = statsQuery.data as {
    pending?: number;
    resolved?: number;
    total?: number;
    by_decision?: { decision: string; count: number }[];
  } | undefined;

  const pendingCount = statsRaw?.pending ?? statsRaw?.by_decision
    ?.filter((d) => d.decision !== "match" && d.decision !== "no_match")
    .reduce((s, d) => s + d.count, 0) ?? 0;

  const resolvedCount = statsRaw?.resolved ?? statsRaw?.by_decision
    ?.filter((d) => d.decision === "match" || d.decision === "no_match")
    .reduce((s, d) => s + d.count, 0) ?? 0;

  function handleFilterChange() {
    setPage(0);
  }

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <ReviewFilters
          status={status}
          onStatusChange={(v) => { setStatus(v); handleFilterChange(); }}
          minScore={minScore}
          onMinScoreChange={(v) => { setMinScore(v); handleFilterChange(); }}
          maxScore={maxScore}
          onMaxScoreChange={(v) => { setMaxScore(v); handleFilterChange(); }}
          source={source}
          onSourceChange={(v) => { setSource(v); handleFilterChange(); }}
        />
        <div className="text-sm text-gray-500 whitespace-nowrap">
          <span className="font-medium text-indigo-600">{pendingCount}</span>{" "}
          pending |{" "}
          <span className="font-medium text-green-600">{resolvedCount}</span>{" "}
          resolved
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="py-16">
          <LoadingSpinner size="lg" />
        </div>
      ) : isError ? (
        <EmptyState
          icon={ClipboardCheck}
          title="Failed to load review queue"
          description="Could not fetch pairs. Check that the collection has been processed."
        />
      ) : pairs.length === 0 ? (
        <EmptyState
          icon={ClipboardCheck}
          title="No pairs to review"
          description="There are no pairs matching the current filters. Adjust filters or run the pipeline to generate new candidates."
        />
      ) : (
        <>
          <div className="space-y-4">
            {pairs.map((p, i) => (
              <PairComparison
                key={`${p.key_a}-${p.key_b}`}
                pair={p}
                collection={collection}
                index={page * PAGE_SIZE + i}
              />
            ))}
          </div>

          {/* Pagination */}
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm">
              <span className="text-sm text-gray-500">
                Showing {page * PAGE_SIZE + 1}–
                {Math.min((page + 1) * PAGE_SIZE, total)} of {total}
              </span>
              <div className="flex gap-1">
                <button
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                  className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" />
                  Prev
                </button>
                <button
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage((p) => p + 1)}
                  className="inline-flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-40"
                >
                  Next
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
