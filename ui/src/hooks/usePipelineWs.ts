import { useState, useEffect, useRef, useCallback } from "react";

export interface StageState {
  name: string;
  status: "waiting" | "running" | "complete" | "error";
  progress?: number;
  result?: Record<string, unknown>;
  startedAt?: string;
  completedAt?: string;
}

interface WsMessage {
  type: string;
  stage?: string;
  progress?: number;
  detail?: string;
  result?: Record<string, unknown>;
  timestamp?: string;
  total_runtime_seconds?: number;
  summary?: Record<string, unknown>;
  error?: string;
  run_id?: string;
  status?: string;
  started_at?: number;
  completed_at?: number;
}

interface UsePipelineWsReturn {
  stages: StageState[];
  isConnected: boolean;
  isComplete: boolean;
  error: string | null;
  summary: Record<string, unknown> | null;
}

const DEFAULT_STAGES: StageState[] = [
  { name: "blocking", status: "waiting" },
  { name: "similarity", status: "waiting" },
  { name: "llm_curation", status: "waiting" },
  { name: "clustering", status: "waiting" },
  { name: "golden_records", status: "waiting" },
];

function formatStageName(name: string): string {
  return name
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export { formatStageName };

export function usePipelineWs(runId: string | null): UsePipelineWsReturn {
  const [stages, setStages] = useState<StageState[]>(DEFAULT_STAGES);
  const [isConnected, setIsConnected] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const updateStage = useCallback(
    (stageName: string, update: Partial<StageState>) => {
      setStages((prev) => {
        const idx = prev.findIndex((s) => s.name === stageName);
        if (idx === -1) {
          return [...prev, { name: stageName, status: "waiting", ...update }];
        }
        return prev.map((s, i) => (i === idx ? { ...s, ...update } : s));
      });
    },
    [],
  );

  useEffect(() => {
    if (!runId) return;

    setStages(DEFAULT_STAGES.map((s) => ({ ...s })));
    setIsComplete(false);
    setError(null);
    setSummary(null);

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/pipeline/${runId}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    ws.onerror = () => {
      setError("WebSocket connection failed");
      setIsConnected(false);
    };

    ws.onmessage = (event) => {
      let msg: WsMessage;
      try {
        msg = JSON.parse(event.data as string) as WsMessage;
      } catch {
        return;
      }

      switch (msg.type) {
        case "stage_start":
          if (msg.stage) {
            updateStage(msg.stage, {
              status: "running",
              startedAt: msg.timestamp ?? new Date().toISOString(),
              progress: 0,
            });
          }
          break;

        case "stage_progress":
          if (msg.stage) {
            updateStage(msg.stage, {
              progress: msg.progress,
            });
          }
          break;

        case "stage_complete":
          if (msg.stage) {
            updateStage(msg.stage, {
              status: "complete",
              progress: 1,
              result: msg.result,
              completedAt: msg.timestamp ?? new Date().toISOString(),
            });
          }
          break;

        case "stage_error":
          if (msg.stage) {
            updateStage(msg.stage, {
              status: "error",
              result: msg.result,
            });
          }
          break;

        case "pipeline_complete":
          setIsComplete(true);
          setSummary(
            msg.summary ?? {
              total_runtime_seconds: msg.total_runtime_seconds,
              result: msg.result,
            },
          );
          break;

        case "pipeline_failed":
          setIsComplete(true);
          setError(msg.error ?? "Pipeline failed");
          break;

        case "status_change":
          if (msg.status === "completed") {
            setIsComplete(true);
            setSummary(msg as unknown as Record<string, unknown>);
          } else if (msg.status === "failed") {
            setIsComplete(true);
            setError(msg.error ?? "Pipeline failed");
          }
          break;

        case "error":
          setError(msg.detail ?? "Unknown error");
          break;
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId, updateStage]);

  return { stages, isConnected, isComplete, error, summary };
}
