import { Eraser } from "lucide-react";

interface RecordInputFormProps {
  fields: string[];
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
}

export function RecordInputForm({
  fields,
  values,
  onChange,
}: RecordInputFormProps) {
  if (fields.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50/50 px-4 py-8 text-center text-sm text-gray-500">
        Select a collection first to load its fields.
      </div>
    );
  }

  const updateField = (field: string, value: string) => {
    onChange({ ...values, [field]: value });
  };

  const clearAll = () => {
    const cleared: Record<string, string> = {};
    for (const f of fields) cleared[f] = "";
    onChange(cleared);
  };

  return (
    <div className="space-y-3">
      {fields.map((field) => (
        <div key={field}>
          <label className="block text-sm font-medium text-gray-700">
            {field}
          </label>
          <input
            type="text"
            value={values[field] ?? ""}
            onChange={(e) => updateField(field, e.target.value)}
            placeholder={`Enter ${field}...`}
            className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-gray-400 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none"
          />
        </div>
      ))}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={clearAll}
          className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700"
        >
          <Eraser className="h-3.5 w-3.5" />
          Clear All
        </button>
      </div>
    </div>
  );
}
