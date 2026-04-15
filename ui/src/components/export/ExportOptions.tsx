interface ExportOptionsValue {
  format: "json" | "csv";
  limit: number | null;
  includeGoldenRecords: boolean;
  includeProvenance: boolean;
}

interface ExportOptionsProps {
  value: ExportOptionsValue;
  onChange: (value: ExportOptionsValue) => void;
}

export type { ExportOptionsValue };

export function ExportOptions({ value, onChange }: ExportOptionsProps) {
  return (
    <div className="space-y-5">
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-gray-700">
          Format
        </legend>
        <div className="flex gap-4">
          {(["json", "csv"] as const).map((fmt) => (
            <label
              key={fmt}
              className="flex cursor-pointer items-center gap-2 text-sm"
            >
              <input
                type="radio"
                name="export-format"
                value={fmt}
                checked={value.format === fmt}
                onChange={() => onChange({ ...value, format: fmt })}
                className="text-indigo-600 focus:ring-indigo-500"
              />
              <span className="uppercase text-gray-700">{fmt}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Limit (clusters)
        </label>
        <input
          type="number"
          min={1}
          placeholder="All"
          value={value.limit ?? ""}
          onChange={(e) =>
            onChange({
              ...value,
              limit: e.target.value ? Number(e.target.value) : null,
            })
          }
          className="block w-40 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <p className="mt-1 text-xs text-gray-500">
          Leave empty to export all clusters
        </p>
      </div>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium text-gray-700">
          Include
        </legend>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={value.includeGoldenRecords}
            onChange={(e) =>
              onChange({ ...value, includeGoldenRecords: e.target.checked })
            }
            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
          Golden records
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={value.includeProvenance}
            onChange={(e) =>
              onChange({ ...value, includeProvenance: e.target.checked })
            }
            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
          Provenance data
        </label>
      </fieldset>
    </div>
  );
}
