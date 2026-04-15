import { fetchApi } from "./client";

export interface PipelineStatus {
  collection: string;
  document_count: number;
  edge_count: number;
  cluster_count: number;
  avg_quality_score?: number;
}

export interface PipelineRun {
  run_id: string;
  collection: string;
  config_name: string;
  started_at: string;
  completed_at?: string;
  status: string;
  clusters_found?: number;
  review_pending?: number;
  runtime_seconds?: number;
}

export interface PipelineConfig {
  collection: string;
  config: Record<string, unknown>;
}

export interface PipelineRunResult {
  run_id: string;
  status: string;
}

export function getPipelineStatus(collection: string) {
  return fetchApi<PipelineStatus>(`/api/pipeline/status/${collection}`);
}

export function getPipelineHistory() {
  return fetchApi<PipelineRun[]>("/api/pipeline/history");
}

export function runPipeline(config: PipelineConfig) {
  return fetchApi<PipelineRunResult>("/api/pipeline/run", {
    method: "POST",
    body: JSON.stringify(config),
  });
}
