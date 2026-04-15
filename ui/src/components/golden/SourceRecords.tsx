import { Fragment } from "react";
import { ScoreBadge } from "../shared/ScoreBadge";

interface SourceRecord {
  source?: string;
  record_key?: string;
  _key?: string;
  _source?: string;
  ingested_at?: string;
  confidence?: number;
  original_record?: Record<string, unknown>;
  [key: string]: unknown;
}

interface SourceRecordsProps {
  sourceRecords: SourceRecord[];
}

function extractDisplayFields(record: SourceRecord) {
  const skip = new Set([
    "source",
    "record_key",
    "_key",
    "_id",
    "_rev",
    "_source",
    "ingested_at",
    "confidence",
    "original_record",
  ]);
  const fields: Record<string, unknown> = {};

  if (record.original_record) {
    for (const [k, v] of Object.entries(record.original_record)) {
      if (!k.startsWith("_")) fields[k] = v;
    }
  } else {
    for (const [k, v] of Object.entries(record)) {
      if (!skip.has(k) && !k.startsWith("_")) fields[k] = v;
    }
  }
  return fields;
}

export function SourceRecords({ sourceRecords }: SourceRecordsProps) {
  if (sourceRecords.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-gray-400">
        No source records available
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {sourceRecords.map((record, idx) => {
        const sourceName =
          record.source ?? record._source ?? `Source ${idx + 1}`;
        const recordKey = record.record_key ?? record._key ?? `#${idx + 1}`;
        const confidence = record.confidence;
        const ingestedAt = record.ingested_at;
        const displayFields = extractDisplayFields(record);

        return (
          <details
            key={recordKey}
            className="group rounded-lg border border-gray-200 bg-white"
          >
            <summary className="flex cursor-pointer items-center justify-between px-4 py-3 text-sm hover:bg-gray-50">
              <div className="flex items-center gap-3">
                <span className="font-medium text-gray-800">{sourceName}</span>
                <span className="text-gray-500">{recordKey}</span>
                {ingestedAt && (
                  <span className="text-xs text-gray-400">{ingestedAt}</span>
                )}
              </div>
              {confidence != null && <ScoreBadge score={confidence} />}
            </summary>

            <div className="border-t border-gray-100 px-4 py-3">
              {Object.keys(displayFields).length === 0 ? (
                <p className="text-sm italic text-gray-400">
                  No additional fields
                </p>
              ) : (
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                  {Object.entries(displayFields).map(([key, value]) => (
                    <Fragment key={key}>
                      <dt className="font-medium text-gray-600">{key}</dt>
                      <dd className="text-gray-700">
                        {value === null || value === undefined
                          ? "—"
                          : typeof value === "object"
                            ? JSON.stringify(value)
                            : String(value)}
                      </dd>
                    </Fragment>
                  ))}
                </dl>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}
