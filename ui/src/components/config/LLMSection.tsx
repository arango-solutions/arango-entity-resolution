import { cn } from "../../lib/cn";

const PROVIDERS = ["ollama", "openrouter", "openai", "anthropic"] as const;

interface LLMSectionProps {
  enabled: boolean;
  provider: string;
  model: string;
  lowThreshold: number;
  highThreshold: number;
  onEnabledChange: (value: boolean) => void;
  onProviderChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onLowThresholdChange: (value: number) => void;
  onHighThresholdChange: (value: number) => void;
}

export function LLMSection({
  enabled,
  provider,
  model,
  lowThreshold,
  highThreshold,
  onEnabledChange,
  onProviderChange,
  onModelChange,
  onLowThresholdChange,
  onHighThresholdChange,
}: LLMSectionProps) {
  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onEnabledChange(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
        />
        <span className="text-sm font-medium text-gray-700">
          Enable LLM Curation
        </span>
      </label>

      <div
        className={cn(
          "space-y-4 transition-opacity",
          !enabled && "pointer-events-none opacity-40",
        )}
      >
        <div>
          <label className="block text-sm font-medium text-gray-700">
            Provider
          </label>
          <select
            value={provider}
            onChange={(e) => onProviderChange(e.target.value)}
            disabled={!enabled}
            className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none disabled:opacity-50"
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Model
          </label>
          <input
            type="text"
            value={model}
            onChange={(e) => onModelChange(e.target.value)}
            disabled={!enabled}
            placeholder="e.g. llama3.1:8b"
            className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none disabled:opacity-50"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Low Threshold
            </label>
            <input
              type="number"
              value={lowThreshold}
              onChange={(e) =>
                onLowThresholdChange(parseFloat(e.target.value) || 0)
              }
              step={0.01}
              min={0}
              max={1}
              disabled={!enabled}
              className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">
              High Threshold
            </label>
            <input
              type="number"
              value={highThreshold}
              onChange={(e) =>
                onHighThresholdChange(parseFloat(e.target.value) || 0)
              }
              step={0.01}
              min={0}
              max={1}
              disabled={!enabled}
              className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none disabled:opacity-50"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
