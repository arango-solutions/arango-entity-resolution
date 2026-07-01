import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getReviewQueue,
  getReviewStats,
  submitVerdict,
  batchVerdict,
  type BatchVerdictItem,
  type ReviewFilters,
  type VerdictRequest,
} from "../api/review";

export function useReviewQueue(
  collection: string | null,
  filters?: ReviewFilters,
) {
  return useQuery({
    queryKey: ["review-queue", collection, filters],
    queryFn: () => getReviewQueue(collection!, filters),
    enabled: !!collection,
  });
}

export function useReviewStats(collection: string | null) {
  return useQuery({
    queryKey: ["review-stats", collection],
    queryFn: () => getReviewStats(collection!),
    enabled: !!collection,
  });
}

export function useSubmitVerdict() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      collection,
      keyA,
      keyB,
      verdict,
    }: {
      collection: string;
      keyA: string;
      keyB: string;
      verdict: VerdictRequest;
    }) => submitVerdict(collection, keyA, keyB, verdict),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      void queryClient.invalidateQueries({ queryKey: ["review-stats"] });
    },
  });
}

export function useBatchVerdict() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      collection,
      verdicts,
    }: {
      collection: string;
      verdicts: BatchVerdictItem[];
    }) => batchVerdict(collection, verdicts),
    onSuccess: () => {
      for (const k of ["review-queue", "review-stats", "clusters", "cluster-detail", "cluster-graph", "cluster-stats"]) {
        void queryClient.invalidateQueries({ queryKey: [k] });
      }
    },
  });
}
