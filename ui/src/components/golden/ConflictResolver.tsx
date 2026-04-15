import { useState } from "react";

export interface ConflictAlternative {
  value: unknown;
  source: string;
  updatedAt?: string;
}

interface ConflictResolverProps {
  fieldName: string;
  alternatives: ConflictAlternative[];
  onResolve: (fieldName: string, value: unknown, source: string) => void;
}

export function ConflictResolver({
  fieldName,
  alternatives,
  onResolve,
}: ConflictResolverProps) {
  const [manualValue, setManualValue] = useState("");

  return (
    <tr>
      <td colSpan={4} className="px-0 py-0">
        <div className="border-t border-amber-200 bg-amber-50 px-6 py-4">
          <p className="mb-3 text-sm font-medium text-amber-800">
            Conflict: <span className="font-semibold">{fieldName}</span> —
            multiple sources disagree
          </p>

          <div className="space-y-2">
            {alternatives.map((alt, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between rounded-md border border-amber-200 bg-white px-4 py-2.5 text-sm"
              >
                <div className="flex flex-1 items-center gap-4">
                  <span className="font-medium text-gray-700">
                    {alt.source}
                  </span>
                  <span className="text-gray-600">
                    {String(alt.value ?? "—")}
                  </span>
                  {alt.updatedAt && (
                    <span className="text-xs text-gray-400">
                      {alt.updatedAt}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => onResolve(fieldName, alt.value, alt.source)}
                  className="ml-4 shrink-0 rounded-md border border-amber-300 bg-amber-100 px-3 py-1 text-xs font-medium text-amber-800 hover:bg-amber-200"
                >
                  Use this
                </button>
              </div>
            ))}
          </div>

          <div className="mt-3 flex items-center gap-2">
            <span className="text-xs font-medium text-gray-600">
              Manual Override:
            </span>
            <input
              type="text"
              value={manualValue}
              onChange={(e) => setManualValue(e.target.value)}
              placeholder="Enter custom value…"
              className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <button
              onClick={() => {
                if (manualValue.trim()) {
                  onResolve(fieldName, manualValue.trim(), "manual_override");
                  setManualValue("");
                }
              }}
              disabled={!manualValue.trim()}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
            >
              Apply
            </button>
          </div>
        </div>
      </td>
    </tr>
  );
}
