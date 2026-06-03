import { useState, useCallback, useEffect } from "react";
import { Play, Square, AlertCircle } from "lucide-react";
import { useSelectedCollection } from "../../contexts/CollectionContext";
import { useRunPipeline } from "../../hooks/usePipeline";
import { usePipelineWs } from "../../hooks/usePipelineWs";
import { StageProgress } from "./StageProgress";
import { PipelineResults } from "./PipelineResults";
import { ConfigUploader } from "./ConfigUploader";
import { PipelineHistory } from "./PipelineHistory";

export function PipelineRunner() {
  const { selectedCollection } = useSelectedCollection();
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const runPipeline = useRunPipeline();
  const { stages, isComplete, error, summary } = usePipelineWs(runId);

  const handleConfigLoaded = useCallback(
    (parsed: Record<string, unknown>) => {
      setConfig(parsed);
    },
    [],
  );

  async function handleRun() {
    if (!config || !selectedCollection) return;

    setIsRunning(true);
    setRunId(null);

    try {
      const result = await runPipeline.mutateAsync({
        collection: selectedCollection,
        config,
      });
      setRunId(result.run_id);
    } catch {
      setIsRunning(false);
    }
  }

  function handleCancel() {
    setRunId(null);
    setIsRunning(false);
  }

  const pipelineDone = isComplete || !!error;
  useEffect(() => {
    if (pipelineDone && isRunning) {
      setIsRunning(false);
    }
  }, [pipelineDone, isRunning]);

  return (
    <div className="space-y-6">
      {!runId && <ConfigUploader onConfigLoaded={handleConfigLoaded} />}

      {!runId && (
        <div className="flex items-center gap-3">
          <button
            onClick={handleRun}
            disabled={!config || isRunning || !selectedCollection}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            Run Pipeline
          </button>
          {!config && (
            <p className="text-xs text-gray-500">
              Upload or paste a config to get started
            </p>
          )}
        </div>
      )}

      {runId && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-900">
              Pipeline Progress
            </h3>
            {isRunning && (
              <button
                onClick={handleCancel}
                className="inline-flex items-center gap-1.5 rounded-md bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-200"
              >
                <Square className="h-3 w-3" />
                Cancel
              </button>
            )}
          </div>

          <div className="space-y-2">
            {stages.map((stage) => (
              <StageProgress
                key={stage.name}
                name={stage.name}
                status={stage.status}
                progress={stage.progress}
                result={stage.result}
                startedAt={stage.startedAt}
                completedAt={stage.completedAt}
              />
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium">Pipeline Error</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      {isComplete && summary && selectedCollection && (
        <PipelineResults summary={summary} collection={selectedCollection} />
      )}

      <div className="rounded-lg border border-gray-200 bg-white p-5">
        <h3 className="mb-4 text-sm font-medium text-gray-700">
          Pipeline History
        </h3>
        <PipelineHistory limit={5} />
      </div>
    </div>
  );
}
