import { fetchApi } from "./client";

export interface ScoreBucket {
  lo: number;
  hi: number;
  count: number;
}

export interface ScoreDistributionResponse {
  buckets: ScoreBucket[];
  bucket: number;
}

export interface BoundaryPair {
  key_a: string;
  key_b: string;
  score: number;
}

export interface ApplyThresholdRequest {
  threshold?: number;
  low_threshold?: number;
  high_threshold?: number;
  run_id?: string;
}

export interface ApplyThresholdResponse {
  status: string;
  run_id: string;
  thresholds: {
    threshold: number | null;
    low_threshold: number | null;
    high_threshold: number | null;
  };
}

export function getScoreDistribution(collection: string, bucket = 0.05) {
  return fetchApi<ScoreDistributionResponse>(
    `/api/metrics/${collection}/score-distribution?bucket=${bucket}`,
  );
}

export function getBoundaryPairs(
  collection: string,
  score: number,
  window = 0.05,
  limit = 10,
) {
  return fetchApi<{ pairs: BoundaryPair[] }>(
    `/api/metrics/${collection}/boundary-pairs?score=${score}&window=${window}&limit=${limit}`,
  );
}

export function applyThreshold(
  collection: string,
  body: ApplyThresholdRequest,
) {
  return fetchApi<ApplyThresholdResponse>(
    `/api/metrics/${collection}/apply-threshold`,
    { method: "POST", body: JSON.stringify(body) },
  );
}
