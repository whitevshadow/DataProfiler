"""
Tests for LCIL LLM Mapper

Tests LLM normalization and validation logic (without making real API calls).
"""

import pytest
from profiler.lcil.models import LCILCandidate
from profiler.lcil.llm_mapper import (
    _normalize_insight,
    _get_observed_values,
    _create_fallback_insight,
    _parse_llm_response,
)


def test_normalize_insight_valid_json():
    """Test normalization of valid LLM output."""
    raw = {
        "table_name": "application_paymentmethods",
        "column_name": "paymentmethodname",
        "semantic_domain": "PaymentMethod",
        "business_meaning": "Method of payment accepted",
        "confidence": 0.95,
        "is_ordered": False,
        "is_hierarchical": False,
        "is_workflow": False,
        "is_boolean": False,
        "suggested_entity": "PaymentMethod",
        "ontology_tags": ["payment", "commerce", "transaction"],
        "insights": ["Used for payment processing"],
        "evidence": ["Contains payment method names"],
        "graph_nodes": [
            {"id": "PaymentMethod", "label": "Payment Method", "node_type": "Domain", "properties": {}},
        ],
        "graph_edges": [],
    }
    
    candidate = LCILCandidate(
        table_name="application_paymentmethods",
        column_name="paymentmethodname",
        distinct_count=4,
        logical_type="category",
        physical_type="string",
        semantic_type=None,
        top_values=[["Cash", 10], ["Credit Card", 8]],
        sample_values=["Cash", "Credit Card"],
        canonical_samples=[],
    )
    
    insight = _normalize_insight(raw, [candidate], min_confidence=0.6)
    
    assert insight is not None
    assert insight.semantic_domain == "PaymentMethod"
    assert insight.confidence == 0.95
    assert "payment" in insight.ontology_tags
    assert len(insight.graph_nodes) == 1


def test_normalize_insight_low_confidence_becomes_unknown():
    """Test that low confidence classifications become Unknown."""
    raw = {
        "table_name": "test_table",
        "column_name": "testcol",
        "semantic_domain": "SomeDomain",
        "business_meaning": "Test meaning",
        "confidence": 0.3,  # Below threshold
        "is_ordered": False,
        "is_hierarchical": False,
        "is_workflow": False,
        "is_boolean": False,
        "suggested_entity": "TestEntity",
        "ontology_tags": ["test"],
        "insights": [],
        "evidence": [],
        "graph_nodes": [],
        "graph_edges": [],
    }
    
    candidate = LCILCandidate(
        table_name="test_table",
        column_name="testcol",
        distinct_count=5,
        top_values=[],
        sample_values=[],
        canonical_samples=[],
    )
    
    insight = _normalize_insight(raw, [candidate], min_confidence=0.6)
    
    assert insight is not None
    assert insight.semantic_domain == "Unknown"
    assert insight.confidence == 0.3  # Confidence preserved but domain changed


def test_normalize_insight_clamps_confidence():
    """Test that confidence is clamped to 0.0-1.0 range."""
    raw = {
        "table_name": "test_table",
        "column_name": "testcol",
        "semantic_domain": "TestDomain",
        "business_meaning": "Test",
        "confidence": 1.5,  # Invalid (too high)
        "is_ordered": False,
        "is_hierarchical": False,
        "is_workflow": False,
        "is_boolean": False,
        "suggested_entity": None,
        "ontology_tags": [],
        "insights": [],
        "evidence": [],
        "graph_nodes": [],
        "graph_edges": [],
    }
    
    candidate = LCILCandidate(
        table_name="test_table",
        column_name="testcol",
        distinct_count=5,
        top_values=[],
        sample_values=[],
        canonical_samples=[],
    )
    
    insight = _normalize_insight(raw, [candidate], min_confidence=0.0)
    
    assert insight is not None
    assert insight.confidence == 1.0  # Clamped to max


def test_normalize_insight_dedupes_ontology_tags():
    """Test that duplicate ontology tags are removed."""
    raw = {
        "table_name": "test_table",
        "column_name": "testcol",
        "semantic_domain": "TestDomain",
        "business_meaning": "Test",
        "confidence": 0.8,
        "is_ordered": False,
        "is_hierarchical": False,
        "is_workflow": False,
        "is_boolean": False,
        "suggested_entity": None,
        "ontology_tags": ["payment", "commerce", "payment", "PAYMENT"],  # Duplicates
        "insights": [],
        "evidence": [],
        "graph_nodes": [],
        "graph_edges": [],
    }
    
    candidate = LCILCandidate(
        table_name="test_table",
        column_name="testcol",
        distinct_count=5,
        top_values=[],
        sample_values=[],
        canonical_samples=[],
    )
    
    insight = _normalize_insight(raw, [candidate], min_confidence=0.0)
    
    assert insight is not None
    assert len(insight.ontology_tags) == 2  # payment and commerce (deduplicated)


def test_normalize_insight_removes_hallucinated_value_nodes():
    """Test that unobserved value nodes are filtered out."""
    raw = {
        "table_name": "application_paymentmethods",
        "column_name": "paymentmethodname",
        "semantic_domain": "PaymentMethod",
        "business_meaning": "Payment method",
        "confidence": 0.9,
        "is_ordered": False,
        "is_hierarchical": False,
        "is_workflow": False,
        "is_boolean": False,
        "suggested_entity": None,
        "ontology_tags": [],
        "insights": [],
        "evidence": [],
        "graph_nodes": [
            # Domain node (should be kept)
            {"id": "PaymentMethod", "label": "Payment Method", "node_type": "Domain", "properties": {}},
            # Observed value node (should be kept)
            {"id": "Cash", "label": "Cash", "node_type": "Value", "properties": {}},
            # Hallucinated value node (should be removed)
            {"id": "Bitcoin", "label": "Bitcoin", "node_type": "Value", "properties": {}},
        ],
        "graph_edges": [],
    }
    
    candidate = LCILCandidate(
        table_name="application_paymentmethods",
        column_name="paymentmethodname",
        distinct_count=4,
        top_values=[["Cash", 10], ["Credit Card", 8]],
        sample_values=["Cash", "Credit Card"],
        canonical_samples=[],
    )
    
    insight = _normalize_insight(raw, [candidate], min_confidence=0.0)
    
    assert insight is not None
    assert len(insight.graph_nodes) == 2  # Domain + Cash only
    node_labels = [node.label for node in insight.graph_nodes]
    assert "Payment Method" in node_labels
    assert "Cash" in node_labels
    assert "Bitcoin" not in node_labels  # Hallucinated, removed


def test_get_observed_values():
    """Test extraction of all observed values from a candidate."""
    candidate = LCILCandidate(
        table_name="test_table",
        column_name="testcol",
        distinct_count=5,
        top_values=[["Value1", 10], ["Value2", 8], ["Value3", 5]],
        sample_values=["Value1", "Value4"],
        canonical_samples=["Value5", "Value1"],  # Overlap with top_values
    )
    
    observed = _get_observed_values(candidate)
    
    assert len(observed) == 5  # Value1-5, no duplicates
    assert "Value1" in observed
    assert "Value2" in observed
    assert "Value3" in observed
    assert "Value4" in observed
    assert "Value5" in observed


def test_create_fallback_insight():
    """Test fallback insight creation when LLM fails."""
    candidate = LCILCandidate(
        table_name="test_table",
        column_name="testcol",
        distinct_count=5,
        top_values=[],
        sample_values=[],
        canonical_samples=[],
    )
    
    insight = _create_fallback_insight(candidate)
    
    assert insight.table_name == "test_table"
    assert insight.column_name == "testcol"
    assert insight.semantic_domain == "Unknown"
    assert insight.confidence == 0.0
    assert "LLM call failed" in insight.evidence


def test_parse_llm_response_strips_markdown():
    """Test that markdown code blocks are stripped from LLM response."""
    response_with_markdown = '''```json
[
  {
    "table_name": "test",
    "column_name": "col1",
    "semantic_domain": "TestDomain",
    "business_meaning": "Test",
    "confidence": 0.8,
    "is_ordered": false,
    "is_hierarchical": false,
    "is_workflow": false,
    "is_boolean": false,
    "suggested_entity": null,
    "ontology_tags": [],
    "insights": [],
    "evidence": [],
    "graph_nodes": [],
    "graph_edges": []
  }
]
```'''
    
    candidate = LCILCandidate(
        table_name="test",
        column_name="col1",
        distinct_count=3,
        top_values=[],
        sample_values=[],
        canonical_samples=[],
    )
    
    parsed = _parse_llm_response(response_with_markdown, [candidate])
    
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["table_name"] == "test"


def test_parse_llm_response_handles_invalid_json():
    """Test that invalid JSON is handled gracefully."""
    invalid_json = "This is not valid JSON at all"
    
    candidate = LCILCandidate(
        table_name="test",
        column_name="col1",
        distinct_count=3,
        top_values=[],
        sample_values=[],
        canonical_samples=[],
    )
    
    parsed = _parse_llm_response(invalid_json, [candidate])
    
    assert isinstance(parsed, list)
    assert len(parsed) == 0  # Should return empty list on parse error
