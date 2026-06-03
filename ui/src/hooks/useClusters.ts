import { useQuery } from "@tanstack/react-query";
import {
  getClusters,
  getClusterDetail,
  getClusterGraph,
  getClusterStats,
  type ClusterListParams,
} from "../api/clusters";

export function useClusters(
  collection: string | null,
  params?: ClusterListParams,
) {
  return useQuery({
    queryKey: ["clusters", collection, params],
    queryFn: () => getClusters(collection!, params),
    enabled: !!collection,
  });
}

export function useClusterDetail(
  collection: string | null,
  key: string | null,
) {
  return useQuery({
    queryKey: ["cluster-detail", collection, key],
    queryFn: () => getClusterDetail(collection!, key!),
    enabled: !!collection && !!key,
  });
}

export function useClusterGraph(
  collection: string | null,
  key: string | null,
) {
  return useQuery({
    queryKey: ["cluster-graph", collection, key],
    queryFn: () => getClusterGraph(collection!, key!),
    enabled: !!collection && !!key,
  });
}

export function useClusterStats(collection: string | null) {
  return useQuery({
    queryKey: ["cluster-stats", collection],
    queryFn: () => getClusterStats(collection!),
    enabled: !!collection,
  });
}
