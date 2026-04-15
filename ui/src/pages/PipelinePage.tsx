import { Play } from "lucide-react";
import { EmptyState } from "../components/shared/EmptyState";
import { useSelectedCollection } from "../contexts/CollectionContext";
import { PipelineRunner } from "../components/pipeline/PipelineRunner";

export function PipelinePage() {
  const { selectedCollection } = useSelectedCollection();

  if (!selectedCollection) {
    return (
      <EmptyState
        icon={Play}
        title="No collection selected"
        description="Select a collection from the sidebar to run or monitor pipelines."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PipelineRunner />
    </div>
  );
}
