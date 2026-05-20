import React, { useEffect } from "react";
import { AppProvider, useApp } from "./store";
import { LeftPanel } from "./LeftPanel";
import { WorkspacePanel } from "./WorkspacePanel";
import { RightPanel } from "./RightPanel";
import { BottomTrace } from "./BottomTrace";
import { fetchTree, fetchStats, triggerRebuild } from "./api";

// ── Top Bar ───────────────────────────────────────────────────
function TopBar() {
  const { state, dispatch, log } = useApp();
  const stats = state.stats;

  const handleRebuild = async () => {
    log("REBUILD", "Triggering tree rebuild from source files…", "info");
    try {
      const r = await triggerRebuild();
      log("REBUILD", `Done — ${r.stats.total_tables} tables, ${r.stats.total_true_fk_edges} FK edges`, "ok");
      // Reload tree
      dispatch({ type: "TREE_LOADING" });
      const tree = await fetchTree(true);
      dispatch({ type: "SET_TREE", roots: tree.tree, stats: tree.stats });
    } catch (e: any) {
      log("REBUILD_ERROR", String(e), "warn");
    }
  };

  return (
    <div className="fkrte-topbar">
      <div className="topbar-logo">
        ⬡ <span>FKRTE</span> <span style={{ fontSize: 11, color: "var(--text3)" }}>FK Relationship Tree Explorer</span>
      </div>
      <div className="topbar-sep" />

      {stats && (
        <>
          <div className="topbar-stat">
            <span className="topbar-stat-val">{stats.total_tables}</span>
            <span className="topbar-stat-lbl">Tables</span>
          </div>
          <div className="topbar-stat">
            <span className="topbar-stat-val">{stats.total_true_fk_edges}</span>
            <span className="topbar-stat-lbl">TRUE_FK</span>
          </div>
          <div className="topbar-stat">
            <span className="topbar-stat-val">{stats.root_nodes}</span>
            <span className="topbar-stat-lbl">Roots</span>
          </div>
        </>
      )}

      {state.treeLoading && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text3)", fontSize: 12 }}>
          <span className="tree-spinner" /> Loading…
        </div>
      )}

      <div className="topbar-actions">
        {state.workspaceRoots.length > 0 && (
          <button className="btn" onClick={() => dispatch({ type: "CLEAR_WORKSPACE" })}>
            ✕ Clear Workspace
          </button>
        )}
        <button className="btn" onClick={handleRebuild} title="Rebuild tree from source JSON files">
          ↺ Rebuild
        </button>
        {state.selectedEntityId && (
          <div style={{ fontSize: 11, color: "var(--cyan)", fontFamily: "var(--mono)", padding: "4px 10px", background: "rgba(0,212,255,.08)", borderRadius: 6, border: "1px solid rgba(0,212,255,.2)" }}>
            ⬡ {state.selectedEntityId}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Boot loader ───────────────────────────────────────────────
function Boot() {
  const { dispatch, log } = useApp();

  useEffect(() => {
    (async () => {
      dispatch({ type: "TREE_LOADING" });
      log("INIT", "Loading FK relationship tree…", "info");
      try {
        const tree = await fetchTree();
        dispatch({ type: "SET_TREE", roots: tree.tree, stats: tree.stats });
        log("INIT", `Loaded ${tree.stats.total_tables} tables, ${tree.stats.total_true_fk_edges} TRUE_FK edges`, "ok");

        // Pre-warm stats
        try {
          const s = await fetchStats();
          log("STATS", `Orphans: ${s.orphan_tables} | With LCIL: ${s.tables_with_lcil}`, "info");
        } catch { /* optional */ }
      } catch (err: any) {
        const msg = String(err);
        dispatch({ type: "TREE_ERROR", error: msg });
        log("ERROR", `Failed to load tree: ${msg}`, "warn");
      }
    })();
  }, []);

  return null;
}

// ── Shell ─────────────────────────────────────────────────────
function Shell() {
  return (
    <div className="fkrte-shell">
      <TopBar />
      <LeftPanel />
      <WorkspacePanel />
      <RightPanel />
      <BottomTrace />
    </div>
  );
}

// ── Root export ───────────────────────────────────────────────
export function FKRTEApp() {
  return (
    <AppProvider>
      <Boot />
      <Shell />
    </AppProvider>
  );
}
