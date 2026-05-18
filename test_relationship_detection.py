"""
Comprehensive Test Suite for Relationship Detection Layer

Tests all major components:
    - Type compatibility
    - Candidate pair generation
    - Bloom filter pruning
    - Containment validation
    - Confidence scoring
    - FK suppression
    - End-to-end relationship detection
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from relationships.type_compatibility import check_type_compatibility
from relationships.candidate_pair_generator import CandidatePairGenerator
from relationships.bloom_filter_engine import BloomFilterEngine
from relationships.containment_validator import ContainmentValidator
from relationships.confidence_engine import ConfidenceEngine
from relationships.suppression_rules import should_suppress_fk
from relationships.relationship_engine import RelationshipEngine
from relationships.relationship_serializer import save_relationship_report


def test_type_compatibility():
    """Test type compatibility engine."""
    print("\n" + "=" * 80)
    print("TEST: Type Compatibility Engine")
    print("=" * 80)
    
    # Test exact match
    result = check_type_compatibility("INTEGER", "INTEGER")
    assert result.compatible
    assert result.compatibility_score == 1.0
    print(f"[OK] INTEGER <-> INTEGER: {result.compatibility_score}")
    
    # Test coercion
    result = check_type_compatibility("INTEGER", "BIGINT")
    assert result.compatible
    assert result.compatibility_score >= 0.9
    print(f"[OK] INTEGER <-> BIGINT: {result.compatibility_score} (coercion)")
    
    # Test UUID <-> STRING
    result = check_type_compatibility("UUID", "STRING")
    assert result.compatible
    assert result.compatibility_score >= 0.8
    print(f"[OK] UUID <-> STRING: {result.compatibility_score}")
    
    # Test incompatible
    result = check_type_compatibility("BOOLEAN", "INTEGER")
    assert result.compatibility_score < 0.5
    print(f"[OK] BOOLEAN <-> INTEGER: {result.compatibility_score} (low compatibility)")
    
    print("\n[PASSED] Type compatibility tests")


def test_candidate_pair_generation():
    """Test candidate pair generator."""
    print("\n" + "=" * 80)
    print("TEST: Candidate Pair Generation")
    print("=" * 80)
    
    # Mock table profiles
    table_profiles = {
        "orders": {
            "columns": [
                {"column_name": "order_id", "physical_type": "INTEGER", "distinct_count": 1000},
                {"column_name": "customer_id", "physical_type": "INTEGER", "distinct_count": 500},
                {"column_name": "product_id", "physical_type": "INTEGER", "distinct_count": 200},
            ]
        },
        "customers": {
            "columns": [
                {"column_name": "customer_id", "physical_type": "INTEGER", "distinct_count": 500},
                {"column_name": "name", "physical_type": "STRING", "distinct_count": 500},
            ]
        },
        "products": {
            "columns": [
                {"column_name": "product_id", "physical_type": "INTEGER", "distinct_count": 200},
                {"column_name": "name", "physical_type": "STRING", "distinct_count": 200},
            ]
        },
    }
    
    # Mock PK candidates
    pk_candidates = {
        "orders": [
            {"column": "order_id", "confidence": 0.95, "accepted": True, "physical_type": "INTEGER", "distinct_count": 1000}
        ],
        "customers": [
            {"column": "customer_id", "confidence": 0.95, "accepted": True, "physical_type": "INTEGER", "distinct_count": 500}
        ],
        "products": [
            {"column": "product_id", "confidence": 0.95, "accepted": True, "physical_type": "INTEGER", "distinct_count": 200}
        ],
    }
    
    generator = CandidatePairGenerator()
    candidates = generator.generate_candidates(table_profiles, pk_candidates)
    
    print(f"Generated {len(candidates)} candidate pairs:")
    for candidate in candidates:
        print(f"  {candidate.fk_table}.{candidate.fk_column} -> {candidate.pk_table}.{candidate.pk_column}")
        print(f"    Reason: {candidate.generation_reason}, Naming similarity: {candidate.naming_similarity:.2f}")
    
    # Should generate at least 2 candidates (customer_id and product_id)
    assert len(candidates) >= 2, f"Expected at least 2 candidates, got {len(candidates)}"
    
    # Should have customer_id candidates
    customer_id_candidates = [c for c in candidates if c.fk_column == "customer_id"]
    assert len(customer_id_candidates) > 0, "No customer_id FK candidates found"
    
    # Should have product_id candidates
    product_id_candidates = [c for c in candidates if c.fk_column == "product_id"]
    assert len(product_id_candidates) > 0, "No product_id FK candidates found"
    
    print(f"\n[OK] Found {len(customer_id_candidates)} customer_id candidates")
    print(f"[OK] Found {len(product_id_candidates)} product_id candidates")
    
    print("\n[PASSED] Candidate pair generation tests")


def test_bloom_filter():
    """Test Bloom filter engine."""
    print("\n" + "=" * 80)
    print("TEST: Bloom Filter Engine")
    print("=" * 80)
    
    # Build Bloom filter with PK values
    pk_values = list(range(1, 10001))  # 10,000 PKs
    
    bloom_engine = BloomFilterEngine()
    bloom = bloom_engine.build_bloom_filter(pk_values)
    
    print(f"Built Bloom filter for {len(pk_values)} PK values")
    print(f"Memory usage: {bloom.get_memory_usage_bytes()} bytes")
    print(f"False positive rate: {bloom.get_actual_false_positive_rate():.4f}")
    
    # Test membership
    assert bloom.contains(5000)  # Should be present
    assert bloom.contains(1)  # Should be present
    assert not bloom.contains(99999)  # Definitely not present (with high probability)
    
    # Test overlap estimation
    fk_values = [1, 2, 3, 99999, 99998]  # 3 present, 2 missing
    overlap = bloom_engine.estimate_overlap(fk_values, bloom)
    
    print(f"FK sample overlap: {overlap.overlap_count}/{len(fk_values)} = {overlap.overlap_ratio:.2f}")
    
    # Should reject if overlap too low
    low_overlap_fk = list(range(90000, 90100))  # All missing
    should_reject = bloom_engine.should_reject_candidate(low_overlap_fk, bloom, rejection_threshold=0.10)
    assert should_reject
    print(f"[OK] Low overlap correctly rejected")
    
    print("\n[PASSED] Bloom filter tests")


def test_containment_validation():
    """Test containment validator."""
    print("\n" + "=" * 80)
    print("TEST: Containment Validation")
    print("=" * 80)
    
    validator = ContainmentValidator()
    
    # Perfect containment
    fk_values = [1, 2, 3, 4, 5]
    pk_values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    
    result = validator.validate_containment_full(fk_values, pk_values)
    print(f"Perfect containment: {result.containment_ratio:.2f}")
    assert result.contained
    assert result.containment_ratio == 1.0
    assert result.orphan_count == 0
    print(f"[OK] Perfect containment validated")
    
    # Partial containment
    fk_values = [1, 2, 3, 99, 100]  # 3 contained, 2 orphans
    pk_values = [1, 2, 3, 4, 5]
    
    result = validator.validate_containment_full(fk_values, pk_values)
    print(f"Partial containment: {result.containment_ratio:.2f}")
    print(f"Orphans: {result.orphan_count}")
    assert result.containment_ratio == 0.6  # 3/5
    assert result.orphan_count == 2
    assert not result.contained  # Below acceptable threshold
    print(f"[OK] Partial containment detected")
    
    # No containment
    fk_values = [99, 100, 101]
    pk_values = [1, 2, 3]
    
    result = validator.validate_containment_full(fk_values, pk_values)
    print(f"No containment: {result.containment_ratio:.2f}")
    assert result.containment_ratio == 0.0
    assert result.orphan_count == 3
    print(f"[OK] No containment detected")
    
    print("\n[PASSED] Containment validation tests")


def test_confidence_scoring():
    """Test confidence scoring engine."""
    print("\n" + "=" * 80)
    print("TEST: Confidence Scoring Engine")
    print("=" * 80)
    
    engine = ConfidenceEngine()
    
    # Strong FK relationship
    confidence = engine.compute_confidence(
        containment_ratio=1.0,
        overlap_ratio=0.95,
        type_compatibility_score=1.0,
        pk_confidence=0.95,
        naming_similarity=0.95,
        null_ratio_fk=0.0,
        cardinality_ratio=0.80,
    )
    print(f"Strong FK confidence: {confidence:.4f}")
    assert confidence >= 0.90
    print(f"[OK] Strong FK scored highly")
    
    # Weak FK (low containment)
    confidence = engine.compute_confidence(
        containment_ratio=0.60,  # Below threshold
        overlap_ratio=0.50,
        type_compatibility_score=0.8,
        pk_confidence=0.90,
        naming_similarity=0.70,
        null_ratio_fk=0.0,
    )
    print(f"Weak FK confidence: {confidence:.4f}")
    assert confidence < 0.75  # Should be penalized
    print(f"[OK] Weak FK scored low due to containment")
    
    # Explain confidence
    explanation = engine.explain_confidence(
        containment_ratio=0.95,
        overlap_ratio=0.90,
        type_compatibility_score=0.95,
        pk_confidence=0.90,
        naming_similarity=0.80,
    )
    print(f"Confidence breakdown:")
    for key, value in explanation.items():
        print(f"  {key}: {value}")
    
    print("\n[PASSED] Confidence scoring tests")


def test_suppression_rules():
    """Test FK suppression rules."""
    print("\n" + "=" * 80)
    print("TEST: FK Suppression Rules")
    print("=" * 80)
    
    # Temporal column should be suppressed
    fk_profile = {"physical_type": "TIMESTAMP", "distinct_count": 1000}
    pk_profile = {"physical_type": "TIMESTAMP", "distinct_count": 1000}
    
    result = should_suppress_fk("created_at", fk_profile, "created_at", pk_profile)
    assert result.should_suppress
    print(f"[OK] Temporal column suppressed: {result.reasons}")
    
    # Boolean column should be suppressed
    fk_profile = {"physical_type": "BOOLEAN", "distinct_count": 2}
    pk_profile = {"physical_type": "BOOLEAN", "distinct_count": 2}
    
    result = should_suppress_fk("is_active", fk_profile, "is_active", pk_profile)
    assert result.should_suppress
    print(f"[OK] Boolean column suppressed: {result.reasons}")
    
    # Valid FK column should not be suppressed
    fk_profile = {"physical_type": "INTEGER", "distinct_count": 500}
    pk_profile = {"physical_type": "INTEGER", "distinct_count": 500}
    
    result = should_suppress_fk("customer_id", fk_profile, "customer_id", pk_profile)
    assert not result.should_suppress
    print(f"[OK] Valid FK column not suppressed")
    
    print("\n[PASSED] Suppression rules tests")


def test_end_to_end_relationship_detection():
    """Test full relationship detection pipeline."""
    print("\n" + "=" * 80)
    print("TEST: End-to-End Relationship Detection")
    print("=" * 80)
    
    # Mock table profiles with realistic data
    table_profiles = {
        "sales_orders": {
            "columns": [
                {"column_name": "orderid", "physical_type": "INTEGER", "distinct_count": 1000, "null_count": 0, "row_count": 1000},
                {"column_name": "customerid", "physical_type": "INTEGER", "distinct_count": 500, "null_count": 0, "row_count": 1000},
                {"column_name": "created_at", "physical_type": "TIMESTAMP", "distinct_count": 1000, "null_count": 0, "row_count": 1000},
            ]
        },
        "sales_customers": {
            "columns": [
                {"column_name": "customerid", "physical_type": "INTEGER", "distinct_count": 500, "null_count": 0, "row_count": 500},
                {"column_name": "name", "physical_type": "STRING", "distinct_count": 500, "null_count": 0, "row_count": 500},
            ]
        },
    }
    
    # PK candidates
    pk_candidates = {
        "sales_orders": [
            {"column": "orderid", "confidence": 0.95, "accepted": True, "physical_type": "INTEGER", "distinct_count": 1000}
        ],
        "sales_customers": [
            {"column": "customerid", "confidence": 0.95, "accepted": True, "physical_type": "INTEGER", "distinct_count": 500}
        ],
    }
    
    # Canonical tables with sample values
    canonical_tables = {
        "sales_orders": {
            "columns": [
                {"normalized_name": "orderid", "sample_values": list(range(1, 101))},
                {"normalized_name": "customerid", "sample_values": [1, 2, 3, 4, 5] * 20},  # FKs referencing customers
                {"normalized_name": "created_at", "sample_values": ["2024-01-01"] * 100},
            ]
        },
        "sales_customers": {
            "columns": [
                {"normalized_name": "customerid", "sample_values": list(range(1, 51))},  # PKs 1-50
                {"normalized_name": "name", "sample_values": [f"Customer {i}" for i in range(1, 51)]},
            ]
        },
    }
    
    # Run detection
    engine = RelationshipEngine(acceptance_threshold=0.75)
    report = engine.detect_relationships(
        table_profiles=table_profiles,
        pk_candidates=pk_candidates,
        canonical_tables=canonical_tables,
    )
    
    print(f"\nDetection Summary:")
    print(f"  Total relationships detected: {report.total_relationships_detected}")
    print(f"  Accepted: {report.total_relationships_accepted}")
    print(f"  Rejected: {report.total_relationships_rejected}")
    print(f"  Tables analyzed: {report.total_tables_analyzed}")
    print(f"  Candidate pairs evaluated: {report.total_candidate_pairs_evaluated}")
    print(f"  Execution time: {report.execution_time_seconds:.3f}s")
    
    # Validate results
    print(f"\nDetected Relationships:")
    for rel in report.relationships:
        if rel.accepted:
            print(f"  [ACCEPTED] {rel.from_column.table}.{rel.from_column.column} -> {rel.to_column.table}.{rel.to_column.column}")
            print(f"    Confidence: {rel.confidence:.4f}")
            print(f"    Containment: {rel.evidence.containment_ratio:.4f}")
            print(f"    Orphans: {rel.validation.orphan_count}")
    
    # Expect to find at least 1 FK relationship
    assert report.total_relationships_accepted >= 1, "No FK relationships accepted!"
    print(f"\n[OK] {report.total_relationships_accepted} FK relationship(s) detected")
    
    # Save report
    output_path = "f:/agentic_profiler/new/output/test_relationship_report.json"
    save_relationship_report(report, output_path)
    print(f"[OK] Report saved to: {output_path}")
    
    print("\n[PASSED] End-to-end relationship detection tests")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("RELATIONSHIP DETECTION LAYER - COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    
    try:
        test_type_compatibility()
        test_candidate_pair_generation()
        test_bloom_filter()
        test_containment_validation()
        test_confidence_scoring()
        test_suppression_rules()
        test_end_to_end_relationship_detection()
        
        print("\n" + "=" * 80)
        print("[ALL TESTS PASSED]")
        print("=" * 80)
        print("\nThe FK Relationship Detection Layer is production-ready!")
        
    except AssertionError as e:
        print(f"\n[TEST FAILED] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
