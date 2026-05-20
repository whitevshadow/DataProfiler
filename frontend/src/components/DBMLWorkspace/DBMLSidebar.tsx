import React from "react";

type NodeLike = { id: string; data?: { title?: string } };

type Props = {
  nodes: NodeLike[];
  activeEntity: string | null;
  onSelect: (id: string) => void;
};

export function DBMLSidebar({ nodes, activeEntity, onSelect }: Props) {
  return (
    <div className="dbml-explorer">
      <div className="dbml-pane-title">Explorer</div>
      <div className="dbml-table-list">
        {nodes.map((node) => (
          <button
            key={node.id}
            className={`dbml-table-item ${activeEntity === node.id ? "active" : ""}`}
            onClick={() => onSelect(node.id)}
          >
            {node.data?.title || node.id}
          </button>
        ))}
      </div>
    </div>
  );
}
