import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getReviewQueue,
  getReviewStats,
  submitVerdict,
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
