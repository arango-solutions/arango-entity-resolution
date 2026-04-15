import { fetchApi } from "./client";

export interface ResolveMatch {
  key: string;
  score: number;
  record: Record<string, unknown>;
}

export interface ResolveResult {
  matches: ResolveMatch[];
  total: number;
}

export interface CrossResolveParams {
  source_collection: string;
  target_collection: string;
  record: Record<string, unknown>;
  fields?: string[];
  limit?: number;
}

export function resolveEntity(
  collection: string,
  record: Record<string, unknown>,
  fields?: string[],
) {
  return fetchApi<ResolveResult>(`/api/resolve/${collection}`, {
    method: "POST",
    body: JSON.stringify({ record, fields }),
  });
}

export function resolveEntityCross(params: CrossResolveParams) {
  return fetchApi<ResolveResult>("/api/resolve/cross", {
    method: "POST",
    body: JSON.stringify(params),
  });
}
