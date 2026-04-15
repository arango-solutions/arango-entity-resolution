import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  AlertTriangle,
  Play,
  Download,
  FlaskConical,
  ShieldCheck,
} from "lucide-react";
import { validateConfig, exportConfig, simulateVariants } from "../../api/config";
import { CollectionSection } from "./CollectionSection";
import { BlockingSection } from "./BlockingSection";
import { SimilaritySection } from "./SimilaritySection";
import { ClusteringSection } from "./ClusteringSection";
import { LLMSection } from "./LLMSection";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { cn } from "../../lib/cn";

interface FieldWeight {
  field: string;
  weight: number;
}

interface PipelineConfig {
  entity_type: string;
  collection_name: string;
  blocking: {
    strategy: string;
    fields: string[];
    max_block_size: number;
  };
  similarity: {
    algorithm: string;
    threshold: number;
    fields: FieldWeight[];
  };
  clustering: {
    backend: string;
    min_cluster_size: number;
    store_results: boolean;
  };
  active_learning: {
    enabled: boolean;
    llm: { provider: string; model: string };
    low_threshold: number;
    high_threshold: number;
  };
}

const DEFAULT_CONFIG: PipelineConfig = {
  entity_type: "",
  collection_name: "",
  blocking: { strategy: "bm25", fields: [], max_block_size: 1000 },
  similarity: { algorithm: "jaro_winkler", threshold: 0.8, fields: [] },
  clustering: { backend: "auto", min_cluster_size: 2, store_results: true },
  active_learning: {
    enabled: false,
    llm: { provider: "ollama", model: "" },
    low_threshold: 0.55,
    high_threshold: 0.8,
  },
};

interface AccordionItemProps {
  title: string;
  step: number;
  isOpen: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

function AccordionItem({
  title,
  step,
  isOpen,
  onToggle,
  children,
}: AccordionItemProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-gray-50"
      >
        {isOpen ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-gray-500" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-gray-500" />
        )}
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700">
          {step}
        </span>
        <span className="text-sm font-semibold text-gray-900">{title}</span>
      </button>
      {isOpen && (
        <div className="border-t border-gray-200 px-4 py-4">{children}</div>
      )}
    </div>
  );
}

export function ConfigBuilder() {
  const navigate = useNavigate();
  const [config, setConfig] = useState<PipelineConfig>(DEFAULT_CONFIG);
  const [openSections, setOpenSections] = useState<Set<number>>(
    new Set([1]),
  );

  const [validationResult, setValidationResult] = useState<{
    valid: boolean;
    errors: string[];
  } | null>(null);
  const [validating, setValidating] = useState(false);

  const [simResult, setSimResult] = useState<Record<string, unknown> | null>(null);
  const [simulating, setSimulating] = useState(false);

  const [exporting, setExporting] = useState(false);

  const toggleSection = (section: number) => {
    setOpenSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) next.delete(section);
      else next.add(section);
      return next;
    });
  };

  const toApiConfig = useCallback((): Record<string, unknown> => {
    const fieldWeights: Record<string, number> = {};
    for (const fw of config.similarity.fields) {
      if (fw.field) fieldWeights[fw.field] = fw.weight;
    }
    return {
      config: {
        entity_type: config.entity_type,
        collection_name: config.collection_name,
        blocking: config.blocking,
        similarity: {
          algorithm: config.similarity.algorithm,
          threshold: config.similarity.threshold,
          fields: fieldWeights,
        },
        clustering: config.clustering,
        active_learning: config.active_learning.enabled
          ? {
              enabled: true,
              llm: config.active_learning.llm,
              low_threshold: config.active_learning.low_threshold,
              high_threshold: config.active_learning.high_threshold,
            }
          : { enabled: false },
      },
    };
  }, [config]);

  const handleValidate = async () => {
    setValidating(true);
    setValidationResult(null);
    try {
      const result = await validateConfig(toApiConfig());
      setValidationResult(result);
    } catch (err) {
      setValidationResult({
        valid: false,
        errors: [
          err instanceof Error ? err.message : "Validation request failed",
        ],
      });
    } finally {
      setValidating(false);
    }
  };

  const handleSimulate = async () => {
    setSimulating(true);
    setSimResult(null);
    try {
      const result = await simulateVariants([
        { name: "current", config: toApiConfig() },
      ]);
      setSimResult(result as unknown as Record<string, unknown>);
    } catch (err) {
      setSimResult({
        error:
          err instanceof Error ? err.message : "Simulation request failed",
      });
    } finally {
      setSimulating(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const result = await exportConfig(toApiConfig(), "yaml");
      const blob = new Blob([result.content], { type: "text/yaml" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "pipeline-config.yaml";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Fallback: show the config as YAML-like JSON download
      const blob = new Blob([JSON.stringify(toApiConfig(), null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "pipeline-config.json";
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  };

  const handleRun = () => {
    navigate("/pipeline", { state: { config: toApiConfig() } });
  };

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <AccordionItem
          title="Collection"
          step={1}
          isOpen={openSections.has(1)}
          onToggle={() => toggleSection(1)}
        >
          <CollectionSection
            entityType={config.entity_type}
            collectionName={config.collection_name}
            onEntityTypeChange={(v) =>
              setConfig((c) => ({ ...c, entity_type: v }))
            }
            onCollectionChange={(v) =>
              setConfig((c) => ({ ...c, collection_name: v }))
            }
          />
        </AccordionItem>

        <AccordionItem
          title="Blocking"
          step={2}
          isOpen={openSections.has(2)}
          onToggle={() => toggleSection(2)}
        >
          <BlockingSection
            strategy={config.blocking.strategy}
            fields={config.blocking.fields}
            maxBlockSize={config.blocking.max_block_size}
            onStrategyChange={(v) =>
              setConfig((c) => ({
                ...c,
                blocking: { ...c.blocking, strategy: v },
              }))
            }
            onFieldsChange={(v) =>
              setConfig((c) => ({
                ...c,
                blocking: { ...c.blocking, fields: v },
              }))
            }
            onMaxBlockSizeChange={(v) =>
              setConfig((c) => ({
                ...c,
                blocking: { ...c.blocking, max_block_size: v },
              }))
            }
            collectionName={config.collection_name}
          />
        </AccordionItem>

        <AccordionItem
          title="Similarity"
          step={3}
          isOpen={openSections.has(3)}
          onToggle={() => toggleSection(3)}
        >
          <SimilaritySection
            algorithm={config.similarity.algorithm}
            threshold={config.similarity.threshold}
            fieldWeights={config.similarity.fields}
            onAlgorithmChange={(v) =>
              setConfig((c) => ({
                ...c,
                similarity: { ...c.similarity, algorithm: v },
              }))
            }
            onThresholdChange={(v) =>
              setConfig((c) => ({
                ...c,
                similarity: { ...c.similarity, threshold: v },
              }))
            }
            onFieldWeightsChange={(v) =>
              setConfig((c) => ({
                ...c,
                similarity: { ...c.similarity, fields: v },
              }))
            }
          />
        </AccordionItem>

        <AccordionItem
          title="Clustering"
          step={4}
          isOpen={openSections.has(4)}
          onToggle={() => toggleSection(4)}
        >
          <ClusteringSection
            backend={config.clustering.backend}
            minClusterSize={config.clustering.min_cluster_size}
            storeResults={config.clustering.store_results}
            onBackendChange={(v) =>
              setConfig((c) => ({
                ...c,
                clustering: { ...c.clustering, backend: v },
              }))
            }
            onMinClusterSizeChange={(v) =>
              setConfig((c) => ({
                ...c,
                clustering: { ...c.clustering, min_cluster_size: v },
              }))
            }
            onStoreResultsChange={(v) =>
              setConfig((c) => ({
                ...c,
                clustering: { ...c.clustering, store_results: v },
              }))
            }
          />
        </AccordionItem>

        <AccordionItem
          title="LLM Curation (optional)"
          step={5}
          isOpen={openSections.has(5)}
          onToggle={() => toggleSection(5)}
        >
          <LLMSection
            enabled={config.active_learning.enabled}
            provider={config.active_learning.llm.provider}
            model={config.active_learning.llm.model}
            lowThreshold={config.active_learning.low_threshold}
            highThreshold={config.active_learning.high_threshold}
            onEnabledChange={(v) =>
              setConfig((c) => ({
                ...c,
                active_learning: { ...c.active_learning, enabled: v },
              }))
            }
            onProviderChange={(v) =>
              setConfig((c) => ({
                ...c,
                active_learning: {
                  ...c.active_learning,
                  llm: { ...c.active_learning.llm, provider: v },
                },
              }))
            }
            onModelChange={(v) =>
              setConfig((c) => ({
                ...c,
                active_learning: {
                  ...c.active_learning,
                  llm: { ...c.active_learning.llm, model: v },
                },
              }))
            }
            onLowThresholdChange={(v) =>
              setConfig((c) => ({
                ...c,
                active_learning: { ...c.active_learning, low_threshold: v },
              }))
            }
            onHighThresholdChange={(v) =>
              setConfig((c) => ({
                ...c,
                active_learning: { ...c.active_learning, high_threshold: v },
              }))
            }
          />
        </AccordionItem>
      </div>

      {/* Validation result */}
      {validationResult && (
        <div
          className={cn(
            "rounded-lg border px-4 py-3",
            validationResult.valid
              ? "border-green-200 bg-green-50"
              : "border-red-200 bg-red-50",
          )}
        >
          <div className="flex items-center gap-2">
            {validationResult.valid ? (
              <CheckCircle2 className="h-5 w-5 text-green-600" />
            ) : (
              <AlertTriangle className="h-5 w-5 text-red-600" />
            )}
            <span
              className={cn(
                "text-sm font-medium",
                validationResult.valid ? "text-green-800" : "text-red-800",
              )}
            >
              {validationResult.valid
                ? "Configuration is valid"
                : `${validationResult.errors.length} error(s) found`}
            </span>
          </div>
          {validationResult.errors.length > 0 && (
            <ul className="mt-2 space-y-1">
              {validationResult.errors.map((err, i) => (
                <li key={i} className="text-sm text-red-700">
                  &bull; {err}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Simulation result */}
      {simResult && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
          <p className="mb-2 text-sm font-medium text-blue-800">
            Simulation Results
          </p>
          <pre className="max-h-60 overflow-auto rounded bg-white p-3 text-xs text-gray-700">
            {JSON.stringify(simResult, null, 2)}
          </pre>
        </div>
      )}

      {/* Action bar */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
        <button
          type="button"
          onClick={handleValidate}
          disabled={validating}
          className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
        >
          <ShieldCheck className="h-4 w-4" />
          Validate
          {validating && <LoadingSpinner size="sm" />}
        </button>

        <button
          type="button"
          onClick={handleSimulate}
          disabled={simulating}
          className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
        >
          <FlaskConical className="h-4 w-4" />
          Simulate
          {simulating && <LoadingSpinner size="sm" />}
        </button>

        <button
          type="button"
          onClick={handleExport}
          disabled={exporting}
          className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
        >
          <Download className="h-4 w-4" />
          Export YAML
          {exporting && <LoadingSpinner size="sm" />}
        </button>

        <div className="flex-1" />

        <button
          type="button"
          onClick={handleRun}
          className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
        >
          <Play className="h-4 w-4" />
          Run
        </button>
      </div>
    </div>
  );
}
