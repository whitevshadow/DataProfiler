import React, { useState, useCallback } from "react";
import type { TreeNode } from "./types";
import { useApp } from "./store";
import { fetchEntity, fetchExpand } from "./api";

// ── Quality badge ─────────────────────────────────────────────
function QBar({ val, label }: { val: number; label: string }) {
  const cls = val >= 0.9 ? "quality-good" : val >= 0.7 ? "quality-mid" : "quality-bad";
  return (
    <div className="quality-bar-wrap">
      <span style={{ fontSize: 10, color: "var(--text3)", minWidth: 72 }}>{label}</span>
      <div className="quality-bar"><div className={`quality-bar-fill ${cls}`} style={{ width: `${val * 100}%` }} /></div>
      <span className="quality-val">{(val * 100).toFixed(0)}%</span>
    </div>
  );
}

// ── Edge click badge ──────────────────────────────────────────
function EdgeBadge({ fkCol, pkCol, pkTable, edgeId, confidence, onEdgeClick }:
  { fkCol: string; pkCol: string; pkTable: string; edgeId: string; confidence: number; onEdgeClick: (id: string) => void }) {
  return (
    <div
      className="ws-edge-label"
      onClick={() => onEdgeClick(edgeId)}
      title={`Click to inspect: ${fkCol} → ${pkTable}.${pkCol}`}
    >
      <span style={{ color: "var(--cyan)", fontFamily: "var(--mono)", fontSize: 10 }}>{fkCol}</span>
      <span className="arrow">→</span>
      <span style={{ color: "var(--green)", fontFamily: "var(--mono)", fontSize: 10 }}>{pkTable}.{pkCol}</span>
      <span className="ws-depth-badge">{(confidence * 100).toFixed(0)}%</span>
    </div>
  );
}

// ── Workspace Node Card ───────────────────────────────────────
interface WsNodeProps {
  node: TreeNode;
  depth: number;
  visitedPath: string[];
  onSelect: (id: string) => void;
  onEdgeClick: (edgeId: string) => void;
  selectedId: string | null;
}

function WsNode({ node, depth, visitedPath, onSelect, onEdgeClick, selectedId }: WsNodeProps) {
  const { state, dispatch, log } = useApp();
  const [isExpanded, setIsExpanded] = useState(false);
  const [children, setChildren] = useState<TreeNode[]>([]);
  const [loading, setLoading] = useState(false);

  const entity = state.entityCache[node.id];
  const isSelected = selectedId === node.id;
  const isCyclic = visitedPath.includes(node.id);

  const handleToggle = useCallback(async () => {
    if (!node.has_children || isCyclic) return;

    if (isExpanded) {
      setIsExpanded(false);
      log("COLLAPSE", node.label, "info");
      return;
    }

    // Use cached children if available
    const cached = state.expandCache[node.id];
    if (cached) {
      setChildren(cached);
      setIsExpanded(true);
      return;
    }

    setLoading(true);
    try {
      const res = await fetchExpand(node.id, visitedPath);
      setChildren(res.children);
      dispatch({ type: "SET_EXPANDED", id: node.id, children: res.children });

      // Pre-fetch entity data for all children
      res.children.forEach(c => {
        if (!state.entityCache[c.id]) {
          fetchEntity(c.id).then(d => dispatch({ type: "CACHE_ENTITY", id: c.id, data: d })).catch(() => {});
        }
      });

      setIsExpanded(true);
      log("EXPAND", `${node.label} → ${res.children.length} children`, "ok");
    } catch (err) {
      log("ERROR", `Failed to expand ${node.label}`, "warn");
    } finally {
      setLoading(false);
    }
  }, [node.id, node.label, node.has_children, isExpanded, isCyclic, visitedPath, state.expandCache, state.entityCache, dispatch, log]);

  const handleSelect = () => {
    onSelect(node.id);
    dispatch({ type: "SELECT_ENTITY", id: node.id });
    if (!entity) {
      fetchEntity(node.id).then(d => dispatch({ type: "CACHE_ENTITY", id: node.id, data: d })).catch(() => {});
    }
  };

  const handleRemove = (e: React.MouseEvent) => {
    e.stopPropagation();
    dispatch({ type: "REMOVE_FROM_WORKSPACE", id: node.id });
    log("REMOVE", node.label, "info");
  };

  return (
    <div className="ws-node anim-in" style={{ marginLeft: depth > 0 ? 0 : 0 }}>
      <div
        className={`ws-node-card${isExpanded ? " expanded" : ""}${isSelected ? " selected" : ""}`}
        onClick={handleSelect}
      >
        <span className="ws-node-icon">{node.has_children ? (isExpanded ? "⬡" : "⬡") : "◈"}</span>

        <div className="ws-node-info">
          <div className="ws-node-name">{node.label}</div>
          <div className="ws-node-meta">
            {entity?.row_count != null && <span>📊 {entity.row_count.toLocaleString()} rows</span>}
            {entity?.column_count && <span>⊞ {entity.column_count} cols</span>}
            {entity?.pk && <span style={{ color: "var(--amber)" }}>🔑 {entity.pk}</span>}
            {entity?.quality_score != null && (
              <span style={{ color: entity.quality_score >= 0.9 ? "var(--green)" : entity.quality_score >= 0.7 ? "var(--amber)" : "var(--red)" }}>
                ◆ {entity.quality_score.toFixed(2)}
              </span>
            )}
            {isCyclic && <span style={{ color: "var(--amber)" }}>⚠ cycle</span>}
          </div>
        </div>

        <div className="ws-node-badges">
          {entity?.fk_count ? <span className="tree-edge-badge">FK:{entity.fk_count}</span> : null}
          {entity?.lcil_domains?.length ? <span className="tag purple" style={{ fontSize: 9 }}>LCIL</span> : null}
          {entity?.is_orphan && <span className="tag red" style={{ fontSize: 9 }}>ORPHAN</span>}
        </div>

        <div className="ws-node-actions">
          {node.has_children && !isCyclic && (
            <button
              className="ws-action-btn"
              onClick={e => { e.stopPropagation(); handleToggle(); }}
              title={isExpanded ? "Collapse" : "Expand FK children"}
            >
              {loading ? <span className="tree-spinner" /> : isExpanded ? "▴" : "▾"}
            </button>
          )}
          {depth === 0 && (
            <button className="ws-action-btn" onClick={handleRemove} title="Remove from workspace" style={{ color: "var(--red)" }}>✕</button>
          )}
        </div>
      </div>

      {/* Children */}
      {isExpanded && (
        <div className="ws-children anim-in">
          {children.length === 0 && (
            <div style={{ fontSize: 11, color: "var(--text3)", padding: "6px 10px" }}>No TRUE_FK children found</div>
          )}
          {children.map(child => {
            const edgeId = child.edge
              ? `${child.id}__${child.edge.fk_column}__${node.id}__${child.edge.pk_column}`
              : "";
            return (
              <div key={`${child.id}__${child.edge?.fk_column}`}>
                {child.edge && (
                  <EdgeBadge
                    fkCol={child.edge.fk_column}
                    pkCol={child.edge.pk_column}
                    pkTable={node.id}
                    edgeId={edgeId}
                    confidence={child.edge.confidence}
                    onEdgeClick={onEdgeClick}
                  />
                )}
                <WsNode
                  node={child}
                  depth={depth + 1}
                  visitedPath={[...visitedPath, node.id]}
                  onSelect={onSelect}
                  onEdgeClick={onEdgeClick}
                  selectedId={selectedId}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Workspace Panel ───────────────────────────────────────────
export function WorkspacePanel() {
  const { state, dispatch, log } = useApp();

  const handleSelect = (id: string) => {
    dispatch({ type: "SELECT_ENTITY", id });
  };

  const handleEdgeClick = (edgeId: string) => {
    dispatch({ type: "SELECT_EDGE", id: edgeId });
    log("EDGE_SELECT", edgeId, "info");
  };

  const handleClear = () => {
    dispatch({ type: "CLEAR_WORKSPACE" });
    log("CLEAR_WORKSPACE", "Workspace cleared", "info");
  };

  if (state.workspaceRoots.length === 0) {
    return (
      <div className="fkrte-center">
        <div className="panel-hdr">
          <span style={{ color: "var(--cyan)", fontSize: 13 }}>◈</span>
          <h3>Expansion Workspace</h3>
        </div>
        <div className="workspace-empty">
          <div style={{ fontSize: 48, opacity: 0.2 }}>⬡</div>
          <h2>FK Relationship Tree Explorer</h2>
          <p>Click ⊕ on any table in the left tree to open it here, then expand its FK children interactively.</p>
          <div className="workspace-hint">
            <span>💡</span>
            <span>Click ▸ in left panel → then ⊕ to add to workspace</span>
          </div>
          <div className="workspace-hint">
            <span>🔑</span>
            <span>Only <strong>TRUE_FK</strong> relationships are shown</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fkrte-center">
      <div className="panel-hdr">
        <span style={{ color: "var(--cyan)", fontSize: 13 }}>◈</span>
        <h3>Expansion Workspace</h3>
        <span className="badge">{state.workspaceRoots.length}</span>
        <button className="collapse-btn" onClick={handleClear} style={{ marginLeft: "auto" }}>Clear All</button>
      </div>
      <div className="workspace scroll" style={{ padding: "16px 20px" }}>
        <div className="ws-tree">
          {state.workspaceRoots.map(root => (
            <div key={root.id} style={{ marginBottom: 12 }}>
              <WsNode
                node={root}
                depth={0}
                visitedPath={[]}
                onSelect={handleSelect}
                onEdgeClick={handleEdgeClick}
                selectedId={state.selectedEntityId}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
