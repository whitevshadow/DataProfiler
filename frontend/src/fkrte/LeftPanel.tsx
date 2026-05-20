import React, { useState, useRef } from "react";
import type { TreeNode, EntityProperties } from "./types";
import { useApp } from "./store";
import { fetchEntity, fetchExpand } from "./api";

// ── Quality dot ──────────────────────────────────────────────
function QualityDot({ score }: { score: number }) {
  const cls = score >= 0.9 ? "dot-green" : score >= 0.7 ? "dot-amber" : "dot-red";
  return <span className={cls} title={`Quality: ${score.toFixed(2)}`} />;
}

// ── Tooltip state ─────────────────────────────────────────────
interface TooltipData {
  entity: EntityProperties;
  x: number;
  y: number;
}

function HoverTooltip({ data }: { data: TooltipData }) {
  const e = data.entity;
  const related = [...(e.related_children || []), ...(e.related_parents || [])];
  return (
    <div className="fkrte-tooltip" style={{ left: data.x + 16, top: Math.min(data.y, window.innerHeight - 260) }}>
      <div className="tt-title">⬡ {e.label}</div>
      <div className="tt-row"><span className="tt-label">Rows</span><span className="tt-val cyan">{e.row_count ?? "—"}</span></div>
      <div className="tt-row"><span className="tt-label">Columns</span><span className="tt-val">{e.column_count}</span></div>
      <div className="tt-row"><span className="tt-label">PK</span><span className="tt-val">{e.pk ?? "—"}</span></div>
      <div className="tt-row"><span className="tt-label">FK Count</span><span className="tt-val">{e.fk_count}</span></div>
      <div className="tt-row"><span className="tt-label">Quality</span><span className="tt-val cyan">{e.quality_score.toFixed(3)}</span></div>
      {related.length > 0 && (
        <>
          <div className="tt-label" style={{ marginTop: 8, marginBottom: 4, fontSize: 10 }}>RELATIONSHIPS</div>
          <div className="tt-rel-list">
            {related.slice(0, 5).map(r => (
              <div key={r} className="tt-rel-item">↗ {r}</div>
            ))}
            {related.length > 5 && <div className="tt-rel-item" style={{ color: "var(--text3)" }}>+{related.length - 5} more</div>}
          </div>
        </>
      )}
    </div>
  );
}

// ── Single tree node row ──────────────────────────────────────
interface NodeRowProps {
  node: TreeNode;
  depth: number;
  isExpanded: boolean;
  isSelected: boolean;
  onToggle: (node: TreeNode) => void;
  onSelect: (node: TreeNode) => void;
  onAddToWorkspace: (node: TreeNode) => void;
}

function NodeRow({ node, depth, isExpanded, isSelected, onToggle, onSelect, onAddToWorkspace }: NodeRowProps) {
  const { state } = useApp();
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const entity = state.entityCache[node.id];

  const handleMouseEnter = (e: React.MouseEvent) => {
    const x = e.clientX, y = e.clientY;
    hoverTimer.current = setTimeout(() => {
      if (entity) setTooltip({ entity, x, y });
    }, 400);
  };

  const handleMouseLeave = () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    setTooltip(null);
  };

  const hasChildren = node.has_children;
  const quality = entity?.quality_score;
  const rowCount = entity?.row_count;
  const colCount = entity?.column_count;
  const fkCount = entity?.fk_count || 0;

  return (
    <>
      <div
        className={`tree-node-row${isSelected ? " selected" : ""}`}
        style={{ paddingLeft: depth * 14 + 8 }}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onClick={() => onSelect(node)}
      >
        {/* Toggle */}
        <span
          className={`tree-toggle ${hasChildren ? (isExpanded ? "open" : "") : "leaf"}`}
          onClick={e => { e.stopPropagation(); if (hasChildren) onToggle(node); }}
        >
          {hasChildren ? (isExpanded ? "▾" : "▸") : "·"}
        </span>

        {/* Icon */}
        <span className="tree-icon" style={{ fontSize: 16 }}>
          {entity?.is_orphan ? "◈" : hasChildren ? "⬢" : "⬡"}
        </span>

        {/* Info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="tree-label">{node.label}</div>
          {entity && (
            <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2, display: 'flex', gap: 8, fontFamily: 'var(--mono)' }}>
              {rowCount != null && <span>{rowCount.toLocaleString()} rows</span>}
              {colCount != null && <span>{colCount} cols</span>}
              {entity.pk && <span style={{ color: 'var(--amber)' }}>PK:{entity.pk}</span>}
            </div>
          )}
        </div>

        {/* Badges */}
        <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexShrink: 0 }}>
          {/* Quality dot */}
          {quality != null && <QualityDot score={quality} />}

          {/* FK count */}
          {fkCount > 0 && (
            <span className="tree-edge-badge">FK:{fkCount}</span>
          )}

          {/* Add to workspace */}
          <span
            className="btn-icon"
            title="Open in workspace"
            style={{ fontSize: 13, opacity: 0, transition: "opacity .15s", cursor: 'pointer' }}
            onClick={e => { e.stopPropagation(); onAddToWorkspace(node); }}
            onMouseEnter={e => (e.currentTarget.style.opacity = "1")}
            onMouseLeave={e => (e.currentTarget.style.opacity = "0")}
          >⊕</span>
        </div>
      </div>

      {tooltip && <HoverTooltip data={tooltip} />}
    </>
  );
}

// ── Recursive tree ────────────────────────────────────────────
interface TreeBranchProps {
  nodes: TreeNode[];
  depth: number;
  expandedSet: Set<string>;
  onToggle: (node: TreeNode) => void;
  onSelect: (node: TreeNode) => void;
  onAddToWorkspace: (node: TreeNode) => void;
  selectedId: string | null;
}

function TreeBranch({ nodes, depth, expandedSet, onToggle, onSelect, onAddToWorkspace, selectedId }: TreeBranchProps) {
  return (
    <>
      {nodes.map(node => {
        const isExpanded = expandedSet.has(node.id);
        return (
          <div key={node.id} className="tree-node">
            <NodeRow
              node={node}
              depth={depth}
              isExpanded={isExpanded}
              isSelected={selectedId === node.id}
              onToggle={onToggle}
              onSelect={onSelect}
              onAddToWorkspace={onAddToWorkspace}
            />
            {isExpanded && node.children.length > 0 && (
              <div className="tree-children anim-in">
                <TreeBranch
                  nodes={node.children}
                  depth={depth + 1}
                  expandedSet={expandedSet}
                  onToggle={onToggle}
                  onSelect={onSelect}
                  onAddToWorkspace={onAddToWorkspace}
                  selectedId={selectedId}
                />
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}

// ── Main LeftPanel ─────────────────────────────────────────────
export function LeftPanel() {
  const { state, dispatch, log } = useApp();
  const [localExpanded, setLocalExpanded] = useState<Set<string>>(new Set());
  const [searchVal, setSearchVal] = useState("");
  const [minQuality, setMinQuality] = useState(0);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [autoExpandedOnce, setAutoExpandedOnce] = useState(false);

  // Auto-expand all root nodes once on initial load to show complete tree
  React.useEffect(() => {
    if (!autoExpandedOnce && state.treeRoots.length > 0 && !state.treeLoading) {
      const allIds = new Set<string>();
      const collectIds = (nodes: TreeNode[]) => {
        nodes.forEach(n => {
          allIds.add(n.id);
          if (n.children && n.children.length > 0) {
            collectIds(n.children);
          }
        });
      };
      collectIds(state.treeRoots);
      setLocalExpanded(allIds);
      setAutoExpandedOnce(true);
      log("AUTO_EXPAND", `Expanded ${allIds.size} nodes to show complete tree structure`, "info");
    }
  }, [state.treeRoots, state.treeLoading, autoExpandedOnce, log]);

  // Filter tree roots
  const visibleRoots = state.treeRoots.filter(n => {
    const e = state.entityCache[n.id];
    if (e && e.quality_score < minQuality) return false;
    if (searchVal) {
      const q = searchVal.toLowerCase();
      return n.label.toLowerCase().includes(q) || n.id.includes(q);
    }
    return true;
  });

  // Prefetch entity on hover
  const prefetchEntity = async (id: string) => {
    if (state.entityCache[id]) return;
    try {
      const data = await fetchEntity(id);
      dispatch({ type: "CACHE_ENTITY", id, data });
    } catch { /* silent */ }
  };

  // Toggle expand in left-panel tree (uses pre-loaded children from treeRoots)
  const handleToggle = async (node: TreeNode) => {
    const next = new Set(localExpanded);
    if (next.has(node.id)) {
      next.delete(node.id);
      log("COLLAPSE", node.label, "info");
    } else {
      next.add(node.id);
      log("EXPAND", node.label, "ok");
      prefetchEntity(node.id);
    }
    setLocalExpanded(next);
  };

  const handleSelect = (node: TreeNode) => {
    dispatch({ type: "SELECT_ENTITY", id: node.id });
    log("SELECT", node.label, "info");
    prefetchEntity(node.id);
    // also trigger background fetch if not cached
    if (!state.entityCache[node.id]) {
      fetchEntity(node.id).then(data => dispatch({ type: "CACHE_ENTITY", id: node.id, data })).catch(() => {});
    }
  };

  const handleAddToWorkspace = (node: TreeNode) => {
    dispatch({ type: "ADD_TO_WORKSPACE", node });
    dispatch({ type: "SELECT_ENTITY", id: node.id });
    log("WORKSPACE_ADD", node.label, "ok");
    if (!state.entityCache[node.id]) {
      fetchEntity(node.id).then(data => dispatch({ type: "CACHE_ENTITY", id: node.id, data })).catch(() => {});
    }
  };

  return (
    <div className="fkrte-left">
      {/* Header */}
      <div className="panel-hdr">
        <span style={{ color: "var(--cyan)", fontSize: 13 }}>⬡</span>
        <h3>Relationship Tree</h3>
        <span className="badge">{state.treeRoots.length}</span>
        <button
          className="btn-icon"
          onClick={() => {
            if (localExpanded.size > 0) {
              setLocalExpanded(new Set());
              log("COLLAPSE_ALL", "Collapsed all nodes", "info");
            } else {
              const allIds = new Set<string>();
              const collectIds = (nodes: TreeNode[]) => {
                nodes.forEach(n => {
                  allIds.add(n.id);
                  if (n.children && n.children.length > 0) {
                    collectIds(n.children);
                  }
                });
              };
              collectIds(state.treeRoots);
              setLocalExpanded(allIds);
              log("EXPAND_ALL", `Expanded ${allIds.size} nodes`, "info");
            }
          }}
          title={localExpanded.size > 0 ? "Collapse all" : "Expand all"}
          style={{ marginLeft: 'auto', fontSize: 12 }}
        >
          {localExpanded.size > 0 ? "▾▾" : "▸▸"}
        </button>
      </div>

      {/* Search */}
      <div className="search-wrap">
        <div className="search-wrap-inner">
          <span className="search-icon">⌕</span>
          <input
            className="search-input"
            placeholder="Search tables, columns, PK…"
            value={searchVal}
            onChange={e => setSearchVal(e.target.value)}
          />
        </div>
      </div>

      {/* Filter */}
      <div className="filter-bar">
        <div className="filter-row">
          <span className="filter-label">Min Quality</span>
          <input
            type="range" min={0} max={1} step={0.05}
            value={minQuality}
            onChange={e => setMinQuality(Number(e.target.value))}
            className="filter-slider"
          />
          <span className="filter-val">{minQuality.toFixed(2)}</span>
        </div>
      </div>

      {/* Tree */}
      <div className="panel-body scroll">
        {state.treeLoading && (
          <div style={{ padding: 20, textAlign: "center", color: "var(--text3)" }}>
            <span className="tree-spinner" style={{ width: 16, height: 16 }} /> Loading tree…
          </div>
        )}
        {state.treeError && (
          <div style={{ padding: 16, color: "var(--red)", fontSize: 12 }}>⚠ {state.treeError}</div>
        )}
        {!state.treeLoading && visibleRoots.length === 0 && !state.treeError && (
          <div style={{ padding: 20, color: "var(--text3)", fontSize: 12, textAlign: "center" }}>
            No tables match filters
          </div>
        )}
        {!state.treeLoading && (
          <div className="tree-root">
            {visibleRoots.length > 0 && (
              <div className="tree-section-label">ROOT ENTITIES</div>
            )}
            <TreeBranch
              nodes={visibleRoots}
              depth={0}
              expandedSet={localExpanded}
              onToggle={handleToggle}
              onSelect={handleSelect}
              onAddToWorkspace={handleAddToWorkspace}
              selectedId={state.selectedEntityId}
            />
          </div>
        )}
      </div>
    </div>
  );
}
