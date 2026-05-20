// ============================================================
// FKRTE – TypeScript Type Definitions
// ============================================================

export interface EdgeInfo {
  fk_column: string;
  pk_column: string;
  confidence: number;
  containment: number;
  semantic_similarity: number;
  reasoning: string[];
  relationship_class: "TRUE_FK";
}

export interface TreeNode {
  id: string;
  label: string;
  has_children: boolean;
  children: TreeNode[];
  edge?: EdgeInfo;        // edge that connects THIS node to its parent
  truncated?: boolean;
  is_visited?: boolean;
}

export interface ColumnInfo {
  name: string;
  key: string;
  type: string;
  logical_type: string;
  semantic_type: string;
  cardinality: string;
  null_ratio: number;
  quality: number;
  top_values: string[];
  is_pk: boolean;
  is_fk: boolean;
  relational_role: string;
  quality_flags: string[];
}

export interface EntityProperties {
  id: string;
  label: string;
  row_count: number | null;
  column_count: number;
  quality_score: number;
  completeness: number;
  pk: string | null;
  pk_confidence: number;
  fk_count: number;
  pk_candidates: string[];
  fk_candidates: string[];
  columns: ColumnInfo[];
  quality_flags: number;
  related_children: string[];
  related_parents: string[];
  lcil_domains: string[];
  is_orphan: boolean;
}

export interface RelationshipEdge {
  id: string;
  fk_table: string;
  fk_table_label: string;
  fk_column: string;
  pk_table: string;
  pk_table_label: string;
  pk_column: string;
  relationship_class: "TRUE_FK";
  confidence: number;
  containment: number;
  semantic_similarity: number;
  reasoning: string[];
}

export interface TableMetrics {
  id: string;
  label: string;
  row_count: number | null;
  column_count: number;
  quality_score: number;
  completeness: number;
  pk: string | null;
  fk_count: number;
  quality_flags: number;
}

export interface SearchResult {
  id: string;
  label: string;
  score: number;
  reasons: string[];
  quality_score: number;
  row_count: number | null;
  pk: string | null;
}

export interface TreeStats {
  total_tables: number;
  total_true_fk_edges: number;
  root_nodes: number;
}

export interface TreeResponse {
  tree: TreeNode[];
  stats: TreeStats;
}

export interface ExpandResponse {
  entity_id: string;
  children: TreeNode[];
}

// ============================================================
// UI State types
// ============================================================

export interface ExpandedNodeState {
  nodeId: string;
  path: string[];       // ancestor chain for cycle detection
  children: TreeNode[];
  isLoading: boolean;
}

export interface WorkspaceNode {
  id: string;
  label: string;
  parentId: string | null;
  depth: number;
  edge?: EdgeInfo;
  isExpanded: boolean;
  isLoading: boolean;
  children: WorkspaceNode[];
  entityData?: EntityProperties;
}

export type FilterState = {
  minQuality: number;
  minConfidence: number;
  minFkCount: number;
  hasLCIL: boolean | null;
  isOrphan: boolean | null;
};

export type PanelMode = "entity" | "relationship" | "column" | "none";

export interface ActivePanel {
  mode: PanelMode;
  entityId?: string;
  edgeId?: string;
  columnKey?: string;
}
