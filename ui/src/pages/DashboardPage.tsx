import { LayoutDashboard } from "lucide-react";
import { EmptyState } from "../components/shared/EmptyState";
import { useSelectedCollection } from "../contexts/CollectionContext";
import { StatsGrid } from "../components/dashboard/StatsGrid";
import { DistributionChart } from "../components/dashboard/DistributionChart";
import { RecentRuns } from "../components/dashboard/RecentRuns";

export function DashboardPage() {
  const { selectedCollection } = useSelectedCollection();

  if (!selectedCollection) {
    return (
      <EmptyState
        icon={LayoutDashboard}
        title="Welcome to Entity Resolution"
        description="Select a collection from the sidebar to view your dashboard."
      />
    );
  }

  return (
    <div className="space-y-8">
      <StatsGrid />
      <DistributionChart collection={selectedCollection} />
      <RecentRuns />
    </div>
  );
}
