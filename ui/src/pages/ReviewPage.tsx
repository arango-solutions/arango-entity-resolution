import { ClipboardCheck } from "lucide-react";
import { EmptyState } from "../components/shared/EmptyState";
import { useSelectedCollection } from "../contexts/CollectionContext";
import { ThresholdBanner } from "../components/review/ThresholdBanner";
import { ReviewQueue } from "../components/review/ReviewQueue";

export function ReviewPage() {
  const { selectedCollection } = useSelectedCollection();

  if (!selectedCollection) {
    return (
      <EmptyState
        icon={ClipboardCheck}
        title="No collection selected"
        description="Select a collection from the sidebar to view the review queue."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Review Queue</h1>
        <p className="mt-1 text-sm text-gray-500">
          Review ambiguous match pairs, compare records side-by-side, and submit
          verdicts. Pairs scoring between the low and high thresholds are queued
          for human judgment.
        </p>
      </div>

      <ThresholdBanner collection={selectedCollection} />
      <ReviewQueue collection={selectedCollection} />
    </div>
  );
}
