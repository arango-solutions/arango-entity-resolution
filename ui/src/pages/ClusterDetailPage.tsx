import { useParams } from "react-router-dom";
import { Network } from "lucide-react";
import { EmptyState } from "../components/shared/EmptyState";
import { ClusterDetail } from "../components/clusters/ClusterDetail";

export function ClusterDetailPage() {
  const { collection, key } = useParams<{
    collection: string;
    key: string;
  }>();

  if (!collection || !key) {
    return (
      <EmptyState
        icon={Network}
        title="Missing parameters"
        description="Collection and cluster key are required."
      />
    );
  }

  return <ClusterDetail />;
}
