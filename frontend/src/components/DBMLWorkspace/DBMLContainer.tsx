import React, { useMemo, useState } from "react";
import { DBMLToolbar } from "./DBMLToolbar";
import { DBMLSidebar } from "./DBMLSidebar";
import { DBMLCanvas } from "./DBMLCanvas";
import { DBMLInspector } from "./DBMLInspector";
import { DBMLStatusBar } from "./DBMLStatusBar";

type NodeLike = { id: string; data?: { title?: string; columns?: Array<{ name: string; type?: string; pk?: boolean }> } };
type EdgeLike = { id: string; source: string; target: string; relation?: string; status?: string };

type Props = {
  nodes: NodeLike[];
  edges: EdgeLike[];
};

export function DBMLContainer({ nodes, edges }: Props) {
  const [activeEntity, setActiveEntity] = useState<string | null>(nodes[0]?.id || null);
  const [zoom, setZoom] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const [minimap, setMinimap] = useState(true);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  const filteredNodes = useMemo(() => {
    const token = search.trim().toLowerCase();
    if (!token) return nodes;
    return nodes.filter((n) => {
      if ((n.data?.title || n.id).toLowerCase().includes(token)) return true;
      const cols = n.data?.columns || [];
      return cols.some((c) => c.name.toLowerCase().includes(token));
    });
  }, [nodes, search]);

  const activeNode = nodes.find((n) => n.id === activeEntity) || null;
  const activeEdges = edges.filter((e) => e.source === activeEntity || e.target === activeEntity);
  const selectedEdge = edges.find((e) => e.id === selectedEdgeId) || null;

  return (
    <div className={fullscreen ? "dbml-workspace-root dbml-fullscreen" : "dbml-workspace-root"}>
      <div className="dbml-workspace">
        <DBMLToolbar
          zoom={zoom}
          minimap={minimap}
          onZoomIn={() => setZoom((z) => Math.min(z + 0.1, 2))}
          onZoomOut={() => setZoom((z) => Math.max(z - 0.1, 0.5))}
          onFit={() => setZoom(1)}
          onToggleMiniMap={() => setMinimap((m) => !m)}
          onExpandAll={() => setExpanded(new Set(nodes.map((n) => n.id)))}
          onCollapseAll={() => setExpanded(new Set())}
          onFullscreen={() => setFullscreen((f) => !f)}
          onExportPng={() => undefined}
          onSearch={setSearch}
        />

        <div className="dbml-main-grid">
          <DBMLSidebar nodes={filteredNodes} activeEntity={activeEntity} onSelect={setActiveEntity} />
          <div className="dbml-main-workspace">
            <div className="dbml-pane-title">Main Workspace</div>
            <DBMLCanvas
              nodes={filteredNodes}
              edges={edges}
              activeEntity={activeEntity}
              zoom={zoom}
              expanded={expanded}
              minimap={minimap}
              onSelectNode={(id) => {
                setActiveEntity(id);
                setExpanded((prev) => {
                  const next = new Set(prev);
                  if (next.has(id)) next.delete(id);
                  else next.add(id);
                  return next;
                });
              }}
              onSelectEdge={(id) => setSelectedEdgeId(id)}
            />
          </div>
          <DBMLInspector activeNode={activeNode} activeEdges={activeEdges} selectedEdge={selectedEdge} />
        </div>
      </div>
      <DBMLStatusBar tables={nodes.length} relationships={edges.length} zoom={zoom} />
    </div>
  );
}
