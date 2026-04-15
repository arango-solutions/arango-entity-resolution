import { useState, Fragment } from "react";
import { AlertTriangle } from "lucide-react";
import { ConflictResolver, type ConflictAlternative } from "./ConflictResolver";
import { ScoreBadge } from "../shared/ScoreBadge";

interface FieldEntry {
  field: string;
  value: unknown;
  source: string;
  confidence: number;
  hasConflict: boolean;
  alternatives?: ConflictAlternative[];
}

interface GoldenRecordViewProps {
  goldenRecord: Record<string, unknown>;
  provenance?: Record<string, { source: string; confidence: number }>;
  conflicts?: string[];
  sources?: Record<string, unknown>[];
  onResolveConflict?: (
    fieldName: string,
    value: unknown,
    source: string,
  ) => void;
}

function flattenObject(
  obj: Record<string, unknown>,
  prefix = "",
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (key.startsWith("_")) continue;
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      Object.assign(
        result,
        flattenObject(value as Record<string, unknown>, fullKey),
      );
    } else {
      result[fullKey] = value;
    }
  }
  return result;
}

function buildAlternatives(
  field: string,
  sources: Record<string, unknown>[],
): ConflictAlternative[] {
  const alts: ConflictAlternative[] = [];
  const seen = new Set<string>();

  for (const src of sources) {
    const flat = flattenObject(src as Record<string, unknown>);
    const val = flat[field];
    if (val === undefined) continue;
    const key = `${src._source ?? "unknown"}::${String(val)}`;
    if (seen.has(key)) continue;
    seen.add(key);

    alts.push({
      value: val,
      source: String(src._source ?? src._key ?? "unknown"),
      updatedAt: src._updated_at
        ? String(src._updated_at)
        : src.updated_at
          ? String(src.updated_at)
          : undefined,
    });
  }
  return alts;
}

export function GoldenRecordView({
  goldenRecord,
  provenance = {},
  conflicts = [],
  sources = [],
  onResolveConflict,
}: GoldenRecordViewProps) {
  const [expandedConflict, setExpandedConflict] = useState<string | null>(null);

  const flatFields = flattenObject(goldenRecord);
  const conflictSet = new Set(conflicts);

  const entries: FieldEntry[] = Object.entries(flatFields).map(
    ([field, value]) => {
      const prov = provenance[field];
      return {
        field,
        value,
        source: prov?.source ?? "—",
        confidence: prov?.confidence ?? 0,
        hasConflict: conflictSet.has(field),
        alternatives:
          conflictSet.has(field) && sources.length > 0
            ? buildAlternatives(field, sources)
            : undefined,
      };
    },
  );

  if (entries.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-400">
        No fields in golden record
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
              Field
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
              Value
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
              Source
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium tracking-wider text-gray-500 uppercase">
              Confidence
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {entries.map((entry) => (
            <Fragment key={entry.field}>
              <tr
                className={
                  entry.hasConflict
                    ? "cursor-pointer bg-amber-50/50 hover:bg-amber-50"
                    : "hover:bg-gray-50"
                }
                onClick={
                  entry.hasConflict
                    ? () =>
                        setExpandedConflict(
                          expandedConflict === entry.field
                            ? null
                            : entry.field,
                        )
                    : undefined
                }
              >
                <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-700">
                  <div className="flex items-center gap-1.5">
                    {entry.field}
                    {entry.hasConflict && (
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-gray-700">
                  {formatValue(entry.value)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                  {entry.source}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  {entry.confidence > 0 ? (
                    <ScoreBadge score={entry.confidence} />
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </td>
              </tr>

              {entry.hasConflict &&
                expandedConflict === entry.field &&
                entry.alternatives && (
                  <ConflictResolver
                    fieldName={entry.field}
                    alternatives={entry.alternatives}
                    onResolve={onResolveConflict ?? (() => {})}
                  />
                )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.join(", ");
  return String(value);
}
