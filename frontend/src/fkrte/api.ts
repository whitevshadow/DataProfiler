// ============================================================
// FKRTE API Client
// Talks to the FastAPI backend at /api/fkrte/*
// Falls back to mock data if backend is unreachable.
// ============================================================

import type {
  TreeResponse,
  EntityProperties,
  RelationshipEdge,
  TableMetrics,
  SearchResult,
  ExpandResponse,
  TreeStats,
} from "./types";

const BASE = "/api/fkrte";

async function _get<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path);
  if (!res.ok) throw new Error(`FKRTE API ${path}: ${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

// ── Tree ────────────────────────────────────────────────────
export async function fetchTree(force = false): Promise<TreeResponse> {
  return _get<TreeResponse>(`/tree${force ? "?force=true" : ""}`);
}

// ── Entity ──────────────────────────────────────────────────
export async function fetchEntity(id: string): Promise<EntityProperties> {
  return _get<EntityProperties>(`/entity/${encodeURIComponent(id)}`);
}

// ── Expand ──────────────────────────────────────────────────
export async function fetchExpand(
  entityId: string,
  visited: string[] = []
): Promise<ExpandResponse> {
  const v = visited.length ? `?visited=${visited.join(",")}` : "";
  return _get<ExpandResponse>(`/expand/${encodeURIComponent(entityId)}${v}`);
}

// ── Relationship ─────────────────────────────────────────────
export async function fetchRelationship(edgeId: string): Promise<RelationshipEdge> {
  return _get<RelationshipEdge>(`/relationship/${encodeURIComponent(edgeId)}`);
}

// ── Relationships for entity ─────────────────────────────────
export async function fetchRelationshipsForEntity(
  entityId: string,
  minConfidence = 0
): Promise<{ relationships: RelationshipEdge[]; count: number }> {
  return _get(`/relationships?entity_id=${encodeURIComponent(entityId)}&min_confidence=${minConfidence}`);
}

// ── Table metrics ────────────────────────────────────────────
export async function fetchTable(id: string): Promise<TableMetrics> {
  return _get<TableMetrics>(`/table/${encodeURIComponent(id)}`);
}

// ── Search ───────────────────────────────────────────────────
export async function fetchSearch(
  q: string,
  opts: {
    minQuality?: number;
    minConfidence?: number;
    hasLCIL?: boolean | null;
    isOrphan?: boolean | null;
    minFkCount?: number;
  } = {}
): Promise<{ query: string; results: SearchResult[]; count: number }> {
  const params = new URLSearchParams({ q });
  if (opts.minQuality) params.set("min_quality", String(opts.minQuality));
  if (opts.minConfidence) params.set("min_confidence", String(opts.minConfidence));
  if (opts.hasLCIL != null) params.set("has_lcil", String(opts.hasLCIL));
  if (opts.isOrphan != null) params.set("is_orphan", String(opts.isOrphan));
  if (opts.minFkCount) params.set("min_fk_count", String(opts.minFkCount));
  return _get(`/search?${params.toString()}`);
}

// ── All entities list ─────────────────────────────────────────
export async function fetchEntities(
  opts: {
    minQuality?: number;
    minFkCount?: number;
    hasLCIL?: boolean | null;
    isOrphan?: boolean | null;
    limit?: number;
    offset?: number;
  } = {}
): Promise<{ entities: EntityProperties[]; total: number }> {
  const params = new URLSearchParams();
  if (opts.minQuality) params.set("min_quality", String(opts.minQuality));
  if (opts.minFkCount) params.set("min_fk_count", String(opts.minFkCount));
  if (opts.hasLCIL != null) params.set("has_lcil", String(opts.hasLCIL));
  if (opts.isOrphan != null) params.set("is_orphan", String(opts.isOrphan));
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.offset) params.set("offset", String(opts.offset));
  return _get(`/entities?${params.toString()}`);
}

// ── Stats ─────────────────────────────────────────────────────
export async function fetchStats(): Promise<TreeStats & {
  orphan_tables: number;
  tables_with_lcil: number;
}> {
  return _get("/stats");
}

// ── Rebuild ───────────────────────────────────────────────────
export async function triggerRebuild(): Promise<{ ok: boolean; stats: TreeStats }> {
  const res = await fetch(`${BASE}/rebuild`, { method: "POST" });
  return res.json();
}
