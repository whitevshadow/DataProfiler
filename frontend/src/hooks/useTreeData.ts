/**
 * useTreeData
 * Hook for loading and managing FKRTE tree data
 */
import { useState, useEffect, useCallback } from 'react';

export interface TreeNode {
  id: string;
  label: string;
  has_children: boolean;
  children: TreeNode[];
  edge?: {
    fk_column: string;
    pk_column: string;
    confidence: number;
    containment: number;
    semantic_similarity: number;
    reasoning: string[];
    relationship_class: string;
  };
  truncated?: boolean;
  expanded?: boolean;
}

export interface EntityDetail {
  id: string;
  label: string;
  row_count: number;
  column_count: number;
  quality_score: number;
  completeness: number;
  pk: string;
  pk_confidence: number;
  fk_count: number;
  pk_candidates: string[];
  fk_candidates: string[];
  columns: Array<{
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
  }>;
  quality_flags: number;
  related_children: string[];
  related_parents: string[];
  lcil_domains: string[];
  is_orphan: boolean;
}

export interface RelationshipDetail {
  id: string;
  fk_table: string;
  fk_table_label: string;
  fk_column: string;
  pk_table: string;
  pk_table_label: string;
  pk_column: string;
  relationship_class: string;
  confidence: number;
  containment: number;
  semantic_similarity: number;
  reasoning: string[];
}

export interface TreeStats {
  total_tables: number;
  true_fk_count: number;
  orphan_tables: number;
  tables_with_lcil: number;
  root_nodes: number;
}

const API_BASE = 'http://127.0.0.1:5500/api/fkrte';

export function useTreeData() {
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [stats, setStats] = useState<TreeStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTree = useCallback(async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const url = force ? `${API_BASE}/tree?force=true` : `${API_BASE}/tree`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setTree(data.tree || []);
      setStats(data.stats || null);
    } catch (err: any) {
      setError(err.message);
      console.error('Failed to load tree:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  return { tree, stats, loading, error, reload: loadTree };
}

export function useEntityDetail(entityId: string | null) {
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!entityId) {
      setEntity(null);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/entity/${encodeURIComponent(entityId)}`)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => setEntity(data))
      .catch(err => {
        setError(err.message);
        console.error('Failed to load entity:', err);
      })
      .finally(() => setLoading(false));
  }, [entityId]);

  return { entity, loading, error };
}

export function useRelationshipDetail(edgeId: string | null) {
  const [relationship, setRelationship] = useState<RelationshipDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!edgeId) {
      setRelationship(null);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/relationship/${encodeURIComponent(edgeId)}`)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => setRelationship(data))
      .catch(err => {
        setError(err.message);
        console.error('Failed to load relationship:', err);
      })
      .finally(() => setLoading(false));
  }, [edgeId]);

  return { relationship, loading, error };
}

export async function expandEntity(entityId: string, visited: string[]): Promise<TreeNode[]> {
  const visitedStr = visited.join(',');
  const url = `${API_BASE}/expand/${encodeURIComponent(entityId)}?visited=${encodeURIComponent(visitedStr)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return data.children || [];
}

export async function searchTree(query: string, filters?: {
  min_quality?: number;
  has_lcil?: boolean;
  is_orphan?: boolean;
  min_fk_count?: number;
}) {
  const params = new URLSearchParams({ q: query });
  if (filters?.min_quality !== undefined) params.set('min_quality', filters.min_quality.toString());
  if (filters?.has_lcil !== undefined) params.set('has_lcil', filters.has_lcil.toString());
  if (filters?.is_orphan !== undefined) params.set('is_orphan', filters.is_orphan.toString());
  if (filters?.min_fk_count !== undefined) params.set('min_fk_count', filters.min_fk_count.toString());
  
  const res = await fetch(`${API_BASE}/search?${params}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
