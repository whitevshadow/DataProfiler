"""
LCIL Data Models

Pydantic models for Low Cardinality Intelligence Layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SemanticDomain(str, Enum):
    """Semantic domain classifications for low-cardinality columns."""
    
    # Financial & Commerce
    PAYMENT_METHOD = "PaymentMethod"
    DELIVERY_METHOD = "DeliveryMethod"
    TRANSACTION_TYPE = "TransactionType"
    CURRENCY_CODE = "CurrencyCode"
    
    # Product & Inventory
    PACKAGING_TYPE = "PackagingType"
    PRODUCT_CATEGORY = "ProductCategory"
    STOCK_GROUP = "StockGroup"
    COLOR = "Color"
    SIZE = "Size"
    
    # Geographic
    GEO_ENTITY = "GeoEntity"
    COUNTRY = "Country"
    STATE_PROVINCE = "StateProvince"
    CITY = "City"
    REGION = "Region"
    
    # Business Classification
    CUSTOMER_CATEGORY = "CustomerCategory"
    SUPPLIER_CATEGORY = "SupplierCategory"
    BUYING_GROUP = "BuyingGroup"
    
    # Workflow & Status
    STATUS = "Status"
    WORKFLOW_STATE = "WorkflowState"
    PRIORITY = "Priority"
    RISK_LEVEL = "RiskLevel"
    SEVERITY = "Severity"
    
    # Boolean & Binary
    BOOLEAN_FLAG = "BooleanFlag"
    YES_NO = "YesNo"
    
    # Other
    DIMENSION = "Dimension"
    CATEGORY = "Category"
    UNKNOWN = "Unknown"


class GraphNode(BaseModel):
    """Node in the suggested knowledge graph."""
    
    id: str = Field(..., description="Unique node identifier")
    label: str = Field(..., description="Human-readable node label")
    node_type: str = Field(..., description="Node type (Domain, Entity, Value, etc.)")
    properties: dict[str, Any] = Field(default_factory=dict, description="Additional node properties")


class GraphEdge(BaseModel):
    """Edge in the suggested knowledge graph."""
    
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    relationship: str = Field(..., description="Relationship type")
    properties: dict[str, Any] = Field(default_factory=dict, description="Additional edge properties")


class LCILInsight(BaseModel):
    """Per-column LCIL enrichment insight."""
    
    table_name: str = Field(..., description="Source table name")
    column_name: str = Field(..., description="Column name")
    semantic_domain: str = Field(..., description="Detected semantic domain (PascalCase)")
    business_meaning: str = Field(..., description="Business-friendly description")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    
    # Flags
    is_ordered: bool = Field(default=False, description="Values have natural ordering")
    is_hierarchical: bool = Field(default=False, description="Values form a hierarchy")
    is_workflow: bool = Field(default=False, description="Represents workflow/lifecycle states")
    is_boolean: bool = Field(default=False, description="Boolean-like values")
    
    # Entity & Ontology
    suggested_entity: Optional[str] = Field(None, description="Suggested entity type (PascalCase)")
    ontology_tags: list[str] = Field(default_factory=list, description="Normalized ontology tags")
    
    # Additional insights
    insights: list[str] = Field(default_factory=list, description="Additional semantic insights")
    evidence: list[str] = Field(default_factory=list, description="Evidence supporting classification")
    
    # Graph suggestions
    graph_nodes: list[GraphNode] = Field(default_factory=list, description="Suggested graph nodes")
    graph_edges: list[GraphEdge] = Field(default_factory=list, description="Suggested graph edges")


class LCILReport(BaseModel):
    """Complete LCIL report artifact."""
    
    schema_version: str = Field(default="1.0", description="Report schema version")
    artifact_type: str = Field(default="low_cardinality_insights", description="Artifact type identifier")
    generated_at: datetime = Field(default_factory=datetime.now, description="Generation timestamp")
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Generation metadata")
    
    # Summary
    summary: dict[str, Any] = Field(default_factory=dict, description="Summary statistics")
    
    # Insights
    insights: list[LCILInsight] = Field(default_factory=list, description="Per-column insights")


class LCILCandidate(BaseModel):
    """Internal candidate for LCIL enrichment."""
    
    table_name: str
    column_name: str
    distinct_count: int
    logical_type: Optional[str] = None
    physical_type: Optional[str] = None
    semantic_type: Optional[str] = None
    
    # Evidence from profile
    top_values: list[tuple[Any, int]] = Field(default_factory=list)
    sample_values: list[Any] = Field(default_factory=list)
    
    # Evidence from canonical (if available)
    canonical_samples: list[Any] = Field(default_factory=list)
