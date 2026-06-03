import { fetchApi } from "./client";

export interface ExportRequestOptions {
  filename_prefix?: string;
  limit?: number | null;
  cluster_collection?: string;
  edge_collection?: string;
}

export interface ExportResult {
  collection: string;
  output_files: { json: string; csv: string };
  clusters_exported: number;
}

export function exportClusters(
  collection: string,
  options?: ExportRequestOptions,
) {
  return fetchApi<ExportResult>(`/api/export/${collection}`, {
    method: "POST",
    body: JSON.stringify(options ?? {}),
  });
}

/** Extract the basename from a server file path for the download endpoint. */
export function basename(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

export function downloadExport(collection: string, filename: string) {
  return `/api/export/${collection}/download/${filename}`;
}
