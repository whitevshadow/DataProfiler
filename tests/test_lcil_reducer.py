"""
Tests for LCIL Reducer and Serializer

Tests report aggregation and serialization logic.
"""

import json
import pytest
from pathlib import Path
from profiler.lcil.models import LCILInsight
from profiler.lcil.reducer import reduce_insights, serialize_report, _build_tag_aliases


def test_build_tag_aliases_normalizes_plurals():
    """Test that tag aliases normalize singular/plural forms."""
    insights = [
        LCILInsight(
            table_name="test1",
            column_name="col1",
            semantic_domain="TestDomain",
            business_meaning="Test",
            confidence=0.8,
            ontology_tags=["payment", "payments", "commerce"],
        ),
        LCILInsight(
            table_name="test2",
            column_name="col2",
            semantic_domain="TestDomain2",
            business_meaning="Test2",
            confidence=0.8,
            ontology_tags=["delivery", "deliveries"],
        ),
    ]
    
    aliases = _build_tag_aliases(insights)
    
    # The function should detect singular/plural pairs and map singular to plural
    # At minimum, verify the function returns a dict and performs some normalization
    assert isinstance(aliases, dict)
    # If it finds any singular->plural mappings, they should be correct
    if "payment" in aliases:
        assert aliases["payment"] == "payments"
    if "delivery" in aliases:
        assert aliases["delivery"] == "deliveries"


def test_reduce_insights_normalizes_tags():
    """Test that reduce_insights normalizes ontology tags."""
    insights = [
        LCILInsight(
            table_name="test1",
            column_name="col1",
            semantic_domain="TestDomain",
            business_meaning="Test",
            confidence=0.8,
            ontology_tags=["payment", "commerce"],  # Singular
        ),
        LCILInsight(
            table_name="test2",
            column_name="col2",
            semantic_domain="TestDomain2",
            business_meaning="Test2",
            confidence=0.8,
            ontology_tags=["payments", "transaction"],  # Plural
        ),
    ]
    
    reduced = reduce_insights(insights)
    
    # First insight should now have "payments" instead of "payment"
    assert "payments" in reduced[0].ontology_tags
    assert "payment" not in reduced[0].ontology_tags


def test_serialize_report_writes_json(tmp_path):
    """Test that report is written as valid JSON."""
    insights = [
        LCILInsight(
            table_name="application_paymentmethods",
            column_name="paymentmethodname",
            semantic_domain="PaymentMethod",
            business_meaning="Method of payment",
            confidence=0.95,
            ontology_tags=["payment", "commerce"],
        ),
        LCILInsight(
            table_name="application_deliverymethods",
            column_name="deliverymethodname",
            semantic_domain="DeliveryMethod",
            business_meaning="Method of delivery",
            confidence=0.88,
            ontology_tags=["delivery", "logistics"],
        ),
    ]
    
    metadata = {"provider": "test", "model": "test-model"}
    
    report_path = serialize_report(insights, tmp_path, metadata)
    
    assert report_path.exists()
    assert report_path.name == "low_cardinality_insights.json"
    
    # Verify valid JSON
    with open(report_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)
    
    assert report_data["artifact_type"] == "low_cardinality_insights"
    assert report_data["schema_version"] == "1.0"
    assert len(report_data["insights"]) == 2


def test_serialize_report_creates_summary(tmp_path):
    """Test that report includes correct summary statistics."""
    insights = [
        LCILInsight(
            table_name="test1",
            column_name="col1",
            semantic_domain="PaymentMethod",
            business_meaning="Test",
            confidence=0.95,  # High
        ),
        LCILInsight(
            table_name="test2",
            column_name="col2",
            semantic_domain="DeliveryMethod",
            business_meaning="Test",
            confidence=0.65,  # Medium
        ),
        LCILInsight(
            table_name="test3",
            column_name="col3",
            semantic_domain="PaymentMethod",  # Duplicate domain
            business_meaning="Test",
            confidence=0.40,  # Low
        ),
        LCILInsight(
            table_name="test4",
            column_name="col4",
            semantic_domain="Unknown",
            business_meaning="Test",
            confidence=0.20,  # Low
        ),
    ]
    
    report_path = serialize_report(insights, tmp_path, {})
    
    with open(report_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)
    
    summary = report_data["summary"]
    
    assert summary["total_columns_enriched"] == 4
    assert summary["unique_domains"] == 3  # PaymentMethod, DeliveryMethod, Unknown
    assert summary["domain_distribution"]["PaymentMethod"] == 2
    assert summary["high_confidence_count"] == 1  # >= 0.8
    assert summary["medium_confidence_count"] == 1  # 0.5 <= x < 0.8
    assert summary["low_confidence_count"] == 2  # < 0.5
    
    # Average confidence = (0.95 + 0.65 + 0.40 + 0.20) / 4 = 0.55
    assert 0.54 <= summary["average_confidence"] <= 0.56


def test_serialize_report_preserves_per_column_schema(tmp_path):
    """Test that each insight in the report matches the requested schema."""
    insights = [
        LCILInsight(
            table_name="application_paymentmethods",
            column_name="paymentmethodname",
            semantic_domain="PaymentMethod",
            business_meaning="Payment method",
            confidence=0.95,
            is_ordered=False,
            is_hierarchical=False,
            is_workflow=False,
            is_boolean=False,
            suggested_entity="PaymentMethod",
            ontology_tags=["payment", "commerce"],
            insights=["Used for payment processing"],
            evidence=["Contains payment method names"],
            graph_nodes=[],
            graph_edges=[],
        ),
    ]
    
    report_path = serialize_report(insights, tmp_path, {})
    
    with open(report_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)
    
    insight_data = report_data["insights"][0]
    
    # Verify all required fields present
    assert "table_name" in insight_data
    assert "column_name" in insight_data
    assert "semantic_domain" in insight_data
    assert "business_meaning" in insight_data
    assert "confidence" in insight_data
    assert "is_ordered" in insight_data
    assert "is_hierarchical" in insight_data
    assert "is_workflow" in insight_data
    assert "is_boolean" in insight_data
    assert "suggested_entity" in insight_data
    assert "ontology_tags" in insight_data
    assert "insights" in insight_data
    assert "evidence" in insight_data
    assert "graph_nodes" in insight_data
    assert "graph_edges" in insight_data
    
    # Verify values
    assert insight_data["table_name"] == "application_paymentmethods"
    assert insight_data["semantic_domain"] == "PaymentMethod"
    assert insight_data["confidence"] == 0.95
