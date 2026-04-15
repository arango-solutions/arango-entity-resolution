interface MergeStrategySelectorProps {
  value: string;
  onChange: (strategy: string) => void;
}

const strategies = [
  {
    value: "most_complete",
    label: "Most Complete",
    description: "Select the most complete value for each field",
  },
  {
    value: "newest",
    label: "Newest",
    description: "Prefer the most recently updated value",
  },
  {
    value: "first",
    label: "First",
    description: "Use the first encountered value",
  },
] as const;

export function MergeStrategySelector({
  value,
  onChange,
}: MergeStrategySelectorProps) {
  const selected = strategies.find((s) => s.value === value);

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-gray-700">
        Merge Strategy
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
      >
        {strategies.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
      {selected && (
        <p className="text-xs text-gray-500">{selected.description}</p>
      )}
    </div>
  );
}
