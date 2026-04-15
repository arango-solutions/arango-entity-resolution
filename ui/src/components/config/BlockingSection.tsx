import { useState } from "react";
import { Plus, X, Lightbulb } from "lucide-react";
import { recommendBlocking } from "../../api/config";
import { LoadingSpinner } from "../shared/LoadingSpinner";

const STRATEGIES = [
  "exact",
  "bm25",
  "vector",
  "geographic",
  "lsh",
  "graph_traversal",
  "shard_parallel",
] as const;

interface BlockingSectionProps {
  strategy: string;
  fields: string[];
  maxBlockSize: number;
  onStrategyChange: (value: string) => void;
  onFieldsChange: (fields: string[]) => void;
  onMaxBlockSizeChange: (value: number) => void;
  collectionName: string;
}

export function BlockingSection({
  strategy,
  fields,
  maxBlockSize,
  onStrategyChange,
  onFieldsChange,
  onMaxBlockSizeChange,
  collectionName,
}: BlockingSectionProps) {
  const [recommendations, setRecommendations] = useState<string[]>([]);
  const [recLoading, setRecLoading] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);

  const addField = () => onFieldsChange([...fields, ""]);
  const removeField = (idx: number) =>
    onFieldsChange(fields.filter((_, i) => i !== idx));
  const updateField = (idx: number, value: string) =>
    onFieldsChange(fields.map((f, i) => (i === idx ? value : f)));

  const handleRecommend = async () => {
    if (!collectionName) return;
    setRecLoading(true);
    setRecError(null);
    try {
      const result = await recommendBlocking({ collection: collectionName });
      setRecommendations(result.blocking_keys ?? []);
    } catch (err) {
      setRecError(
        err instanceof Error ? err.message : "Failed to get recommendations",
      );
    } finally {
      setRecLoading(false);
    }
  };

  const addRecommendedField = (field: string) => {
    if (!fields.includes(field)) {
      onFieldsChange([...fields, field]);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700">
          Strategy
        </label>
        <select
          value={strategy}
          onChange={(e) => onStrategyChange(e.target.value)}
          className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
        >
          {STRATEGIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium text-gray-700">
          Fields
        </label>
        <div className="space-y-2">
          {fields.map((field, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="text"
                value={field}
                onChange={(e) => updateField(idx, e.target.value)}
                placeholder="Field name"
                className="block flex-1 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => removeField(idx)}
                className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500"
                title="Remove field"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={addField}
          className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-700"
        >
          <Plus className="h-4 w-4" />
          Add Field
        </button>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700">
          Max Block Size
        </label>
        <input
          type="number"
          value={maxBlockSize}
          onChange={(e) => onMaxBlockSizeChange(parseInt(e.target.value) || 0)}
          min={1}
          className="mt-1 block w-32 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
        />
      </div>

      <div>
        <button
          type="button"
          onClick={handleRecommend}
          disabled={!collectionName || recLoading}
          className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
        >
          <Lightbulb className="h-4 w-4" />
          Get Recommendations
          {recLoading && <LoadingSpinner size="sm" />}
        </button>
      </div>

      {recError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {recError}
        </div>
      )}

      {recommendations.length > 0 && (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-3">
          <p className="mb-2 text-xs font-medium text-indigo-700">
            Recommended fields — click to add:
          </p>
          <div className="flex flex-wrap gap-2">
            {recommendations.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => addRecommendedField(f)}
                disabled={fields.includes(f)}
                className="rounded-full border border-indigo-300 bg-white px-3 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-40"
              >
                + {f}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
