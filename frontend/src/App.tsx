import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  ReactFlowInstance,
} from "reactflow";
import "reactflow/dist/style.css";

import { DiagramEdge, DiagramNode, RelationshipDetail, TableDetail } from "./types";
import { useDiagram } from "./hooks/useDiagram";
import { fetchDbml, fetchRelationshipDetail, fetchTableDetail } from "./data/api";
import { Badge } from "./components/Badge";
import { TableNode } from "./components/TableNode";
import { SearchBar } from "./components/SearchBar";
import { PipelineStatus } from "./components/PipelineStatus";
import { TopActions } from "./components/TopActions";
import { Tabs } from "./components/Tabs";
import { ExecutionTrace } from "./components/ExecutionTrace";
import { RelationshipLegend } from "./components/RelationshipLegend";
import logo from "../neuleap_logo.jpg";
import { useTrace } from "./hooks/useTrace";
import { ColumnTooltipList } from "./components/ColumnTooltipList";
import { FKRTreeExplorer } from "./components/FKRTreeExplorer";

const PIPELINE_STEPS = [
  "L1 Intake",
  "L2 Format",
  "L3 Standardization",
  "L4 Profiling",
  "L5 Type",
  "L6 Quality",
  "L7 PK",
  "L8 LCIL",
  "L9 Relationships",
  "L10 Diagram",
];

const relationshipColors: Record<string, string> = {
  TRUE_FK: "#22c55e",
  SEMANTICALLY_RELATED: "#60a5fa",
  SHARED_ENTITY_DOMAIN: "#a855f7",
  POSSIBLE_REFERENCE: "#f97316",
  UNKNOWN: "#64748b",
};

const nodeTypes = {
  expandedTable: TableNode,
  collapsedTable: TableNode,
  column: TableNode,
};

export default function App() {
  const [viewMode, setViewMode] = useState<"diagram" | "tree">("diagram");
  const { diagram, loading, error, filters, setFilters } = useDiagram();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [selectedTable, setSelectedTable] = useState<TableDetail | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<RelationshipDetail | null>(null);
  const [activeTab, setActiveTab] = useState("Overview");
  const { events: traceEvents, setEvents: setTraceEvents } = useTrace();
  const [reactFlow, setReactFlow] = useState<ReactFlowInstance | null>(null);
  const [search, setSearch] = useState("");
  const [tableDetails, setTableDetails] = useState<Record<string, TableDetail>>({});
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  const derivedNodes = useMemo(() => {
    if (!diagram) return [] as Node[];
    return diagram.nodes.map((node, index) => {
      const isExpanded = !!expanded[node.id];
      const detail = tableDetails[node.id];
      const token = search.trim().toLowerCase();
      const isMatch = token
        ? node.name.toLowerCase().includes(token)
          || node.columns.some((col) => col.name.toLowerCase().includes(token))
        : false;
      const isSelected = selectedNodeId === node.id;
      return {
        id: node.id,
        type: isExpanded ? "expandedTable" : "collapsedTable",
        position: { x: (index % 5) * 280, y: Math.floor(index / 5) * 220 },
        className: isSelected ? "ring-2 ring-accent" : isMatch ? "ring-2 ring-accent/60" : "",
        data: {
          ...node,
          expanded: isExpanded,
          columnInsights: detail?.columns ?? [],
        } as DiagramNode & { expanded: boolean },
      } as Node;
    });
  }, [diagram, expanded, tableDetails, search, selectedNodeId]);

  const derivedEdges = useMemo(() => {
    if (!diagram) return [] as Edge[];
    return diagram.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: `${edge.source_column} → ${edge.target_column}`,
      style: {
        stroke: selectedEdgeId === edge.id ? "#fbbf24" : relationshipColors[edge.relationship_class] || "#22c55e",
        strokeWidth: selectedEdgeId === edge.id ? 3 : 2,
      },
      data: edge,
    }));
  }, [diagram, selectedEdgeId]);

  useEffect(() => {
    setNodes(derivedNodes);
  }, [derivedNodes, setNodes]);

  useEffect(() => {
    setEdges(derivedEdges);
  }, [derivedEdges, setEdges]);

  const handleNodeClick = async (_: unknown, node: Node) => {
    const id = node.id;
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
    setSelectedNodeId(id);
    setSelectedEdgeId(null);
    try {
      const detail = await fetchTableDetail(id);
      setTableDetails((prev) => ({ ...prev, [id]: detail }));
      setSelectedTable(detail);
      setSelectedEdge(null);
      setActiveTab("Columns");
    } catch {
      setSelectedTable(null);
    }
  };

  const selectEdgeById = async (edgeId: string) => {
    try {
      const detail = await fetchRelationshipDetail(edgeId);
      setSelectedEdge(detail);
      setSelectedEdgeId(edgeId);
      setSelectedNodeId(null);
      setSelectedTable(null);
      setActiveTab("Relationships");
    } catch {
      setSelectedEdge(null);
    }
  };

  const handleEdgeClick = async (_: unknown, edge: Edge) => {
    await selectEdgeById(edge.id);
  };

  const handleEdgeDoubleClick = (_: unknown, edge: Edge) => {
    if (!reactFlow) return;
    reactFlow.fitView({ nodes: nodes.filter((n) => n.id === edge.source || n.id === edge.target), padding: 0.3 });
  };

  const handleNodeDoubleClick = (_: unknown, node: Node) => {
    if (!reactFlow) return;
    reactFlow.fitView({ nodes: nodes.filter((n) => n.id === node.id), padding: 0.35 });
  };

  const tableRelationships = useMemo(() => {
    if (!diagram || !selectedTable) return [] as DiagramEdge[];
    return diagram.edges.filter(
      (edge) => edge.source === selectedTable.table || edge.target === selectedTable.table
    );
  }, [diagram, selectedTable]);

  const qualityIssues = useMemo(() => {
    if (!selectedTable) return [];
    return [...selectedTable.columns]
      .filter((col) => col.quality < 0.8 || col.null_ratio > 0.1)
      .sort((a, b) => a.quality - b.quality)
      .slice(0, 8);
  }, [selectedTable]);

  const semanticSummary = useMemo(() => {
    if (!selectedTable) return [] as Array<{ semantic: string; count: number }>;
    const tally: Record<string, number> = {};
    selectedTable.columns.forEach((col) => {
      const key = col.semantic || "UNKNOWN";
      tally[key] = (tally[key] || 0) + 1;
    });
    return Object.entries(tally)
      .map(([semantic, count]) => ({ semantic, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
  }, [selectedTable]);

  const handleDbmlExport = async () => {
    const dbml = await fetchDbml();
    const blob = new Blob([dbml], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "schema.dbml";
    link.click();
    URL.revokeObjectURL(url);
  };

  const filteredNodes = useMemo(() => {
    if (!nodes.length || !search.trim()) return nodes;
    const token = search.toLowerCase();
    return nodes.filter((node) => {
      const data = node.data as DiagramNode & { expanded: boolean };
      if (data.name.toLowerCase().includes(token)) return true;
      return data.columns.some((col) => col.name.toLowerCase().includes(token));
    });
  }, [nodes, search]);

  const filteredEdges = useMemo(() => {
    if (!edges.length) return edges;
    const allowed = new Set(filters.relationshipClasses.map((item) => item.toUpperCase()));
    return edges.filter((edge) => {
      const rel = edge.data as DiagramEdge;
      return allowed.has(rel.relationship_class);
    });
  }, [edges, filters.relationshipClasses]);

  return (
    <div className="flex h-screen bg-canvas text-slate-100">
      <aside className="flex w-[280px] flex-col border-r border-slate-800 bg-panel px-5 py-6">
        <div className="flex items-center gap-3">
          <img src={logo} alt="NeuLeap" className="h-10 w-10 rounded-lg" />
          <div>
            <div className="text-lg font-semibold">NeuLeap Workspace</div>
            <div className="text-xs text-slate-400">Semantic DB Explorer</div>
          </div>
        </div>

        {/* View Mode Switcher */}
        <div className="mt-6 flex gap-2">
          <button
            onClick={() => setViewMode("diagram")}
            className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              viewMode === "diagram"
                ? "bg-blue-600 text-white"
                : "bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-300"
            }`}
          >
            <div className="flex items-center justify-center gap-1.5">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM14 5a1 1 0 011-1h4a1 1 0 011 1v7a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1H5a1 1 0 01-1-1v-3zM14 16a1 1 0 011-1h4a1 1 0 011 1v3a1 1 0 01-1 1h-4a1 1 0 01-1-1v-3z" />
              </svg>
              <span>Diagram</span>
            </div>
          </button>
          <button
            onClick={() => setViewMode("tree")}
            className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              viewMode === "tree"
                ? "bg-blue-600 text-white"
                : "bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-300"
            }`}
          >
            <div className="flex items-center justify-center gap-1.5">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              <span>FK Tree</span>
            </div>
          </button>
        </div>

        <div className="mt-6 space-y-4">
          <SearchBar value={search} onChange={setSearch} />

          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Filters</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {filters.relationshipClasses.map((cls) => (
                <Badge key={cls} label={cls} />
              ))}
            </div>
            <div className="mt-3 space-y-2 text-[11px] text-slate-400">
              {["TRUE_FK", "SEMANTICALLY_RELATED", "SHARED_ENTITY_DOMAIN"].map((cls) => (
                <label key={cls} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={filters.relationshipClasses.includes(cls)}
                    onChange={(e) => {
                      setFilters((prev) => {
                        const set = new Set(prev.relationshipClasses);
                        if (e.target.checked) {
                          set.add(cls);
                        } else {
                          set.delete(cls);
                        }
                        return { ...prev, relationshipClasses: Array.from(set) };
                      });
                    }}
                  />
                  <span>{cls}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs text-slate-400">Confidence</label>
            <input
              type="range"
              min={0.1}
              max={1}
              step={0.05}
              value={filters.minConfidence}
              onChange={(e) => setFilters((prev) => ({ ...prev, minConfidence: Number(e.target.value) }))}
              className="w-full"
            />
            <div className="text-xs text-slate-400">{filters.minConfidence.toFixed(2)} minimum</div>
          </div>

          <div className="space-y-2">
            <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Dataset</div>
            <div className="rounded-xl border border-slate-800 bg-surface p-3 text-xs text-slate-300">
              <div className="flex justify-between"><span>Tables</span><span>{diagram?.metrics.table_count ?? 0}</span></div>
              <div className="flex justify-between"><span>Relationships</span><span>{diagram?.metrics.relationship_count ?? 0}</span></div>
            </div>
          </div>

          <div>
            <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Legend</div>
            <div className="mt-2">
              <RelationshipLegend />
            </div>
          </div>
        </div>
      </aside>

      <main className="flex flex-1 flex-col">
        {viewMode === "tree" ? (
          <FKRTreeExplorer />
        ) : (
          <>
            <header className="border-b border-slate-800 bg-surface px-6 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xl font-semibold">Interactive DB Diagram</div>
              <div className="text-xs text-slate-400">Click a table to expand. Double-click to focus.</div>
            </div>
            <TopActions onExport={handleDbmlExport} />
          </div>
          <PipelineStatus steps={PIPELINE_STEPS} />
        </header>

        <section className="flex flex-1">
          <div className="flex-1">
            {loading ? (
              <div className="flex h-full items-center justify-center text-slate-400">Loading diagram...</div>
            ) : error ? (
              <div className="flex h-full items-center justify-center text-red-400">{error}</div>
            ) : (
              <ReactFlow
                nodes={filteredNodes}
                edges={filteredEdges}
                nodeTypes={nodeTypes}
                onNodeClick={handleNodeClick}
                onNodeDoubleClick={handleNodeDoubleClick}
                onEdgeClick={handleEdgeClick}
                onEdgeDoubleClick={handleEdgeDoubleClick}
                onInit={setReactFlow}
                fitView
              >
                <Background gap={24} color="#1f2937" />
                <MiniMap nodeColor="#22d3ee" maskColor="#0b1220" />
                <Controls />
              </ReactFlow>
            )}
          </div>

          <motion.aside
            className="w-[320px] border-l border-slate-800 bg-panel p-4"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold">Insights</div>
              <div className="text-[10px] text-slate-500">{selectedTable?.table ?? selectedEdge?.id ?? "Select a node"}</div>
            </div>

            <div className="mt-3">
              <Tabs
                tabs={["Overview", "Columns", "Quality", "PK", "LCIL", "Relationships", "Standardization", "Lineage"]}
                active={activeTab}
                onChange={setActiveTab}
              />
            </div>

            <div className="mt-4 space-y-3 text-xs text-slate-300">
              {selectedEdge && activeTab === "Relationships" ? (
                <div className="space-y-2">
                  <div className="text-sm font-semibold text-white">Relationship</div>
                  <div className="flex justify-between"><span>Type</span><span>{selectedEdge.relationship_class}</span></div>
                  <div className="flex justify-between"><span>Confidence</span><span>{selectedEdge.confidence.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span>Containment</span><span>{selectedEdge.containment_ratio.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span>Semantic</span><span>{selectedEdge.semantic_similarity.toFixed(2)}</span></div>
                  <div className="text-[11px] text-slate-400">{selectedEdge.fk_table}.{selectedEdge.fk_column} → {selectedEdge.pk_table}.{selectedEdge.pk_column}</div>
                </div>
              ) : selectedTable ? (
                <div className="space-y-3">
                  <div>
                    <div className="text-sm font-semibold text-white">{selectedTable.table}</div>
                    <div className="mt-1 flex justify-between"><span>Rows</span><span>{selectedTable.row_count}</span></div>
                    <div className="flex justify-between"><span>Quality</span><span>{selectedTable.quality.toFixed(2)}</span></div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {selectedTable.pk_columns.map((col) => (
                        <Badge key={col} label={`PK ${col}`} tone="pk" />
                      ))}
                    </div>
                  </div>
                  {activeTab === "Overview" ? (
                    <div className="space-y-2 text-[11px] text-slate-400">
                      <div className="flex justify-between"><span>Columns</span><span>{selectedTable.columns.length}</span></div>
                      <div className="flex justify-between"><span>Quality Avg</span><span>{selectedTable.quality.toFixed(2)}</span></div>
                      <div className="mt-2">
                        <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500">Semantic Mix</div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {semanticSummary.map((item) => (
                            <Badge key={item.semantic} label={`${item.semantic} (${item.count})`} />
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : null}
                  {activeTab === "Columns" ? (
                    <ColumnTooltipList columns={selectedTable.columns} />
                  ) : null}
                  {activeTab === "Quality" ? (
                    <div className="space-y-2">
                      {qualityIssues.length === 0 ? (
                        <div className="text-slate-500">No flagged quality issues.</div>
                      ) : (
                        qualityIssues.map((col) => (
                          <div key={col.column} className="flex items-center justify-between rounded-lg border border-slate-800 bg-surface px-3 py-2">
                            <span>{col.column}</span>
                            <span className="text-danger">Q {col.quality.toFixed(2)}</span>
                          </div>
                        ))
                      )}
                    </div>
                  ) : null}
                  {activeTab === "PK" ? (
                    <div className="flex flex-wrap gap-2">
                      {selectedTable.pk_columns.length === 0 ? (
                        <div className="text-slate-500">No PK columns detected.</div>
                      ) : (
                        selectedTable.pk_columns.map((col) => (
                          <Badge key={col} label={col} tone="pk" />
                        ))
                      )}
                    </div>
                  ) : null}
                  {activeTab === "LCIL" ? (
                    <div className="space-y-2">
                      {selectedTable.columns.filter((col) => col.ontology_tags.length > 0).length === 0 ? (
                        <div className="text-slate-500">No LCIL tags found.</div>
                      ) : (
                        selectedTable.columns.filter((col) => col.ontology_tags.length > 0).map((col) => (
                          <div key={col.column} className="rounded-lg border border-slate-800 bg-surface px-3 py-2">
                            <div className="text-sm text-white">{col.column}</div>
                            <div className="mt-1 flex flex-wrap gap-1">
                              {col.ontology_tags.map((tag) => (
                                <Badge key={tag} label={tag} tone="lcil" />
                              ))}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  ) : null}
                  {activeTab === "Relationships" ? (
                    <div className="space-y-2">
                      {tableRelationships.length === 0 ? (
                        <div className="text-slate-500">No relationships found.</div>
                      ) : (
                        tableRelationships.slice(0, 8).map((rel) => (
                          <button
                            key={rel.id}
                            className="w-full rounded-lg border border-slate-800 bg-surface px-3 py-2 text-left"
                            onClick={() => selectEdgeById(rel.id)}
                          >
                            <div className="text-xs text-white">{rel.source_column} → {rel.target_column}</div>
                            <div className="text-[10px] text-slate-500">{rel.relationship_class} · {rel.confidence.toFixed(2)}</div>
                          </button>
                        ))
                      )}
                    </div>
                  ) : null}
                  {activeTab === "Standardization" ? (
                    <div className="text-slate-500">Standardization metadata not available in current outputs.</div>
                  ) : null}
                  {activeTab === "Lineage" ? (
                    <div className="text-slate-500">Lineage metadata not available in current outputs.</div>
                  ) : null}
                  <div className="text-[11px] text-slate-400">{selectedTable.columns.length} columns loaded</div>
                </div>
              ) : (
                <div className="text-slate-500">Select a table or relationship to inspect details.</div>
              )}
            </div>
          </motion.aside>
        </section>

        <footer className="border-t border-slate-800 bg-surface px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Execution Trace</div>
            <button
              className="text-[11px] text-slate-400"
              onClick={() => setTraceEvents([])}
            >
              Clear
            </button>
          </div>
          <div className="mt-3">
            <ExecutionTrace events={traceEvents} />
          </div>
        </footer>
          </>
        )}
      </main>
    </div>
  );
}
