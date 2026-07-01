import { fetchApi } from "./client";

export interface AuditEntry {
  _key: string;
  actor: string;
  action: string;
  collection: string;
  entity_key: string | null;
  before: unknown;
  after: unknown;
  ts: number;
}

export interface CurationHistoryResponse {
  entries: AuditEntry[];
}

export interface ReclusterResult {
  component_size: number;
  clusters_before: number;
  clusters_after: number;
  cluster_keys: string[];
}

export interface CurationMutationResult {
  status: string;
  clusters_changed: string[];
  recluster: ReclusterResult;
}

export interface SuspectCluster {
  cluster_key: string;
  reason: string;
  mean_edge_score: number | null;
  members: string[];
  status: string;
}

/** Fetch the audit trail (newest first) for a cluster/entity/pair key. */
export function getCurationHistory(
  collection: string,
  key: string,
  limit = 50,
) {
  return fetchApi<CurationHistoryResponse>(
    `/api/curation/${collection}/history/${key}?limit=${limit}`,
  );
}

/** Eject a member from a cluster (suppresses its intra-cluster edges). */
export function removeMember(collection: string, clusterKey: string, memberKey: string) {
  return fetchApi<CurationMutationResult>(
    `/api/curation/${collection}/cluster/${clusterKey}/remove-member`,
    { method: "POST", body: JSON.stringify({ member_key: memberKey }) },
  );
}

/** Merge two or more clusters into one. */
export function mergeClusters(collection: string, clusterKeys: string[]) {
  return fetchApi<CurationMutationResult>(
    `/api/curation/${collection}/merge`,
    { method: "POST", body: JSON.stringify({ cluster_keys: clusterKeys }) },
  );
}

/** Split a cluster by suppressing a bridge edge between two members. */
export function splitCluster(
  collection: string,
  clusterKey: string,
  keyA: string,
  keyB: string,
) {
  return fetchApi<CurationMutationResult>(
    `/api/curation/${collection}/cluster/${clusterKey}/split`,
    { method: "POST", body: JSON.stringify({ key_a: keyA, key_b: keyB }) },
  );
}

/** Pending cluster-repair-queue entries scoped to a collection. */
export function getSuspectClusters(collection: string, limit = 50) {
  return fetchApi<{ clusters: SuspectCluster[] }>(
    `/api/curation/${collection}/suspect-clusters?limit=${limit}`,
  );
}
