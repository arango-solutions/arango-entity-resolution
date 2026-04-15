import { FileText, Network, ClipboardCheck, Star } from "lucide-react";
import { StatCard } from "../shared/StatCard";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { useSelectedCollection } from "../../contexts/CollectionContext";
import { usePipelineStatus } from "../../hooks/usePipeline";
import { useReviewStats } from "../../hooks/useReview";

export function StatsGrid() {
  const { selectedCollection } = useSelectedCollection();
  const { data: pipelineStatus, isLoading: pipelineLoading } =
    usePipelineStatus(selectedCollection);
  const { data: reviewStats, isLoading: reviewLoading } =
    useReviewStats(selectedCollection);

  const isLoading = pipelineLoading || reviewLoading;

  if (isLoading) {
    return <LoadingSpinner className="py-8" />;
  }

  const status = pipelineStatus as Record<string, unknown> | undefined;
  const totalDocs =
    typeof status?.["total_documents"] === "number"
      ? status["total_documents"]
      : typeof status?.["document_count"] === "number"
        ? status["document_count"]
        : 0;
  const clusterCount =
    typeof status?.["cluster_count"] === "number"
      ? status["cluster_count"]
      : 0;
  const avgQuality =
    typeof status?.["avg_quality_score"] === "number"
      ? status["avg_quality_score"]
      : null;

  const review = reviewStats as Record<string, unknown> | undefined;
  const pendingReviews =
    typeof review?.["pending"] === "number" ? review["pending"] : 0;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label="Documents"
        value={totalDocs as number}
        icon={FileText}
        accent="indigo"
      />
      <StatCard
        label="Clusters"
        value={clusterCount as number}
        icon={Network}
        accent="green"
      />
      <StatCard
        label="Pending Reviews"
        value={pendingReviews as number}
        icon={ClipboardCheck}
        accent="amber"
      />
      <StatCard
        label="Avg Quality Score"
        value={avgQuality != null ? (avgQuality as number).toFixed(2) : "—"}
        icon={Star}
        accent="indigo"
      />
    </div>
  );
}
