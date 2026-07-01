import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getCurationHistory,
  getSuspectClusters,
  removeMember,
  mergeClusters,
  splitCluster,
} from "../api/curation";

export function useCurationHistory(
  collection: string | null,
  key: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: ["curation-history", collection, key],
    queryFn: () => getCurationHistory(collection!, key!),
    enabled: enabled && !!collection && !!key,
  });
}

export function useSuspectClusters(collection: string | null) {
  return useQuery({
    queryKey: ["suspect-clusters", collection],
    queryFn: () => getSuspectClusters(collection!),
    enabled: !!collection,
  });
}

/** Invalidate every cluster-derived query after a curation edit. */
function useInvalidateClusters(collection: string | null) {
  const qc = useQueryClient();
  return () => {
    for (const k of [
      "clusters",
      "cluster-detail",
      "cluster-graph",
      "cluster-stats",
      "suspect-clusters",
      "curation-history",
    ]) {
      qc.invalidateQueries({ queryKey: [k, collection] });
    }
    // cluster-detail/graph/history carry an extra key segment.
    qc.invalidateQueries({ queryKey: ["cluster-detail"] });
    qc.invalidateQueries({ queryKey: ["cluster-graph"] });
    qc.invalidateQueries({ queryKey: ["curation-history"] });
  };
}

export function useRemoveMember(collection: string | null) {
  const invalidate = useInvalidateClusters(collection);
  return useMutation({
    mutationFn: ({ clusterKey, memberKey }: { clusterKey: string; memberKey: string }) =>
      removeMember(collection!, clusterKey, memberKey),
    onSuccess: invalidate,
  });
}

export function useMergeClusters(collection: string | null) {
  const invalidate = useInvalidateClusters(collection);
  return useMutation({
    mutationFn: (clusterKeys: string[]) => mergeClusters(collection!, clusterKeys),
    onSuccess: invalidate,
  });
}

export function useSplitCluster(collection: string | null) {
  const invalidate = useInvalidateClusters(collection);
  return useMutation({
    mutationFn: ({ clusterKey, keyA, keyB }: { clusterKey: string; keyA: string; keyB: string }) =>
      splitCluster(collection!, clusterKey, keyA, keyB),
    onSuccess: invalidate,
  });
}
