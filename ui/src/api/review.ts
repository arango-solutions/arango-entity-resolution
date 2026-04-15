import { fetchApi } from "./client";

export interface ReviewPairSummary {
  key_a: string;
  key_b: string;
  score: number;
  status: string;
  llm_verdict?: string;
  llm_confidence?: number;
}

export interface ReviewFilters {
  status?: string;
  min_score?: number;
  max_score?: number;
  page?: number;
  page_size?: number;
}

export interface ReviewQueueResponse {
  pairs: ReviewPairSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReviewStats {
  pending: number;
  resolved: number;
  total: number;
  match_count: number;
  no_match_count: number;
}

export interface ReviewPairDetail {
  key_a: string;
  key_b: string;
  record_a: Record<string, unknown>;
  record_b: Record<string, unknown>;
  overall_score: number;
  field_scores: Record<string, number>;
  llm_verdict?: string;
  llm_confidence?: number;
  llm_reasoning?: string;
}

export interface VerdictRequest {
  verdict: "match" | "no_match" | "skip";
  notes?: string;
}

export interface ThresholdInfo {
  low: number;
  high: number;
}

export function getReviewQueue(collection: string, filters?: ReviewFilters) {
  const search = new URLSearchParams();
  if (filters) {
    Object.entries(filters).forEach(([k, v]) => {
      if (v != null) search.set(k, String(v));
    });
  }
  const qs = search.toString();
  return fetchApi<ReviewQueueResponse>(
    `/api/review/${collection}${qs ? `?${qs}` : ""}`,
  );
}

export function getReviewStats(collection: string) {
  return fetchApi<ReviewStats>(`/api/review/${collection}/stats`);
}

export function getReviewPair(
  collection: string,
  keyA: string,
  keyB: string,
) {
  return fetchApi<ReviewPairDetail>(
    `/api/review/${collection}/pair/${keyA}/${keyB}`,
  );
}

export function submitVerdict(
  collection: string,
  keyA: string,
  keyB: string,
  verdict: VerdictRequest,
) {
  return fetchApi<{ ok: boolean }>(
    `/api/review/${collection}/pair/${keyA}/${keyB}/verdict`,
    { method: "POST", body: JSON.stringify(verdict) },
  );
}

export function optimizeThresholds(collection: string) {
  return fetchApi<ThresholdInfo>(`/api/review/${collection}/optimize`, {
    method: "POST",
  });
}

export function getThresholds(collection: string) {
  return fetchApi<ThresholdInfo>(`/api/review/${collection}/thresholds`);
}
