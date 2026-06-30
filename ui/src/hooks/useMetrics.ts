import { useQuery } from "@tanstack/react-query";
import { getScoreDistribution, getBoundaryPairs } from "../api/metrics";

export function useScoreDistribution(
  collection: string | null,
  bucket = 0.05,
) {
  return useQuery({
    queryKey: ["score-distribution", collection, bucket],
    queryFn: () => getScoreDistribution(collection!, bucket),
    enabled: !!collection,
  });
}

export function useBoundaryPairs(
  collection: string | null,
  score: number,
  window = 0.05,
  limit = 10,
) {
  return useQuery({
    queryKey: ["boundary-pairs", collection, score, window, limit],
    queryFn: () => getBoundaryPairs(collection!, score, window, limit),
    enabled: !!collection,
  });
}
