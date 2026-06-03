import { fetchApi } from "./client";

export interface GoldenRecordPreview {
  golden_record: Record<string, unknown>;
  merged_keys: string[];
  canonical_key: string;
  strategy_used: string;
}

export interface GoldenMergeResult extends GoldenRecordPreview {
  persisted?: boolean;
  golden_collection?: string;
}

export interface GoldenProvenance {
  golden_record: Record<string, unknown>;
  source_records: Record<string, unknown>[];
  merged_keys: string[];
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
      body: JSON.stringify({ entity_keys: keys, strategy }),
    },
  );
}

export function mergeGoldenRecord(
  collection: string,
  keys: string[],
  strategy?: string,
) {
  return fetchApi<GoldenMergeResult>(`/api/golden/${collection}/merge`, {
    method: "POST",
    body: JSON.stringify({ entity_keys: keys, strategy }),
  });
}

export function getGoldenRecord(collection: string, key: string) {
  return fetchApi<Record<string, unknown>>(`/api/golden/${collection}/${key}`);
}

export function getProvenance(collection: string, key: string) {
  return fetchApi<GoldenProvenance>(
    `/api/golden/${collection}/${key}/provenance`,
  );
}
