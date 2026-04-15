import { fetchApi } from "./client";

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface StrategyRecommendation {
  strategy: string;
  rationale: string;
  field_weights: Record<string, number>;
  similarity_algorithm: string;
}

export interface BlockingRecommendation {
  blocking_keys: string[];
  strategy: string;
  estimated_reduction: number;
  rationale: string;
}

export interface SimulationVariant {
  name: string;
  config: Record<string, unknown>;
}

export interface SimulationResult {
  variants: {
    name: string;
    estimated_clusters: number;
    estimated_precision: number;
    estimated_recall: number;
  }[];
}

export interface ExportedConfig {
  format: string;
  content: string;
}

export function validateConfig(config: Record<string, unknown>) {
  return fetchApi<ValidationResult>("/api/config/validate", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function recommendStrategy(profile: Record<string, unknown>) {
  return fetchApi<StrategyRecommendation>("/api/config/recommend", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

export function recommendBlocking(profile: Record<string, unknown>) {
  return fetchApi<BlockingRecommendation>("/api/config/blocking", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

export function simulateVariants(variants: SimulationVariant[]) {
  return fetchApi<SimulationResult>("/api/config/simulate", {
    method: "POST",
    body: JSON.stringify({ variants }),
  });
}

export function exportConfig(
  recommendation: Record<string, unknown>,
  format: string,
) {
  return fetchApi<ExportedConfig>("/api/config/export", {
    method: "POST",
    body: JSON.stringify({ recommendation, format }),
  });
}
