import { useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { EmptyState } from "../components/shared/EmptyState";
import { useSelectedCollection } from "../contexts/CollectionContext";
import { ThresholdBanner } from "../components/review/ThresholdBanner";
import { ReviewQueue } from "../components/review/ReviewQueue";
import { SuspectClusters } from "../components/clusters/SuspectClusters";
import { cn } from "../lib/cn";

type Tab = "queue" | "suspect";

export function ReviewPage() {
  const { selectedCollection } = useSelectedCollection();
  const [tab, setTab] = useState<Tab>("queue");

  if (!selectedCollection) {
    return (
      <EmptyState
        icon={ClipboardCheck}
        title="No collection selected"
        description="Select a collection from the sidebar to view the review queue."
      />
    );
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "queue", label: "Pair queue" },
    { id: "suspect", label: "Suspect clusters" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Review</h1>
        <p className="mt-1 text-sm text-gray-500">
          Review ambiguous match pairs and repair low-quality clusters flagged by
          the repair queue.
        </p>
      </div>

      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-6">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "border-b-2 px-1 py-2.5 text-sm font-medium",
                tab === t.id
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700",
              )}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {tab === "queue" ? (
        <>
          <ThresholdBanner collection={selectedCollection} />
          <ReviewQueue collection={selectedCollection} />
        </>
      ) : (
        <SuspectClusters collection={selectedCollection} />
      )}
    </div>
  );
}
