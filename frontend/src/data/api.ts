import { ColumnInsight, DiagramState, RelationshipDetail, TableDetail } from "../types";

export async function fetchDiagramState(params: {
  minConfidence?: number;
  relationshipClasses?: string[];
  topK?: number;
} = {}): Promise<DiagramState> {
  const query = new URLSearchParams();
  if (params.minConfidence !== undefined) query.set("min_confidence", String(params.minConfidence));
  if (params.topK !== undefined) query.set("top_k", String(params.topK));
  if (params.relationshipClasses?.length) query.set("relationship_classes", params.relationshipClasses.join(","));
  const res = await fetch(`/api/diagram/state?${query.toString()}`);
  if (!res.ok) throw new Error("Failed to load diagram state");
  return res.json();
}

export async function fetchTableDetail(tableId: string): Promise<TableDetail> {
  const res = await fetch(`/api/diagram/table/${encodeURIComponent(tableId)}`);
  if (!res.ok) throw new Error("Failed to load table detail");
  return res.json();
}

export async function fetchColumnInsight(columnId: string): Promise<ColumnInsight> {
  const res = await fetch(`/api/diagram/column/${encodeURIComponent(columnId)}`);
  if (!res.ok) throw new Error("Failed to load column insight");
  return res.json();
}

export async function fetchRelationshipDetail(edgeId: string): Promise<RelationshipDetail> {
  const res = await fetch(`/api/diagram/relationship/${encodeURIComponent(edgeId)}`);
  if (!res.ok) throw new Error("Failed to load relationship detail");
  return res.json();
}

export async function fetchDbml(): Promise<string> {
  const res = await fetch(`/api/diagram/dbml`);
  if (!res.ok) throw new Error("Failed to load DBML");
  return res.text();
}
