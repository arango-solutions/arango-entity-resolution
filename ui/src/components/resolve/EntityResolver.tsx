import { useState, useEffect, useCallback } from "react";
import { Search, X, Database } from "lucide-react";
import { useSelectedCollection } from "../../contexts/CollectionContext";
import { useCollections } from "../../hooks/useCollections";
import { getCollectionSample } from "../../api/collections";
import { resolveEntity, type ResolveMatch } from "../../api/resolve";
import { RecordInputForm } from "./RecordInputForm";
import { MatchResult } from "./MatchResult";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { EmptyState } from "../shared/EmptyState";

export function EntityResolver() {
  const { selectedCollection, setSelectedCollection } =
    useSelectedCollection();
  const { data: collections } = useCollections();

  const [fields, setFields] = useState<string[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [matches, setMatches] = useState<ResolveMatch[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasResolved, setHasResolved] = useState(false);

  const loadFields = useCallback(async (collection: string) => {
    try {
      const sample = await getCollectionSample(collection);
      if (sample.sample && sample.sample.length > 0) {
        const doc = sample.sample[0] as Record<string, unknown>;
        const fieldNames = Object.keys(doc).filter(
          (k) => !k.startsWith("_"),
        );
        setFields(fieldNames);
        const init: Record<string, string> = {};
        for (const f of fieldNames) init[f] = "";
        setValues(init);
      }
    } catch {
      setFields([]);
    }
  }, []);

  useEffect(() => {
    if (selectedCollection) {
      loadFields(selectedCollection);
      setMatches([]);
      setHasResolved(false);
      setError(null);
    } else {
      setFields([]);
      setValues({});
    }
  }, [selectedCollection, loadFields]);

  const handleResolve = async () => {
    if (!selectedCollection) return;

    const record: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(values)) {
      if (v.trim()) record[k] = v.trim();
    }

    if (Object.keys(record).length === 0) {
      setError("Enter at least one field value.");
      return;
    }

    setLoading(true);
    setError(null);
    setMatches([]);
    try {
      const result = await resolveEntity(
        selectedCollection,
        record,
        Object.keys(record),
      );
      const resolved = result.matches ?? (result as unknown as ResolveMatch[]);
      const sorted = Array.isArray(resolved)
        ? [...resolved].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
        : [];
      setMatches(sorted);
      setHasResolved(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Resolution failed",
      );
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setMatches([]);
    setHasResolved(false);
    setError(null);
  };

  return (
    <div className="space-y-6">
      {/* Collection selector */}
      <div>
        <label className="block text-sm font-medium text-gray-700">
          Collection
        </label>
        <div className="relative mt-1">
          <Database className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <select
            value={selectedCollection ?? ""}
            onChange={(e) =>
              setSelectedCollection(e.target.value || null)
            }
            className="block w-full appearance-none rounded-md border border-gray-300 bg-white py-2 pl-9 pr-8 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
          >
            <option value="">Select a collection...</option>
            {collections?.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} ({c.count.toLocaleString()} docs)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Input form */}
      {selectedCollection && (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">
            Input Record
          </h3>
          <RecordInputForm
            fields={fields}
            values={values}
            onChange={setValues}
          />
          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              onClick={handleResolve}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
            >
              <Search className="h-4 w-4" />
              Resolve
              {loading && <LoadingSpinner size="sm" />}
            </button>
            {hasResolved && (
              <button
                type="button"
                onClick={handleClear}
                className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700"
              >
                <X className="h-4 w-4" />
                Clear Results
              </button>
            )}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && <LoadingSpinner className="py-8" />}

      {/* Results */}
      {!loading && hasResolved && (
        <div>
          <h3 className="mb-3 text-sm font-semibold text-gray-900">
            Matches ({matches.length} found)
          </h3>
          {matches.length === 0 ? (
            <EmptyState
              icon={Search}
              title="No matches found"
              description="Try adjusting the input values or using a different collection."
            />
          ) : (
            <div className="space-y-3">
              {matches.map((m, idx) => (
                <MatchResult
                  key={m.key ?? idx}
                  rank={idx + 1}
                  matchKey={m.key ?? `match-${idx}`}
                  score={m.score ?? 0}
                  record={m.record ?? {}}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* No collection selected */}
      {!selectedCollection && (
        <EmptyState
          icon={Search}
          title="No collection selected"
          description="Select a collection from the dropdown above to start resolving entities."
        />
      )}
    </div>
  );
}
