import { fetchApi } from "./client";

export interface Collection {
  name: string;
  type: string;
  count: number;
}

export interface CollectionProfile {
  collection: string;
  field_stats: Record<string, unknown>;
  null_rates: Record<string, number>;
  heavy_hitters: Record<string, unknown>;
}

export interface CollectionSample {
  schema: Record<string, unknown>;
  sample: unknown[];
}

export function getCollections() {
  return fetchApi<Collection[]>("/api/collections");
}

export function getCollectionProfile(name: string) {
  return fetchApi<CollectionProfile>(`/api/collections/${name}/profile`);
}

export function getCollectionSample(name: string) {
  return fetchApi<CollectionSample>(`/api/collections/${name}/sample`);
}
