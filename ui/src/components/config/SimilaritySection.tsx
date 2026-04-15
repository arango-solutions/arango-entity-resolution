import { Plus } from "lucide-react";
import { WeightSlider } from "./WeightSlider";

const ALGORITHMS = [
  "jaro_winkler",
  "levenshtein",
  "jaccard",
  "cosine",
] as const;

interface FieldWeight {
  field: string;
  weight: number;
}

interface SimilaritySectionProps {
  algorithm: string;
  threshold: number;
  fieldWeights: FieldWeight[];
  onAlgorithmChange: (value: string) => void;
  onThresholdChange: (value: number) => void;
  onFieldWeightsChange: (weights: FieldWeight[]) => void;
}

export function SimilaritySection({
  algorithm,
  threshold,
  fieldWeights,
  onAlgorithmChange,
  onThresholdChange,
  onFieldWeightsChange,
}: SimilaritySectionProps) {
  const addFieldWeight = () => {
    onFieldWeightsChange([...fieldWeights, { field: "", weight: 0.5 }]);
  };

  const removeFieldWeight = (idx: number) => {
    onFieldWeightsChange(fieldWeights.filter((_, i) => i !== idx));
  };

  const updateFieldName = (idx: number, name: string) => {
    onFieldWeightsChange(
      fieldWeights.map((fw, i) => (i === idx ? { ...fw, field: name } : fw)),
    );
  };

  const updateFieldWeightValue = (idx: number, weight: number) => {
    onFieldWeightsChange(
      fieldWeights.map((fw, i) => (i === idx ? { ...fw, weight } : fw)),
    );
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700">
          Algorithm
        </label>
        <select
          value={algorithm}
          onChange={(e) => onAlgorithmChange(e.target.value)}
          className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
        >
          {ALGORITHMS.map((a) => (
            <option key={a} value={a}>
              {a.replace("_", "-")}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Threshold
        </label>
        <WeightSlider
          label="Threshold"
          value={threshold}
          onChange={onThresholdChange}
          min={0}
          max={1}
          step={0.01}
        />
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium text-gray-700">
          Field Weights
        </label>
        <div className="space-y-2">
          {fieldWeights.map((fw, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="text"
                value={fw.field}
                onChange={(e) => updateFieldName(idx, e.target.value)}
                placeholder="Field name"
                className="w-28 shrink-0 rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
              />
              <WeightSlider
                label=""
                value={fw.weight}
                onChange={(v) => updateFieldWeightValue(idx, v)}
                onRemove={() => removeFieldWeight(idx)}
                className="flex-1"
              />
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={addFieldWeight}
          className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-indigo-600 hover:text-indigo-700"
        >
          <Plus className="h-4 w-4" />
          Add Field Weight
        </button>
      </div>

      <div>
        <button
          type="button"
          disabled
          className="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm opacity-50"
          title="Requires labeled data"
        >
          Estimate Weights
        </button>
        <p className="mt-1 text-xs text-gray-500">
          Requires labeled training data to estimate optimal weights.
        </p>
      </div>
    </div>
  );
}
