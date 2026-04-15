import { Download } from "lucide-react";
import { EmptyState } from "../components/shared/EmptyState";
import { ExportCenter } from "../components/export/ExportCenter";
import { useSelectedCollection } from "../contexts/CollectionContext";

export function ExportPage() {
  const { selectedCollection } = useSelectedCollection();

  if (!selectedCollection) {
    return (
      <EmptyState
        icon={Download}
        title="No collection selected"
        description="Select a collection from the sidebar to export cluster data."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">Export Center</h1>
        <p className="mt-1 text-sm text-gray-500">
          Export entity clusters and resolution results from{" "}
          <span className="font-medium">{selectedCollection}</span> as JSON or
          CSV. Download previously exported artifacts below.
        </p>
      </div>

      <ExportCenter />
    </div>
  );
}
