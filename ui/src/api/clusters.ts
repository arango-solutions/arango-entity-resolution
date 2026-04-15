import { fetchApi } from "./client";

export interface ClusterSummary {
  id: string;
  size: number;
  quality_score: number;
  average_similarity: number;
  density: number;
}

export interface ClusterListParams {
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  min_size?: number;
  search?: string;
}

export interface ClusterListResponse {
  clusters: ClusterSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface ClusterDetail {
  id: string;
  size: number;
  quality_score: number;
  average_similarity: number;
  density: number;
  members: Record<string, unknown>[];
}

export interface ClusterGraphNode {
  id: string;
  label: string;
  source?: string;
  data: Record<string, unknown>;
}

export interface ClusterGraphEdge {
  source: string;
  target: string;
  similarity: number;
}

export interface ClusterGraph {
  nodes: ClusterGraphNode[];
  edges: ClusterGraphEdge[];
}

export interface ClusterStats {
  total_clusters: number;
  total_members: number;
  avg_cluster_size: number;
  avg_quality_score: number;
  size_distribution: Record<string, number>;
}

export function getClusters(collection: string, params?: ClusterListParams) {
  const search = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v != null) search.set(k, String(v));
    });
  }
  const qs = search.toString();
  return fetchApi<ClusterListResponse>(
    `/api/clusters/${collection}${qs ? `?${qs}` : ""}`,
  );
}

export function getClusterDetail(collection: string, key: string) {
  return fetchApi<ClusterDetail>(`/api/clusters/${collection}/${key}`);
}

export function getClusterGraph(collection: string, key: string) {
  return fetchApi<ClusterGraph>(`/api/clusters/${collection}/${key}/graph`);
}

export function getClusterStats(collection: string) {
  return fetchApi<ClusterStats>(`/api/clusters/${collection}/stats`);
}
