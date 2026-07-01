import { useState, useMemo, useEffect } from "react";
import {
  ClipboardCheck,
  ChevronLeft,
  ChevronRight,
  Check,
  X,
  Download,
  HelpCircle,
} from "lucide-react";
import { useReviewQueue, useReviewStats, useBatchVerdict } from "../../hooks/useReview";
import {
  reviewCsvUrl,
  type ReviewFilters as ReviewFiltersType,
} from "../../api/review";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { EmptyState } from "../shared/EmptyState";
import { ReviewFilters } from "./ReviewFilters";
import { PairComparison } from "./PairComparison";
import { ShortcutsModal } from "./ShortcutsModal";

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
  offset?: number;
  limit?: number;
}

const pairId = (a: string, b: string) => `${a}::${b}`;

export function ReviewQueue({ collection }: ReviewQueueProps) {
  const [status, setStatus] = useState("");
  const [minScore, setMinScore] = useState("");
  const [maxScore, setMaxScore] = useState("");
  const [source, setSource] = useState("");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showShortcuts, setShowShortcuts] = useState(false);

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
  const batchMut = useBatchVerdict();

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

  // Preserve pagination across filter changes, but clamp if now out of range.
  useEffect(() => {
    if (page > 0 && page > totalPages - 1) setPage(totalPages - 1);
  }, [totalPages, page]);

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

  const toggleSelect = (a: string, b: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      const id = pairId(a, b);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const selectAllVisible = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      const allSelected = pairs.every((p) => next.has(pairId(p.key_a, p.key_b)));
      for (const p of pairs) {
        const id = pairId(p.key_a, p.key_b);
        allSelected ? next.delete(id) : next.add(id);
      }
      return next;
    });

  const applyBulk = (decision: "match" | "no_match") => {
    const verdicts = pairs
      .filter((p) => selected.has(pairId(p.key_a, p.key_b)))
      .map((p) => ({ key_a: p.key_a, key_b: p.key_b, decision }));
    if (verdicts.length === 0) return;
    if (!window.confirm(`Apply "${decision}" to ${verdicts.length} pairs?`)) return;
    batchMut.mutate({ collection, verdicts }, { onSuccess: () => setSelected(new Set()) });
  };

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <ReviewFilters
          status={status}
          onStatusChange={setStatus}
          minScore={minScore}
          onMinScoreChange={setMinScore}
          maxScore={maxScore}
          onMaxScoreChange={setMaxScore}
          source={source}
          onSourceChange={setSource}
        />
        <div className="flex items-center gap-3">
          <div className="text-sm text-gray-500 whitespace-nowrap">
            <span className="font-medium text-indigo-600">{pendingCount}</span> pending |{" "}
            <span className="font-medium text-green-600">{resolvedCount}</span> resolved
          </div>
          <a
            href={reviewCsvUrl(collection, filters)}
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
          >
            <Download className="h-3.5 w-3.5" />
            CSV
          </a>
          <button
            onClick={() => setShowShortcuts(true)}
            title="Keyboard shortcuts"
            className="inline-flex items-center rounded-md border border-gray-300 bg-white p-1.5 text-gray-600 shadow-sm hover:bg-gray-50"
          >
            <HelpCircle className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Bulk action bar */}
      {pairs.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-2 text-sm">
          <button onClick={selectAllVisible} className="font-medium text-indigo-600 hover:underline">
            {pairs.every((p) => selected.has(pairId(p.key_a, p.key_b)))
              ? "Deselect page"
              : "Select page"}
          </button>
          <span className="text-gray-500">{selected.size} selected</span>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => applyBulk("match")}
              disabled={selected.size === 0 || batchMut.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-40"
            >
              <Check className="h-3.5 w-3.5" />
              Accept as match
            </button>
            <button
              onClick={() => applyBulk("no_match")}
              disabled={selected.size === 0 || batchMut.isPending}
              className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-40"
            >
              <X className="h-3.5 w-3.5" />
              Reject as no-match
            </button>
          </div>
        </div>
      )}

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
            {pairs.map((p, i) => {
              const id = pairId(p.key_a, p.key_b);
              return (
                <div key={id} className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={selected.has(id)}
                    onChange={() => toggleSelect(p.key_a, p.key_b)}
                    className="mt-4 h-4 w-4 shrink-0 rounded border-gray-300 accent-indigo-600"
                  />
                  <div className="min-w-0 flex-1">
                    <PairComparison
                      pair={p}
                      collection={collection}
                      index={page * PAGE_SIZE + i}
                    />
                  </div>
                </div>
              );
            })}
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

      <ShortcutsModal open={showShortcuts} onClose={() => setShowShortcuts(false)} />
    </div>
  );
}
