import { useState } from "react";
import { Download, FileDown, Loader2 } from "lucide-react";
import { ExportOptions, type ExportOptionsValue } from "./ExportOptions";
import { exportClusters, downloadExport, basename } from "../../api/export";
import { useSelectedCollection } from "../../contexts/CollectionContext";
import { EmptyState } from "../shared/EmptyState";

interface ExportHistoryEntry {
  filename: string;
  collection: string;
  format: string;
  recordCount: number;
  exportedAt: string;
}

export function ExportCenter() {
  const { selectedCollection } = useSelectedCollection();

  const [options, setOptions] = useState<ExportOptionsValue>({
    format: "json",
    limit: null,
    includeGoldenRecords: true,
    includeProvenance: false,
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<ExportHistoryEntry[]>([]);

  if (!selectedCollection) {
    return (
      <EmptyState
        icon={Download}
        title="No collection selected"
        description="Select a collection from the sidebar to export cluster data."
      />
    );
  }

  async function handleExport() {
    if (!selectedCollection) return;
    setLoading(true);
    setError(null);

    try {
      // The backend always writes both JSON and CSV artifacts; the format
      // selector chooses which file to surface first in history.
      const result = await exportClusters(selectedCollection, {
        limit: options.limit,
      });

      const exportedAt = new Date().toLocaleString();
      const files: Array<[string, string]> = [
        ["JSON", result.output_files.json],
        ["CSV", result.output_files.csv],
      ];
      if (options.format === "csv") files.reverse();

      const entries: ExportHistoryEntry[] = files
        .filter(([, path]) => Boolean(path))
        .map(([format, path]) => ({
          filename: basename(path),
          collection: selectedCollection,
          format,
          recordCount: result.clusters_exported,
          exportedAt,
        }));

      setHistory((prev) => [...entries, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h3 className="mb-4 text-sm font-semibold text-gray-900">
          Export Configuration
        </h3>

        <ExportOptions value={options} onChange={setOptions} />

        <div className="mt-6">
          <button
            onClick={handleExport}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            {loading ? "Exporting…" : "Export"}
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h3 className="mb-4 text-sm font-semibold text-gray-900">
          Export History
        </h3>

        {history.length === 0 ? (
          <p className="py-4 text-center text-sm text-gray-400">
            No exports yet. Configure options above and click Export.
          </p>
        ) : (
          <div className="divide-y divide-gray-100">
            {history.map((entry, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between py-3 text-sm"
              >
                <div className="flex items-center gap-3">
                  <FileDown className="h-4 w-4 text-gray-400" />
                  <div>
                    <p className="font-medium text-gray-800">
                      {entry.filename}
                    </p>
                    <p className="text-xs text-gray-500">
                      {entry.format} · {entry.recordCount} clusters ·{" "}
                      {entry.exportedAt}
                    </p>
                  </div>
                </div>
                <a
                  href={downloadExport(entry.collection, entry.filename)}
                  download
                  className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                >
                  Download
                </a>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
