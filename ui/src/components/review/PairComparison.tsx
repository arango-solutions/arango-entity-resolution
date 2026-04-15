import { useQuery } from "@tanstack/react-query";
import { ScoreBadge } from "../shared/ScoreBadge";
import { FieldDiff } from "../shared/FieldDiff";
import { Badge } from "../shared/Badge";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { FieldScoreBar } from "./FieldScoreBar";
import { VerdictPanel } from "./VerdictPanel";
import { getReviewPair, type ReviewPairSummary } from "../../api/review";

interface PairComparisonProps {
  pair: ReviewPairSummary;
  collection: string;
  index: number;
}

interface PairDetailRaw {
  key_a?: string;
  key_b?: string;
  record_a?: Record<string, unknown>;
  record_b?: Record<string, unknown>;
  doc_a?: Record<string, unknown>;
  doc_b?: Record<string, unknown>;
  overall_score?: number;
  field_scores?: Record<string, number>;
  llm_verdict?: string;
  llm_confidence?: number;
  llm_reasoning?: string;
  explanation?: {
    overall_score?: number;
    field_scores?: Record<string, number>;
    llm_verdict?: string;
    llm_confidence?: number;
    reasoning?: string;
    [key: string]: unknown;
  };
}

const INTERNAL_FIELDS = new Set([
  "_key",
  "_id",
  "_rev",
  "_from",
  "_to",
  "_er_source",
  "_er_cluster",
]);

function extractDisplayFields(
  docA: Record<string, unknown> | undefined,
  docB: Record<string, unknown> | undefined,
): { label: string; valueA: string | null; valueB: string | null }[] {
  if (!docA && !docB) return [];

  const allKeys = new Set([
    ...Object.keys(docA ?? {}),
    ...Object.keys(docB ?? {}),
  ]);

  return [...allKeys]
    .filter((k) => !INTERNAL_FIELDS.has(k))
    .sort()
    .map((k) => ({
      label: k,
      valueA: docA?.[k] != null ? String(docA[k]) : null,
      valueB: docB?.[k] != null ? String(docB[k]) : null,
    }));
}

export function PairComparison({
  pair,
  collection,
  index,
}: PairComparisonProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["review-pair", collection, pair.key_a, pair.key_b],
    queryFn: () => getReviewPair(collection, pair.key_a, pair.key_b),
    staleTime: 5 * 60 * 1000,
  });

  const raw = data as PairDetailRaw | undefined;
  const docA = raw?.record_a ?? raw?.doc_a;
  const docB = raw?.record_b ?? raw?.doc_b;
  const fieldScores =
    raw?.field_scores ?? raw?.explanation?.field_scores ?? {};
  const overallScore =
    raw?.overall_score ?? raw?.explanation?.overall_score ?? pair.score;
  const llmVerdict =
    raw?.llm_verdict ?? raw?.explanation?.llm_verdict ?? pair.llm_verdict;
  const llmConfidence =
    raw?.llm_confidence ??
    raw?.explanation?.llm_confidence ??
    pair.llm_confidence;
  const llmReasoning = raw?.llm_reasoning ?? raw?.explanation?.reasoning;

  const diffFields = extractDisplayFields(docA, docB);

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 border-b border-gray-100 bg-gray-50 px-5 py-3">
        <span className="text-sm font-semibold text-gray-700">
          Pair #{index + 1}
        </span>
        <span className="text-xs text-gray-400">|</span>
        <span className="text-sm text-gray-600">
          Score: <ScoreBadge score={overallScore} />
        </span>
        {llmVerdict && (
          <>
            <span className="text-xs text-gray-400">|</span>
            <span className="text-sm text-gray-600">
              LLM:{" "}
              <Badge
                variant={
                  llmVerdict === "match"
                    ? "success"
                    : llmVerdict === "no_match"
                      ? "danger"
                      : "warning"
                }
              >
                {llmVerdict}
              </Badge>
              {llmConfidence != null && (
                <span className="ml-1 text-xs text-gray-400">
                  ({llmConfidence.toFixed(2)})
                </span>
              )}
            </span>
          </>
        )}
        <div className="ml-auto flex gap-2 text-xs text-gray-400">
          <code>{pair.key_a}</code>
          <span>↔</span>
          <code>{pair.key_b}</code>
        </div>
      </div>

      {/* Body */}
      <div className="px-5 py-4 space-y-4">
        {isLoading ? (
          <div className="py-8">
            <LoadingSpinner />
          </div>
        ) : isError ? (
          <p className="text-sm text-red-600 py-4 text-center">
            Failed to load pair details. The records may not exist.
          </p>
        ) : (
          <>
            {/* Side-by-side field diff */}
            {diffFields.length > 0 && <FieldDiff fields={diffFields} />}

            {/* Field-level scores */}
            {Object.keys(fieldScores).length > 0 && (
              <div className="space-y-1.5">
                <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Field Scores
                </h4>
                <div className="space-y-1">
                  {Object.entries(fieldScores)
                    .sort(([, a], [, b]) => b - a)
                    .map(([field, score]) => (
                      <FieldScoreBar
                        key={field}
                        fieldName={field}
                        score={score}
                      />
                    ))}
                </div>
              </div>
            )}

            {/* LLM Reasoning */}
            {llmReasoning && (
              <div className="rounded-lg border border-blue-100 bg-blue-50/50 px-4 py-3">
                <h4 className="text-xs font-medium text-blue-700 uppercase tracking-wider mb-1">
                  LLM Reasoning
                </h4>
                <p className="text-sm text-blue-900 leading-relaxed">
                  {llmReasoning}
                </p>
              </div>
            )}
          </>
        )}

        {/* Verdict panel */}
        <div className="border-t border-gray-100 pt-1">
          <VerdictPanel
            collection={collection}
            keyA={pair.key_a}
            keyB={pair.key_b}
          />
        </div>
      </div>
    </div>
  );
}
