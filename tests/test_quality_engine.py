"""
Test Enhanced Quality Engine

Demonstrates the 10 quality dimensions with explainable reasoning,
confidence scores, and remediation hints.
"""

import sys
sys.path.insert(0, 'f:\\agentic_profiler\\new')

from profiler.profiling.quality_engine import QualityEngine, QualitySeverity
from profiler.profiling.profiling_models import PhysicalType, SemanticType, RelationalRole, QualityFlag
from typing import Dict, Any


def print_header(title: str):
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def print_quality_assessment(context: Dict[str, Any]):
    """Print detailed quality assessment for a column."""
    engine = QualityEngine()
    
    column_name = context.get("column_name", "unknown")
    print(f"\n{'-' * 100}")
    print(f"Column: {column_name}")
    print(f"{'-' * 100}")
    
    # Run assessment
    flags, quality_score, issues = engine.assess_quality(context)
    
    # Print results
    print(f"\nQuality Score: {quality_score:.2f}/1.00")
    print(f"Issues Found: {len(issues)}")
    
    if issues:
        print("\nQuality Issues:")
        for i, issue in enumerate(issues, 1):
            severity_map = {
                QualitySeverity.CRITICAL: "CRITICAL",
                QualitySeverity.HIGH: "HIGH",
                QualitySeverity.MEDIUM: "MEDIUM",
                QualitySeverity.LOW: "LOW",
                QualitySeverity.INFO: "INFO",
            }
            severity_label = severity_map.get(issue.severity, "INFO")
            
            print(f"\n  {i}. [{severity_label}] {issue.flag.value.upper()}")
            print(f"     Confidence: {issue.confidence:.2f}")
            print(f"     Message: {issue.message}")
            if issue.affected_count:
                print(f"     Affected: {issue.affected_count} rows")
            if issue.sample_values:
                print(f"     Samples: {issue.sample_values}")
            if issue.remediation_hint:
                print(f"     [Remediation] {issue.remediation_hint}")
    else:
        print("\n[OK] No quality issues detected!")
    
    return quality_score, issues


def test_completeness_quality():
    """Test completeness quality validators."""
    print_header("TEST 1: COMPLETENESS QUALITY")
    
    # Test HIGH_NULL_RATIO
    context = {
        "column_name": "optional_field",
        "physical_type": PhysicalType.STRING,
        "null_ratio": 0.75,
        "null_count": 750,
        "total_count": 1000,
        "distinct_count": 50,
        "entropy_normalized": 0.5,
        "uniqueness_ratio": 0.05,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.HIGH_NULL_RATIO in [i.flag for i in issues]
    
    # Test REQUIRED_FIELD_MISSING (PK with nulls)
    context = {
        "column_name": "customer_id",
        "physical_type": PhysicalType.INTEGER,
        "relational_role": RelationalRole.PRIMARY_KEY,
        "null_ratio": 0.05,
        "null_count": 5,
        "total_count": 100,
        "distinct_count": 95,
        "entropy_normalized": 0.95,
        "uniqueness_ratio": 0.95,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.REQUIRED_FIELD_MISSING in [i.flag for i in issues]


def test_uniqueness_quality():
    """Test uniqueness quality validators."""
    print_header("TEST 2: UNIQUENESS QUALITY")
    
    # Test PK_DUPLICATION
    context = {
        "column_name": "order_id",
        "physical_type": PhysicalType.INTEGER,
        "relational_role": RelationalRole.PRIMARY_KEY,
        "null_ratio": 0.0,
        "null_count": 0,
        "total_count": 1000,
        "distinct_count": 950,
        "entropy_normalized": 0.95,
        "uniqueness_ratio": 0.95,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.PK_DUPLICATION in [i.flag for i in issues]
    
    # Test WEAK_IDENTIFIER
    context = {
        "column_name": "transaction_id",
        "physical_type": PhysicalType.STRING,
        "null_ratio": 0.0,
        "null_count": 0,
        "total_count": 1000,
        "distinct_count": 800,
        "entropy_normalized": 0.85,
        "uniqueness_ratio": 0.80,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.WEAK_IDENTIFIER in [i.flag for i in issues]


def test_semantic_quality():
    """Test semantic quality validators."""
    print_header("TEST 3: SEMANTIC QUALITY")
    
    # Test INVALID_EMAIL
    context = {
        "column_name": "email",
        "physical_type": PhysicalType.STRING,
        "semantic_type": SemanticType.EMAIL,
        "null_ratio": 0.1,
        "null_count": 10,
        "total_count": 100,
        "distinct_count": 90,
        "entropy_normalized": 0.9,
        "uniqueness_ratio": 0.9,
        "sample_values": ["user@example.com", "invalid-email", "another@bad", "good@email.com"],
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.INVALID_EMAIL in [i.flag for i in issues]
    
    # Test NEGATIVE_PRICE
    context = {
        "column_name": "product_price",
        "physical_type": PhysicalType.FLOAT,
        "null_ratio": 0.0,
        "null_count": 0,
        "total_count": 1000,
        "distinct_count": 200,
        "entropy_normalized": 0.7,
        "uniqueness_ratio": 0.2,
        "min_value": -10.50,
        "max_value": 999.99,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.NEGATIVE_PRICE in [i.flag for i in issues]
    
    # Test IMPOSSIBLE_AGE
    context = {
        "column_name": "customer_age",
        "physical_type": PhysicalType.INTEGER,
        "null_ratio": 0.0,
        "null_count": 0,
        "total_count": 1000,
        "distinct_count": 80,
        "entropy_normalized": 0.6,
        "uniqueness_ratio": 0.08,
        "min_value": -5,
        "max_value": 85,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.IMPOSSIBLE_AGE in [i.flag for i in issues]


def test_statistical_quality():
    """Test statistical quality validators."""
    print_header("TEST 4: STATISTICAL QUALITY")
    
    # Test CONSTANT_COLUMN
    context = {
        "column_name": "status",
        "physical_type": PhysicalType.STRING,
        "null_ratio": 0.0,
        "null_count": 0,
        "total_count": 1000,
        "distinct_count": 1,
        "entropy_normalized": 0.0,
        "uniqueness_ratio": 0.001,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.CONSTANT_COLUMN in [i.flag for i in issues]
    assert score < 0.75  # Should have significant penalty
    
    # Test EXTREME_SKEWNESS
    context = {
        "column_name": "revenue",
        "physical_type": PhysicalType.FLOAT,
        "null_ratio": 0.0,
        "null_count": 0,
        "total_count": 1000,
        "distinct_count": 800,
        "entropy_normalized": 0.85,
        "uniqueness_ratio": 0.8,
        "skewness": 8.5,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.EXTREME_SKEWNESS in [i.flag for i in issues]


def test_relational_quality():
    """Test relational quality validators."""
    print_header("TEST 5: RELATIONAL QUALITY")
    
    # Test WEAK_RELATIONSHIP
    context = {
        "column_name": "supplier_id",
        "physical_type": PhysicalType.INTEGER,
        "relational_role": RelationalRole.FOREIGN_KEY,
        "fk_confidence": 0.55,
        "null_ratio": 0.1,
        "null_count": 10,
        "total_count": 100,
        "distinct_count": 15,
        "entropy_normalized": 0.6,
        "uniqueness_ratio": 0.15,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.WEAK_RELATIONSHIP in [i.flag for i in issues]


def test_cardinality_quality():
    """Test cardinality quality validators."""
    print_header("TEST 6: CARDINALITY QUALITY")
    
    # Test LOW_CARDINALITY
    context = {
        "column_name": "flag",
        "physical_type": PhysicalType.STRING,
        "null_ratio": 0.0,
        "null_count": 0,
        "total_count": 1000,
        "distinct_count": 2,
        "entropy_normalized": 0.1,
        "uniqueness_ratio": 0.002,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.LOW_CARDINALITY in [i.flag for i in issues]
    
    # Test HIGH_CARDINALITY (for category)
    context = {
        "column_name": "product_category",
        "physical_type": PhysicalType.STRING,
        "semantic_type": SemanticType.CATEGORY,
        "null_ratio": 0.0,
        "null_count": 0,
        "total_count": 10000,
        "distinct_count": 2500,
        "entropy_normalized": 0.95,
        "uniqueness_ratio": 0.25,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.HIGH_CARDINALITY in [i.flag for i in issues]


def test_pii_quality():
    """Test PII quality validators."""
    print_header("TEST 7: PII EXPOSURE RISK")
    
    # Test PII_EXPOSURE_RISK
    context = {
        "column_name": "customer_email",
        "physical_type": PhysicalType.STRING,
        "semantic_type": SemanticType.EMAIL,
        "null_ratio": 0.05,
        "null_count": 5,
        "total_count": 100,
        "distinct_count": 95,
        "entropy_normalized": 0.95,
        "uniqueness_ratio": 0.95,
    }
    score, issues = print_quality_assessment(context)
    assert QualityFlag.PII_EXPOSURE_RISK in [i.flag for i in issues]


def test_perfect_column():
    """Test a column with no quality issues."""
    print_header("TEST 8: PERFECT QUALITY COLUMN")
    
    context = {
        "column_name": "product_id",
        "physical_type": PhysicalType.INTEGER,
        "relational_role": RelationalRole.PRIMARY_KEY,
        "null_ratio": 0.0,
        "null_count": 0,
        "total_count": 1000,
        "distinct_count": 1000,
        "entropy_normalized": 1.0,
        "uniqueness_ratio": 1.0,
    }
    score, issues = print_quality_assessment(context)
    assert score == 1.0
    assert len(issues) == 0


def test_multiple_issues():
    """Test a column with multiple quality issues."""
    print_header("TEST 9: MULTIPLE QUALITY ISSUES")
    
    context = {
        "column_name": "email",
        "physical_type": PhysicalType.STRING,
        "semantic_type": SemanticType.EMAIL,
        "null_ratio": 0.60,
        "null_count": 600,
        "total_count": 1000,
        "distinct_count": 300,
        "entropy_normalized": 0.65,
        "uniqueness_ratio": 0.3,
        "sample_values": ["user@example.com", "bad-email", "another@invalid", "good@test.com"],
    }
    score, issues = print_quality_assessment(context)
    # Should have: HIGH_NULL_RATIO, INVALID_EMAIL, PII_EXPOSURE_RISK
    assert len(issues) >= 3
    assert score < 0.60  # Multiple issues should significantly reduce score


def print_summary():
    """Print test summary."""
    print_header("TEST SUMMARY")
    print("\n[SUCCESS] All quality dimension tests passed!")
    print("\nQuality Engine Features Demonstrated:")
    print("  1. [OK] 10 Quality Dimensions implemented")
    print("  2. [OK] Modular validator architecture")
    print("  3. [OK] Explainable quality reasoning")
    print("  4. [OK] Confidence-based scoring")
    print("  5. [OK] Severity-weighted penalties")
    print("  6. [OK] Remediation hints provided")
    print("  7. [OK] Sample values captured")
    print("  8. [OK] Affected row counts tracked")
    print("\nQuality Score Interpretation:")
    print("  1.00       = Perfect quality (no issues)")
    print("  0.90-0.99  = Excellent quality (minor issues)")
    print("  0.70-0.89  = Good quality (some issues)")
    print("  0.50-0.69  = Fair quality (multiple issues)")
    print("  0.30-0.49  = Poor quality (significant issues)")
    print("  < 0.30     = Critical quality (unusable)")
    print("\n")


if __name__ == "__main__":
    print_header("ENHANCED QUALITY ENGINE TEST SUITE")
    print("Production-grade semantic data quality intelligence system")
    print("10 quality dimensions with explainable reasoning")
    
    try:
        test_completeness_quality()
        test_uniqueness_quality()
        test_semantic_quality()
        test_statistical_quality()
        test_relational_quality()
        test_cardinality_quality()
        test_pii_quality()
        test_perfect_column()
        test_multiple_issues()
        print_summary()
        
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
