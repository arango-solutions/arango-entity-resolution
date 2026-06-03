import { fetchApi } from "./client";

export interface ResolveMatch {
  key: string;
  _key?: string;
  score: number;
  match?: boolean;
  field_scores?: Record<string, number>;
  record: Record<string, unknown>;
}

export interface CrossResolveParams {
  source_collection: string;
  target_collection: string;
  source_fields: string[];
  target_fields: string[];
  options?: Record<string, unknown>;
}

export function resolveEntity(
  collection: string,
  record: Record<string, unknown>,
  fields?: string[],
) {
  // The endpoint returns a bare array of matches.
  return fetchApi<ResolveMatch[]>(`/api/resolve/${collection}`, {
    method: "POST",
    body: JSON.stringify({ record, fields }),
  });
}

export function resolveEntityCross(params: CrossResolveParams) {
  return fetchApi<Record<string, unknown>>("/api/resolve/cross", {
    method: "POST",
    body: JSON.stringify(params),
  });
}
