import React from "react";

type NodeLike = { id: string; data?: { title?: string; columns?: Array<{ name: string; pk?: boolean }> } };
type EdgeLike = { id: string; source: string; target: string; relation?: string; status?: string };

type Props = {
  activeNode: NodeLike | null;
  activeEdges: EdgeLike[];
  selectedEdge: EdgeLike | null;
};

export function DBMLInspector({ activeNode, activeEdges, selectedEdge }: Props) {
  const columns = activeNode?.data?.columns || [];
  return (
    <div className="dbml-property-panel">
      <div className="dbml-pane-title">Properties</div>
      <div className="dbml-inspector-card">
        <h4>{activeNode?.data?.title || "No table selected"}</h4>
        <div className="dbml-inspector-section"><strong>PK</strong><div>{columns.filter((c) => c.pk).map((c) => c.name).join(", ") || "-"}</div></div>
        <div className="dbml-inspector-section"><strong>FK</strong><div>{activeEdges.length}</div></div>
        <div className="dbml-inspector-section"><strong>Quality</strong><div>N/A</div></div>
        <div className="dbml-inspector-section"><strong>LCIL</strong><div>N/A</div></div>
        <div className="dbml-inspector-section"><strong>Metrics</strong><div>{columns.length} columns</div></div>
        {selectedEdge ? (
          <div className="dbml-inspector-section dbml-inspector-highlight">
            <strong>Relationship</strong>
            <div>Type: {selectedEdge.relation || "TRUE_FK"}</div>
            <div>Status: {selectedEdge.status || "resolved"}</div>
            <div>{selectedEdge.source} -&gt; {selectedEdge.target}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
