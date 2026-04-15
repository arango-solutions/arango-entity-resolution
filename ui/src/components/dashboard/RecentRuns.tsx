import { PipelineHistory } from "../pipeline/PipelineHistory";

export function RecentRuns() {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <h3 className="mb-4 text-sm font-medium text-gray-700">
        Recent Pipeline Runs
      </h3>
      <PipelineHistory limit={5} />
    </div>
  );
}
