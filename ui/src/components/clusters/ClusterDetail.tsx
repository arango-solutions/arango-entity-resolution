import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Network, ExternalLink, Search } from "lucide-react";
import { useClusterDetail, useClusterGraph } from "../../hooks/useClusters";
import { ScoreBadge } from "../shared/ScoreBadge";
import { LoadingSpinner } from "../shared/LoadingSpinner";
import { EmptyState } from "../shared/EmptyState";
import { ClusterMembers } from "./ClusterMembers";
import { ClusterGraph } from "./ClusterGraph";
import { ExplainMatchModal } from "./ExplainMatchModal";

interface DetailResult {
  cluster_id: string;
  size: number;
  representative?: string;
  quality_score: number | null;
  density: number | null;
  average_similarity: number | null;
  members: Record<string, unknown>[];
}

interface GraphNodeResult {
  id: string;
  key: string;
  data: Record<string, unknown>;
}

interface GraphEdgeResult {
  source: string;
  target: string;
  similarity: number;
  method?: string;
}

interface GraphResult {
  nodes: GraphNodeResult[];
  edges: GraphEdgeResult[];
}

export function ClusterDetail() {
  const { collection, key } = useParams<{
    collection: string;
    key: string;
  }>();
  const navigate = useNavigate();

  const [selectedEdge, setSelectedEdge] = useState<{
    a: string;
    b: string;
  } | null>(null);
  const [highlightedMember, setHighlightedMember] = useState<string | null>(
    null,
  );

  const { data: rawDetail, isLoading: detailLoading, error: detailError } =
    useClusterDetail(collection ?? null, key ?? null);
  const { data: rawGraph, isLoading: graphLoading } = useClusterGraph(
    collection ?? null,
    key ?? null,
  );

  const detail = rawDetail as unknown as DetailResult | undefined;
  const graph = rawGraph as unknown as GraphResult | undefined;

  if (!collection || !key) {
    return (
      <EmptyState
        icon={Network}
        title="Missing parameters"
        description="Collection and cluster key are required."
      />
    );
  }

  if (detailLoading) {
    return <LoadingSpinner className="py-24" size="lg" />;
  }

  if (detailError) {
    return (
      <EmptyState
        icon={Network}
        title="Error loading cluster"
        description={
          detailError instanceof Error
            ? detailError.message
            : "An error occurred"
        }
      />
    );
  }

  if (!detail) {
    return (
      <EmptyState
        icon={Network}
        title="Cluster not found"
        description={`No cluster with key "${key}" was found.`}
      />
    );
  }

  const handleEdgeClick = (sourceKey: string, targetKey: string) => {
    setSelectedEdge({ a: sourceKey, b: targetKey });
  };

  const handleMemberClick = (memberKey: string) => {
    setHighlightedMember((prev) =>
      prev === memberKey ? null : memberKey,
    );
  };

  return (
    <div className="space-y-4">
      {/* Back button */}
      <button
        onClick={() => navigate("/clusters")}
        className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to clusters
      </button>

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">
            Cluster {detail.representative ?? detail.cluster_id}
          </h2>
          <div className="mt-1 flex items-center gap-3 text-sm text-gray-500">
            <span>{detail.size} members</span>
            <span className="text-gray-300">|</span>
            {detail.quality_score != null && (
              <>
                <span>Quality:</span>
                <ScoreBadge score={detail.quality_score} />
              </>
            )}
            {detail.average_similarity != null && (
              <>
                <span className="text-gray-300">|</span>
                <span>
                  Avg Similarity: {detail.average_similarity.toFixed(2)}
                </span>
              </>
            )}
            {detail.density != null && (
              <>
                <span className="text-gray-300">|</span>
                <span>Density: {detail.density.toFixed(2)}</span>
              </>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <Link
            to={`/golden/${collection}/${key}`}
            className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            View Golden Record
          </Link>
          {selectedEdge && (
            <button
              onClick={() =>
                setSelectedEdge({
                  a: selectedEdge.a,
                  b: selectedEdge.b,
                })
              }
              className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
            >
              <Search className="h-3.5 w-3.5" />
              Explain Edge
            </button>
          )}
        </div>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* Members list — ~40% */}
        <div className="lg:col-span-2">
          <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-4">
            <h3 className="mb-3 text-sm font-semibold text-gray-700">
              Members ({detail.members.length})
            </h3>
            <div className="max-h-[600px] overflow-y-auto">
              <ClusterMembers
                members={detail.members}
                highlightedKey={highlightedMember}
                onMemberClick={handleMemberClick}
              />
            </div>
          </div>
        </div>

        {/* Graph — ~60% */}
        <div className="lg:col-span-3">
          <div className="h-[600px] rounded-lg border border-gray-200 bg-gray-50/50 p-1">
            {graphLoading ? (
              <LoadingSpinner className="h-full" />
            ) : (
              <ClusterGraph
                nodes={graph?.nodes ?? []}
                edges={graph?.edges ?? []}
                onEdgeClick={handleEdgeClick}
                highlightedMemberKey={highlightedMember}
              />
            )}
          </div>
        </div>
      </div>

      {/* Explain Match Modal */}
      {selectedEdge && (
        <ExplainMatchModal
          isOpen={!!selectedEdge}
          onClose={() => setSelectedEdge(null)}
          collection={collection}
          keyA={selectedEdge.a}
          keyB={selectedEdge.b}
        />
      )}
    </div>
  );
}
