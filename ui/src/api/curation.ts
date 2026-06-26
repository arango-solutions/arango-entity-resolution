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
