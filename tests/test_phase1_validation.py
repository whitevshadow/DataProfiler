"""Phase 1 validation tests for relationship ownership fix.

Tests to verify:
1. Relationship detection works independently (without enrichment)
2. Enrichment only adds descriptions (no relationships)
3. Intent router routes correctly
4. Session state persists
5. UI counters are accurate
"""

import json
from pathlib import Path


def test_relationship_ownership():
    """Test that relationships are created by detect_relationships, not enrichment."""
    print("TEST 1: Relationship Ownership")
    print("=" * 60)
    
    # Check that enrich_descriptions exists as separate function
    from profiler import services
    
    assert hasattr(services, "enrich_descriptions"), "enrich_descriptions function must exist"
    assert hasattr(services, "detect_relationships"), "detect_relationships function must exist"
    assert hasattr(services, "enrich_relationships"), "enrich_relationships kept for compatibility"
    
    print("✓ All three functions exist: enrich_descriptions, detect_relationships, enrich_relationships")
    
    # Verify enrich_descriptions doesn't create relationships
    import inspect
    enrich_desc_source = inspect.getsource(services.enrich_descriptions)
    assert "_stage4" not in enrich_desc_source, "enrich_descriptions must NOT call stage 4"
    assert "_stage3" in enrich_desc_source, "enrich_descriptions must call stage 3"
    
    print("✓ enrich_descriptions only calls stage 3 (descriptions)")
    print("✓ enrich_descriptions does NOT call stage 4 (relationships)")
    
    # Verify detect_relationships creates relationships
    detect_rel_source = inspect.getsource(services.detect_relationships)
    assert "_stage4" in detect_rel_source, "detect_relationships must call stage 4"
    
    print("✓ detect_relationships calls stage 4 (relationships)")
    print()


def test_intent_router():
    """Test that intent router routes queries correctly."""
    print("TEST 2: Intent Router")
    print("=" * 60)
    
    from core.intent_router import IntentRouter, Intent
    
    router = IntentRouter()
    
    # Test profile intents
    match = router.classify_intent("show me the profiles")
    assert match.intent == Intent.GET_PROFILE, f"Expected GET_PROFILE, got {match.intent}"
    print(f"✓ 'show me the profiles' → {match.intent} (confidence: {match.confidence:.2f})")
    
    # Test relationship intents
    match = router.classify_intent("show relationships")
    assert match.intent == Intent.GET_RELATIONSHIPS, f"Expected GET_RELATIONSHIPS, got {match.intent}"
    print(f"✓ 'show relationships' → {match.intent} (confidence: {match.confidence:.2f})")
    
    # Test PK intents
    match = router.classify_intent("show primary keys")
    assert match.intent == Intent.GET_PK, f"Expected GET_PK, got {match.intent}"
    print(f"✓ 'show primary keys' → {match.intent} (confidence: {match.confidence:.2f})")
    
    # Test enrichment intents
    match = router.classify_intent("enrich the data")
    assert match.intent == Intent.ENRICH_DESCRIPTIONS, f"Expected ENRICH_DESCRIPTIONS, got {match.intent}"
    print(f"✓ 'enrich the data' → {match.intent} (confidence: {match.confidence:.2f})")
    
    # Test detection intent
    match = router.classify_intent("detect relationships")
    assert match.intent == Intent.DETECT_RELATIONSHIPS, f"Expected DETECT_RELATIONSHIPS, got {match.intent}"
    print(f"✓ 'detect relationships' → {match.intent} (confidence: {match.confidence:.2f})")
    
    print()


def test_session_state():
    """Test that session state persists correctly."""
    print("TEST 3: Session State")
    print("=" * 60)
    
    from session.session_state import SessionState, SessionStateManager
    
    # Create a test session
    manager = SessionStateManager(Path("output/session/test_session_state.json"))
    
    # Clear any existing state
    manager.clear()
    
    # Create new session
    session = manager.load_or_create()
    assert session.tables == 0, "New session should have 0 tables"
    print("✓ Created new session with zero metrics")
    
    # Mark profile complete
    session.mark_profile_complete("/path/to/profiles", tables=31, rows=12000, columns=367)
    manager.save()
    print("✓ Marked profile complete (31 tables, 12000 rows, 367 columns)")
    
    # Load session again to verify persistence
    manager2 = SessionStateManager(Path("output/session/test_session_state.json"))
    loaded_session = manager2.load_or_create()
    
    assert loaded_session.tables == 31, f"Expected 31 tables, got {loaded_session.tables}"
    assert loaded_session.rows == 12000, f"Expected 12000 rows, got {loaded_session.rows}"
    assert loaded_session.columns == 367, f"Expected 367 columns, got {loaded_session.columns}"
    assert loaded_session.profile_complete is True, "Profile should be marked complete"
    
    print("✓ Session state persisted correctly")
    print("✓ Loaded session has correct metrics")
    
    # Clean up
    manager.clear()
    print()


def test_ui_state():
    """Test that UI state is emitted correctly."""
    print("TEST 4: UI State Builder")
    print("=" * 60)
    
    from ui.ui_state_builder import UIStateBuilder, UIState
    
    # Create test UI state
    builder = UIStateBuilder(Path("output/ui/test_ui_state.json"))
    builder.clear()
    
    # Emit profile complete
    builder.emit_profile_complete(tables=31, rows=12000, columns=367)
    print("✓ Emitted PROFILE_COMPLETE event")
    
    # Check state was saved
    assert Path("output/ui/test_ui_state.json").exists(), "UI state file should exist"
    
    # Load and verify
    ui_data = json.loads(Path("output/ui/test_ui_state.json").read_text())
    assert ui_data["tables"] == 31, f"Expected 31 tables, got {ui_data['tables']}"
    assert ui_data["rows"] == 12000, f"Expected 12000 rows, got {ui_data['rows']}"
    assert ui_data["columns"] == 367, f"Expected 367 columns, got {ui_data['columns']}"
    assert ui_data["profile_complete"] is True, "Profile should be marked complete"
    
    print("✓ UI state JSON written correctly")
    print("✓ Counters are accurate (31 tables, 12000 rows, 367 columns)")
    
    # Emit relationship complete
    builder.emit_relationship_complete(fk_count=95)
    print("✓ Emitted RELATIONSHIP_COMPLETE event")
    
    # Verify FK count
    ui_data = json.loads(Path("output/ui/test_ui_state.json").read_text())
    assert ui_data["fk_count"] == 95, f"Expected 95 FK, got {ui_data['fk_count']}"
    print("✓ FK count updated (95)")
    
    # Clean up
    builder.clear()
    print()


def test_join_recommender():
    """Test that join recommender only uses TRUE_FK relationships."""
    print("TEST 5: Join Recommender (TRUE_FK Only)")
    print("=" * 60)
    
    from joins.join_recommender import JoinRecommender, reject_semantic_joins
    
    # Create test relationships
    test_relationships = [
        {
            "source_table": "sales_orders",
            "source_column": "customerid",
            "target_table": "sales_customers",
            "target_column": "customerid",
            "relationship_class": "TRUE_FK",
            "confidence": 0.96,
            "containment_ratio": 0.98
        },
        {
            "source_table": "application_cities",
            "source_column": "cityname",
            "target_table": "application_countries",
            "target_column": "countryname",
            "relationship_class": "SEMANTICALLY_RELATED",
            "confidence": 0.85,
            "containment_ratio": 0.45
        },
        {
            "source_table": "warehouse_stockitems",
            "source_column": "supplierid",
            "target_table": "purchasing_suppliers",
            "target_column": "supplierid",
            "relationship_class": "TRUE_FK",
            "confidence": 0.99,
            "containment_ratio": 1.0
        },
    ]
    
    # Test semantic rejection
    true_fk_only = reject_semantic_joins(test_relationships)
    assert len(true_fk_only) == 2, f"Expected 2 TRUE_FK, got {len(true_fk_only)}"
    print(f"✓ Rejected semantic relationships: {len(test_relationships)} → {len(true_fk_only)}")
    
    for rel in true_fk_only:
        assert rel["relationship_class"] == "TRUE_FK", "All should be TRUE_FK"
        assert rel["containment_ratio"] >= 0.9, "All should have high containment"
    
    print("✓ All retained relationships are TRUE_FK with high containment")
    print("✓ Semantic text matches (city→country) were REJECTED")
    print()


def run_all_tests():
    """Run all Phase 1 validation tests."""
    print()
    print("=" * 60)
    print("PHASE 1 VALIDATION TESTS")
    print("=" * 60)
    print()
    
    try:
        test_relationship_ownership()
        test_intent_router()
        test_session_state()
        test_ui_state()
        test_join_recommender()
        
        print("=" * 60)
        print("✅ ALL PHASE 1 TESTS PASSED!")
        print("=" * 60)
        print()
        print("Summary of fixes:")
        print("1. ✓ Relationship detection separated from enrichment")
        print("2. ✓ Intent router routes queries correctly")
        print("3. ✓ Session state persists pipeline metrics")
        print("4. ✓ UI counters show accurate values")
        print("5. ✓ Join recommender only uses TRUE_FK relationships")
        print()
        return True
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        return False
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ ERROR: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
