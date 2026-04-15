import { useState } from "react";
import { Database, BarChart3 } from "lucide-react";
import { useCollections, useCollectionProfile } from "../../hooks/useCollections";
import { LoadingSpinner } from "../shared/LoadingSpinner";

interface CollectionSectionProps {
  entityType: string;
  collectionName: string;
  onEntityTypeChange: (value: string) => void;
  onCollectionChange: (value: string) => void;
}

export function CollectionSection({
  entityType,
  collectionName,
  onEntityTypeChange,
  onCollectionChange,
}: CollectionSectionProps) {
  const { data: collections, isLoading: collectionsLoading } = useCollections();
  const [showProfile, setShowProfile] = useState(false);
  const {
    data: profile,
    isLoading: profileLoading,
    refetch: fetchProfile,
  } = useCollectionProfile(showProfile ? collectionName : null);

  const selectedCol = collections?.find((c) => c.name === collectionName);

  const handleProfile = () => {
    if (!collectionName) return;
    setShowProfile(true);
    fetchProfile();
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700">
          Entity Type
        </label>
        <input
          type="text"
          value={entityType}
          onChange={(e) => onEntityTypeChange(e.target.value)}
          placeholder="e.g. company, person, product"
          className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700">
          Collection
        </label>
        <div className="mt-1 flex items-center gap-3">
          <div className="relative flex-1">
            <Database className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <select
              value={collectionName}
              onChange={(e) => {
                onCollectionChange(e.target.value);
                setShowProfile(false);
              }}
              disabled={collectionsLoading}
              className="block w-full appearance-none rounded-md border border-gray-300 bg-white py-2 pl-9 pr-8 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none disabled:opacity-50"
            >
              <option value="">Select a collection...</option>
              {collections?.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          {selectedCol && (
            <span className="shrink-0 text-sm text-gray-500">
              {selectedCol.count.toLocaleString()} docs
            </span>
          )}
        </div>
      </div>

      <div>
        <button
          type="button"
          onClick={handleProfile}
          disabled={!collectionName || profileLoading}
          className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
        >
          <BarChart3 className="h-4 w-4" />
          Profile Dataset
          {profileLoading && <LoadingSpinner size="sm" />}
        </button>
      </div>

      {showProfile && profile && (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Field
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Null Rate
                </th>
                <th className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Distinct Count
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {Object.entries(profile.null_rates).map(([field, rate]) => {
                const stats = profile.field_stats[field] as
                  | Record<string, unknown>
                  | undefined;
                const distinct =
                  stats && typeof stats.distinct_count === "number"
                    ? stats.distinct_count
                    : "—";
                return (
                  <tr key={field}>
                    <td className="whitespace-nowrap px-4 py-2 font-medium text-gray-700">
                      {field}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-gray-600">
                      {(rate * 100).toFixed(1)}%
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-gray-600">
                      {typeof distinct === "number"
                        ? distinct.toLocaleString()
                        : distinct}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
