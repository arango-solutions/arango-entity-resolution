import { fetchApi } from "./client";

export interface ExportOptions {
  format: "json" | "csv";
  include_metadata?: boolean;
  include_golden_records?: boolean;
}

export interface ExportResult {
  filename: string;
  size: number;
  record_count: number;
}

export function exportClusters(collection: string, options: ExportOptions) {
  return fetchApi<ExportResult>(`/api/export/${collection}`, {
    method: "POST",
    body: JSON.stringify(options),
  });
}

export function downloadExport(collection: string, filename: string) {
  return `/api/export/${collection}/download/${filename}`;
}
