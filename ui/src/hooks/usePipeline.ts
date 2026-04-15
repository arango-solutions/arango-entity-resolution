import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getPipelineStatus,
  getPipelineHistory,
  runPipeline,
  type PipelineConfig,
} from "../api/pipeline";

export function usePipelineStatus(collection: string | null) {
  return useQuery({
    queryKey: ["pipeline-status", collection],
    queryFn: () => getPipelineStatus(collection!),
    enabled: !!collection,
  });
}

export function usePipelineHistory() {
  return useQuery({
    queryKey: ["pipeline-history"],
    queryFn: getPipelineHistory,
  });
}

export function useRunPipeline() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (config: PipelineConfig) => runPipeline(config),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pipeline-status"] });
      void queryClient.invalidateQueries({ queryKey: ["pipeline-history"] });
    },
  });
}
