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

export interface FieldProvenance {
  distinctValues: number;
  sources: number;
  chosenFrom: string;
  strategy: string;
}

export interface SurvivorshipPreview {
  golden_record: Record<string, unknown>;
  provenance: Record<string, FieldProvenance>;
  conflicts: string[];
  sources: Record<string, unknown>[];
  merged_keys: string[];
}

export interface GoldenApplyResult {
  status: string;
  golden_key: string;
  golden_record: Record<string, unknown>;
}

/** Preview a golden record from member keys using a survivorship strategy. */
export function survivorshipPreview(
  collection: string,
  memberKeys: string[],
  mergeStrategy: string,
  fieldStrategies?: Record<string, string>,
) {
  return fetchApi<SurvivorshipPreview>(
    `/api/golden/${collection}/survivorship-preview`,
    {
      method: "POST",
      body: JSON.stringify({
        member_keys: memberKeys,
        merge_strategy: mergeStrategy,
        field_strategies: fieldStrategies,
      }),
    },
  );
}

/** Persist a steward-edited golden record (audited). */
export function applyGoldenRecord(
  collection: string,
  memberKeys: string[],
  fields: Record<string, unknown>,
  mergeStrategy?: string,
) {
  return fetchApi<GoldenApplyResult>(`/api/golden/${collection}/apply`, {
    method: "POST",
    body: JSON.stringify({
      member_keys: memberKeys,
      fields,
      merge_strategy: mergeStrategy,
    }),
  });
}
