import { fetchApi } from "./client";

export interface GoldenRecordPreview {
  fields: Record<string, unknown>;
  provenance: Record<string, { source: string; confidence: number }>;
  conflicts: string[];
}

export interface GoldenRecord {
  _key: string;
  collection: string;
  fields: Record<string, unknown>;
  provenance: Record<string, { source: string; confidence: number }>;
  created_at: string;
}

export interface ProvenanceRecord {
  source: string;
  record_key: string;
  ingested_at: string;
  confidence: number;
  fields: Record<string, unknown>;
}

export function previewGoldenRecord(
  collection: string,
  keys: string[],
  strategy?: string,
) {
  return fetchApi<GoldenRecordPreview>(
    `/api/golden/${collection}/preview`,
    {
      method: "POST",
      body: JSON.stringify({ keys, strategy }),
    },
  );
}

export function mergeGoldenRecord(
  collection: string,
  keys: string[],
  strategy?: string,
) {
  return fetchApi<GoldenRecord>(`/api/golden/${collection}/merge`, {
    method: "POST",
    body: JSON.stringify({ keys, strategy }),
  });
}

export function getGoldenRecord(collection: string, key: string) {
  return fetchApi<GoldenRecord>(`/api/golden/${collection}/${key}`);
}

export function getProvenance(collection: string, key: string) {
  return fetchApi<ProvenanceRecord[]>(
    `/api/golden/${collection}/${key}/provenance`,
  );
}
