export type RelationshipClass = "TRUE_FK" | "SEMANTICALLY_RELATED" | "SHARED_ENTITY_DOMAIN" | "POSSIBLE_REFERENCE" | "UNKNOWN";

export type DiagramNode = {
  id: string;
  name: string;
  module: string;
  collapsed: boolean;
  row_count: number;
  quality: number;
  column_count: number;
  pk_columns: string[];
  fk_columns: string[];
  columns: Array<{
    name: string;
    type: string;
    pk: boolean;
    fk: boolean;
    quality: number;
    cardinality: string;
  }>;
};

export type DiagramEdge = {
  id: string;
  source: string;
  target: string;
  source_column: string;
  target_column: string;
  relationship_class: RelationshipClass;
  confidence: number;
  containment_ratio: number;
  semantic_similarity: number;
  reasoning: string[];
};

export type DiagramState = {
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  metrics: {
    table_count: number;
    relationship_count: number;
    min_confidence: number;
    relationship_classes: string[];
  };
};

export type TableDetail = {
  table: string;
  row_count: number;
  quality: number;
  pk_columns: string[];
  columns: ColumnInsight[];
};

export type ColumnInsight = {
  table: string;
  column: string;
  type: string;
  semantic: string;
  quality: number;
  cardinality: string;
  null_ratio: number;
  pk_confidence: number;
  fk_confidence: number;
  relationships: string[];
  top_values: string[];
  business_meaning: string;
  ontology_tags: string[];
};

export type RelationshipDetail = {
  id: string;
  relationship_class: RelationshipClass;
  confidence: number;
  containment_ratio: number;
  semantic_similarity: number;
  reasoning: string[];
  fk_table: string;
  fk_column: string;
  pk_table: string;
  pk_column: string;
};

export type TraceEvent = {
  id: string;
  layer: string;
  duration?: string;
  rows?: number;
  columns?: number;
  warnings?: string[];
  outputs?: string[];
};
