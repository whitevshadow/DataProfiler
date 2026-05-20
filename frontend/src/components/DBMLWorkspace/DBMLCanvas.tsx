import React from "react";

type NodeLike = {
  id: string;
  data?: { title?: string; columns?: Array<{ name: string; type?: string; pk?: boolean }> };
};

type EdgeLike = { id: string; source: string; target: string; relation?: string };

type Props = {
  nodes: NodeLike[];
  edges: EdgeLike[];
  activeEntity: string | null;
  zoom: number;
  expanded: Set<string>;
  minimap: boolean;
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
};

export function DBMLCanvas({ nodes, edges, activeEntity, zoom, expanded, minimap, onSelectNode, onSelectEdge }: Props) {
  return (
    <div className="dbml-viewer-area">
      <div className="dbml-canvas-wrap">
        <div className="dbml-card-grid">
          {nodes.map((node) => {
            const cols = node.data?.columns || [];
            const isExpanded = expanded.has(node.id);
            return (
              <div
                key={node.id}
                className={`dbml-card ${activeEntity === node.id ? "active" : ""}`}
                style={{ transform: `scale(${zoom})` }}
                onClick={() => onSelectNode(node.id)}
              >
                <div className="dbml-card-title">{node.data?.title || node.id}</div>
                {isExpanded
                  ? cols.map((c) => (
                      <div className="dbml-col-row" key={`${node.id}-${c.name}`}>
                        {c.pk ? "[PK] " : ""}
                        {c.name}: {c.type || "?"}
                      </div>
                    ))
                  : null}
              </div>
            );
          })}
        </div>

        {minimap ? <div className="dbml-minimap">MiniMap: {nodes.length} nodes</div> : null}

        <div className="dbml-edge-list">
          {edges.map((edge) => (
            <button key={edge.id} className="dbml-edge-line" onClick={() => onSelectEdge(edge.id)}>
              {edge.source} -&gt; {edge.target}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
