import { fetchApi } from "./client";

export interface ReviewVerdict {
  key_a: string;
  key_b: string;
  score: number;
  decision?: string;
  confidence?: number;
  source?: string;
}

/** Display shape for a pair in the review queue (derived from a verdict). */
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
  source?: string;
  sort_by?: string;
  sort_order?: string;
  limit?: number;
  offset?: number;
}

export interface ReviewQueueResponse {
  verdicts: ReviewVerdict[];
  total: number;
  offset: number;
  limit: number;
}

export interface ReviewDecisionCount {
  decision: string;
  count: number;
  avg_score?: number;
  avg_confidence?: number;
}

export interface ReviewStats {
  by_decision: ReviewDecisionCount[];
  total: number;
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
  decision: "match" | "no_match";
  confidence?: number;
  notes?: string;
}

export interface ThresholdInfo {
  low_threshold: number;
  high_threshold: number;
  source?: string;
  sample_count?: number;
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
