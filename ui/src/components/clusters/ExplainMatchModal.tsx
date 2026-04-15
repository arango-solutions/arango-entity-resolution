import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { getReviewPair } from "../../api/review";
import { ScoreBadge } from "../shared/ScoreBadge";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { cn } from "../../lib/cn";

interface ExplainMatchModalProps {
  isOpen: boolean;
  onClose: () => void;
  collection: string;
  keyA: string;
  keyB: string;
}

function scoreBarColor(score: number): string {
  if (score >= 0.8) return "bg-green-500";
  if (score >= 0.55) return "bg-amber-500";
  return "bg-red-500";
}

export function ExplainMatchModal({
  isOpen,
  onClose,
  collection,
  keyA,
  keyB,
}: ExplainMatchModalProps) {
  const backdropRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["explain-match", collection, keyA, keyB],
    queryFn: () => getReviewPair(collection, keyA, keyB),
    enabled: isOpen && !!collection && !!keyA && !!keyB,
  });

  useEffect(() => {
    if (!isOpen) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const allFields = data
    ? Array.from(
        new Set([
          ...Object.keys(data.record_a),
          ...Object.keys(data.record_b),
        ]),
      ).filter((k) => !k.startsWith("_"))
    : [];

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === backdropRef.current) onClose();
      }}
    >
      <div className="relative mx-4 max-h-[85vh] w-full max-w-3xl overflow-hidden rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Edge Explanation
            </h2>
            <p className="mt-0.5 text-sm text-gray-500">
              <span className="font-mono">{keyA}</span>
              {" ↔ "}
              <span className="font-mono">{keyB}</span>
            </p>
          </div>
          <div className="flex items-center gap-3">
            {data && <ScoreBadge score={data.overall_score} />}
            <button
              onClick={onClose}
              className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto px-6 py-4" style={{ maxHeight: "calc(85vh - 80px)" }}>
          {isLoading && <LoadingSpinner className="py-12" />}

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error instanceof Error
                ? error.message
                : "Failed to load comparison data"}
            </div>
          )}

          {data && (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2.5 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
                      Field
                    </th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
                      Record A
                    </th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
                      Record B
                    </th>
                    <th className="px-4 py-2.5 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
                      Score
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">
                  {allFields.map((field) => {
                    const valA = data.record_a[field];
                    const valB = data.record_b[field];
                    const score = data.field_scores[field];
                    const differs =
                      valA != null &&
                      valB != null &&
                      String(valA) !== String(valB);

                    return (
                      <tr key={field}>
                        <td className="whitespace-nowrap px-4 py-2 font-medium text-gray-700">
                          {field}
                        </td>
                        <td
                          className={cn(
                            "max-w-[200px] truncate px-4 py-2",
                            valA == null
                              ? "italic text-gray-400"
                              : differs
                                ? "bg-amber-50 text-amber-900"
                                : "text-gray-700",
                          )}
                          title={valA != null ? String(valA) : undefined}
                        >
                          {valA != null ? String(valA) : "—"}
                        </td>
                        <td
                          className={cn(
                            "max-w-[200px] truncate px-4 py-2",
                            valB == null
                              ? "italic text-gray-400"
                              : differs
                                ? "bg-amber-50 text-amber-900"
                                : "text-gray-700",
                          )}
                          title={valB != null ? String(valB) : undefined}
                        >
                          {valB != null ? String(valB) : "—"}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2">
                          {score != null ? (
                            <div className="flex items-center gap-2">
                              <div className="h-2 w-24 overflow-hidden rounded-full bg-gray-200">
                                <div
                                  className={cn(
                                    "h-full rounded-full transition-all",
                                    scoreBarColor(score),
                                  )}
                                  style={{ width: `${score * 100}%` }}
                                />
                              </div>
                              <span className="text-xs font-medium text-gray-600">
                                {score.toFixed(2)}
                              </span>
                            </div>
                          ) : (
                            <span className="text-xs text-gray-400">N/A</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
