import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Trophy } from "lucide-react";
import { getGoldenRecord, getProvenance } from "../api/golden";
import { GoldenRecordView } from "../components/golden/GoldenRecordView";
import { SourceRecords } from "../components/golden/SourceRecords";
import { ProvenanceTable } from "../components/golden/ProvenanceTable";
import { LoadingSpinner } from "../components/shared/LoadingSpinner";
import { EmptyState } from "../components/shared/EmptyState";

export function GoldenRecordDetailPage() {
  const { collection, key } = useParams<{
    collection: string;
    key: string;
  }>();

  const goldenQuery = useQuery({
    queryKey: ["golden-record", collection, key],
    queryFn: () => getGoldenRecord(collection!, key!),
    enabled: !!collection && !!key,
  });

  const provenanceQuery = useQuery({
    queryKey: ["golden-provenance", collection, key],
    queryFn: () => getProvenance(collection!, key!),
    enabled: !!collection && !!key,
  });

  if (!collection || !key) {
    return (
      <EmptyState
        icon={Trophy}
        title="Missing parameters"
        description="Collection and key are required to view a golden record."
      />
    );
  }

  if (goldenQuery.isLoading || provenanceQuery.isLoading) {
    return <LoadingSpinner className="py-16" size="lg" />;
  }

  if (goldenQuery.error) {
    return (
      <div className="rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
        {goldenQuery.error instanceof Error
          ? goldenQuery.error.message
          : "Failed to load golden record"}
      </div>
    );
  }

  const goldenRecord = goldenQuery.data;
  if (!goldenRecord) {
    return (
      <EmptyState
        icon={Trophy}
        title="Golden record not found"
        description={`No golden record found for key "${key}" in ${collection}.`}
      />
    );
  }

  const provenanceData = provenanceQuery.data as
    | {
        golden_record?: Record<string, unknown>;
        source_records?: Record<string, unknown>[];
        merged_keys?: string[];
      }
    | Record<string, unknown>[]
    | undefined;

  const sourceRecords = Array.isArray(provenanceData)
    ? provenanceData
    : provenanceData?.source_records ?? [];

  const provenance = (goldenRecord.provenance ?? {}) as Record<
    string,
    { source: string; confidence: number }
  >;

  const raw = goldenRecord as unknown as Record<string, unknown>;
  const { _key: _k, _id, _rev, _merged_keys, _strategy, provenance: _p, ...recordFields } =
    raw as Record<string, unknown> & {
      _key?: string;
      _id?: string;
      _rev?: string;
      _merged_keys?: string[];
      _strategy?: string;
      provenance?: Record<string, { source: string; confidence: number }>;
    };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          to="/golden"
          className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="text-lg font-semibold text-gray-900">
            Golden Record — {key}
          </h1>
          <p className="text-sm text-gray-500">
            Collection: {collection}
            {_strategy && <> · Strategy: {_strategy}</>}
          </p>
        </div>
      </div>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-gray-900">
          Merged Fields
        </h2>
        <GoldenRecordView
          goldenRecord={recordFields}
          provenance={provenance}
          sources={sourceRecords as Record<string, unknown>[]}
        />
      </section>

      {sourceRecords.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">
            Source Records ({sourceRecords.length})
          </h2>
          <SourceRecords
            sourceRecords={
              sourceRecords as {
                source?: string;
                record_key?: string;
                _key?: string;
                _source?: string;
                ingested_at?: string;
                confidence?: number;
                original_record?: Record<string, unknown>;
              }[]
            }
          />
        </section>
      )}

      {Object.keys(provenance).length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">
            Field Provenance
          </h2>
          <ProvenanceTable provenance={provenance} />
        </section>
      )}
    </div>
  );
}
