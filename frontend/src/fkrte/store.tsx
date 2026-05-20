import React, { createContext, useContext, useReducer, useCallback, useRef } from "react";
import type { EntityProperties, RelationshipEdge, FilterState, ActivePanel, TreeNode } from "./types";

// ── Trace log entry ──────────────────────────────────────────
export interface TraceEntry {
  ts: string;
  action: string;
  detail: string;
  kind: "ok" | "info" | "warn";
}

// ── App State ────────────────────────────────────────────────
export interface AppState {
  // Tree data (left panel)
  treeRoots: TreeNode[];
  treeLoading: boolean;
  treeError: string | null;

  // Workspace (centre) — expanded nodes keyed by nodeId
  workspaceRoots: TreeNode[];       // top-level nodes added to workspace
  expandedIds: Set<string>;          // ids currently expanded in workspace
  expandCache: Record<string, TreeNode[]>; // id → children

  // Selected entity
  selectedEntityId: string | null;
  entityCache: Record<string, EntityProperties>;

  // Selected edge
  selectedEdgeId: string | null;
  edgeCache: Record<string, RelationshipEdge>;

  // Selected column
  selectedColumnKey: string | null;

  // Active right panel mode
  activePanel: ActivePanel;

  // Search
  searchQuery: string;
  searchResults: { id: string; label: string; score: number }[];

  // Filters
  filters: FilterState;

  // Stats
  stats: { total_tables: number; total_true_fk_edges: number; root_nodes: number } | null;

  // Execution trace
  trace: TraceEntry[];
}

type Action =
  | { type: "SET_TREE"; roots: TreeNode[]; stats: AppState["stats"] }
  | { type: "TREE_LOADING" }
  | { type: "TREE_ERROR"; error: string }
  | { type: "ADD_TO_WORKSPACE"; node: TreeNode }
  | { type: "REMOVE_FROM_WORKSPACE"; id: string }
  | { type: "CLEAR_WORKSPACE" }
  | { type: "SET_EXPANDED"; id: string; children: TreeNode[] }
  | { type: "COLLAPSE"; id: string }
  | { type: "SELECT_ENTITY"; id: string }
  | { type: "CACHE_ENTITY"; id: string; data: EntityProperties }
  | { type: "SELECT_EDGE"; id: string }
  | { type: "CACHE_EDGE"; id: string; data: RelationshipEdge }
  | { type: "SELECT_COLUMN"; key: string | null }
  | { type: "SET_PANEL"; panel: ActivePanel }
  | { type: "SET_SEARCH"; q: string; results: AppState["searchResults"] }
  | { type: "SET_FILTER"; key: keyof FilterState; value: FilterState[keyof FilterState] }
  | { type: "LOG"; entry: TraceEntry };

const initial: AppState = {
  treeRoots: [],
  treeLoading: false,
  treeError: null,
  workspaceRoots: [],
  expandedIds: new Set(),
  expandCache: {},
  selectedEntityId: null,
  entityCache: {},
  selectedEdgeId: null,
  edgeCache: {},
  selectedColumnKey: null,
  activePanel: { mode: "none" },
  searchQuery: "",
  searchResults: [],
  filters: { minQuality: 0, minConfidence: 0, minFkCount: 0, hasLCIL: null, isOrphan: null },
  stats: null,
  trace: [],
};

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "TREE_LOADING": return { ...state, treeLoading: true, treeError: null };
    case "TREE_ERROR": return { ...state, treeLoading: false, treeError: action.error };
    case "SET_TREE": return { ...state, treeLoading: false, treeRoots: action.roots, stats: action.stats };

    case "ADD_TO_WORKSPACE": {
      const exists = state.workspaceRoots.some(n => n.id === action.node.id);
      if (exists) return state;
      return { ...state, workspaceRoots: [...state.workspaceRoots, action.node] };
    }
    case "REMOVE_FROM_WORKSPACE":
      return { ...state, workspaceRoots: state.workspaceRoots.filter(n => n.id !== action.id) };
    case "CLEAR_WORKSPACE":
      return { ...state, workspaceRoots: [], expandedIds: new Set() };

    case "SET_EXPANDED": {
      const next = new Set(state.expandedIds);
      next.add(action.id);
      return { ...state, expandedIds: next, expandCache: { ...state.expandCache, [action.id]: action.children } };
    }
    case "COLLAPSE": {
      const next = new Set(state.expandedIds);
      next.delete(action.id);
      return { ...state, expandedIds: next };
    }

    case "SELECT_ENTITY":
      return { ...state, selectedEntityId: action.id, selectedColumnKey: null, activePanel: { mode: "entity", entityId: action.id } };
    case "CACHE_ENTITY":
      return { ...state, entityCache: { ...state.entityCache, [action.id]: action.data } };

    case "SELECT_EDGE":
      return { ...state, selectedEdgeId: action.id, activePanel: { mode: "relationship", edgeId: action.id } };
    case "CACHE_EDGE":
      return { ...state, edgeCache: { ...state.edgeCache, [action.id]: action.data } };

    case "SELECT_COLUMN":
      return { ...state, selectedColumnKey: action.key, activePanel: { mode: "column", columnKey: action.key ?? undefined, entityId: state.selectedEntityId ?? undefined } };

    case "SET_PANEL": return { ...state, activePanel: action.panel };
    case "SET_SEARCH": return { ...state, searchQuery: action.q, searchResults: action.results };
    case "SET_FILTER": return { ...state, filters: { ...state.filters, [action.key]: action.value } };

    case "LOG":
      return { ...state, trace: [action.entry, ...state.trace].slice(0, 200) };

    default: return state;
  }
}

// ── Context ──────────────────────────────────────────────────
interface Ctx {
  state: AppState;
  dispatch: React.Dispatch<Action>;
  log: (action: string, detail: string, kind?: TraceEntry["kind"]) => void;
}

const AppCtx = createContext<Ctx>(null!);
export const useApp = () => useContext(AppCtx);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);

  const log = useCallback((action: string, detail: string, kind: TraceEntry["kind"] = "info") => {
    const ts = new Date().toTimeString().slice(0, 8);
    dispatch({ type: "LOG", entry: { ts, action, detail, kind } });
  }, []);

  return <AppCtx.Provider value={{ state, dispatch, log }}>{children}</AppCtx.Provider>;
}
