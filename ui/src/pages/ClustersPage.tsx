import { Network } from "lucide-react";
import { EmptyState } from "../components/shared/EmptyState";
import { ClusterList } from "../components/clusters/ClusterList";
import { useSelectedCollection } from "../contexts/CollectionContext";

export function ClustersPage() {
  const { selectedCollection } = useSelectedCollection();

  if (!selectedCollection) {
    return (
      <EmptyState
        icon={Network}
        title="No collection selected"
        description="Select a collection from the sidebar to browse entity clusters."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Clusters</h1>
        <p className="mt-1 text-sm text-gray-500">
          Browse entity clusters for{" "}
          <span className="font-medium text-gray-700">
            {selectedCollection}
          </span>{" "}
          with quality scores, similarity metrics, and density.
        </p>
      </div>
      <ClusterList collection={selectedCollection} />
    </div>
  );
}
