import { useMemo, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Node as FlowNode,
  type Edge as FlowEdge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Network } from "lucide-react";
import { EmptyState } from "../shared/EmptyState";

interface GraphNodeData {
  id: string;
  key: string;
  data: Record<string, unknown>;
}

interface GraphEdgeData {
  source: string;
  target: string;
  similarity: number;
  method?: string;
}

interface ClusterGraphProps {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  onEdgeClick?: (sourceKey: string, targetKey: string) => void;
  highlightedMemberKey?: string | null;
}

const SOURCE_COLORS = [
  "#818cf8",
  "#34d399",
  "#fb923c",
  "#60a5fa",
  "#f472b6",
  "#a78bfa",
  "#4ade80",
  "#fbbf24",
];

function hashString(s: string): number {
  let hash = 0;
  for (let i = 0; i < s.length; i++) {
    hash = (hash * 31 + s.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function getNodeColor(data: Record<string, unknown>): string {
  for (const field of ["source", "source_system", "_source"]) {
    const val = data[field];
    if (typeof val === "string" && val) {
      return SOURCE_COLORS[hashString(val) % SOURCE_COLORS.length] ?? SOURCE_COLORS[0]!;
    }
  }
  return "#e5e7eb";
}

function getEdgeColor(similarity: number): string {
  if (similarity >= 0.8) return "#22c55e";
  if (similarity >= 0.55) return "#f59e0b";
  return "#ef4444";
}

function getEdgeWidth(similarity: number): number {
  return 1 + similarity * 3;
}

function getNodeLabel(node: GraphNodeData): React.ReactNode {
  const entries = Object.entries(node.data)
    .filter(([k]) => !k.startsWith("_") && k !== "source" && k !== "source_system")
    .slice(0, 3);

  return (
    <div className="min-w-0">
      <div className="truncate font-semibold text-[11px] text-gray-800">
        {node.key}
      </div>
      {entries.map(([k, v]) => (
        <div key={k} className="truncate text-[10px] text-gray-600">
          {k}: {v == null ? "—" : String(v)}
        </div>
      ))}
    </div>
  );
}

export function ClusterGraph({
  nodes,
  edges,
  onEdgeClick,
  highlightedMemberKey,
}: ClusterGraphProps) {
  const flowNodes: FlowNode[] = useMemo(() => {
    const n = nodes.length;
    if (n === 0) return [];

    const radius = Math.max(180, n * 50);
    const angleStep = (2 * Math.PI) / n;

    return nodes.map((gn, i) => {
      const angle = i * angleStep - Math.PI / 2;
      const isHighlighted = highlightedMemberKey != null &&
        (gn.key === highlightedMemberKey || gn.id.endsWith(`/${highlightedMemberKey}`));
      const bgColor = getNodeColor(gn.data);

      return {
        id: gn.id,
        position: {
          x: radius * Math.cos(angle),
          y: radius * Math.sin(angle),
        },
        data: { label: getNodeLabel(gn) },
        style: {
          background: isHighlighted ? "#c7d2fe" : bgColor,
          border: isHighlighted ? "2px solid #6366f1" : "1px solid #d1d5db",
          borderRadius: "8px",
          padding: "8px",
          width: 170,
          fontSize: "12px",
          boxShadow: isHighlighted ? "0 0 0 3px rgba(99,102,241,0.2)" : undefined,
        },
      };
    });
  }, [nodes, highlightedMemberKey]);

  const flowEdges: FlowEdge[] = useMemo(
    () =>
      edges.map((ge, i) => ({
        id: `e-${i}`,
        source: ge.source,
        target: ge.target,
        label: ge.similarity.toFixed(2),
        style: {
          stroke: getEdgeColor(ge.similarity),
          strokeWidth: getEdgeWidth(ge.similarity),
        },
        labelStyle: {
          fontSize: "11px",
          fontWeight: 600,
          fill: getEdgeColor(ge.similarity),
        },
        labelBgStyle: {
          fill: "white",
          fillOpacity: 0.85,
        },
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 4,
      })),
    [edges],
  );

  const handleEdgeClick = useCallback(
    (_: React.MouseEvent, edge: FlowEdge) => {
      if (!onEdgeClick) return;
      const sourceKey = edge.source.split("/").pop() ?? edge.source;
      const targetKey = edge.target.split("/").pop() ?? edge.target;
      onEdgeClick(sourceKey, targetKey);
    },
    [onEdgeClick],
  );

  if (nodes.length === 0) {
    return (
      <EmptyState
        icon={Network}
        title="No graph data"
        description="No nodes available for visualization."
        className="h-full"
      />
    );
  }

  return (
    <div className="h-full w-full rounded-lg border border-gray-200 bg-white">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onEdgeClick={handleEdgeClick}
        fitView
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
