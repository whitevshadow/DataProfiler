"""Phase 1 V2 validation tests for new core modules.

Tests workflow manager, tool registry, agent context, and agent memory.
"""

import json
from pathlib import Path


def test_workflow_manager():
    """Test workflow orchestration."""
    print("TEST: Workflow Manager")
    print("=" * 60)
    
    from core.workflow_manager import WorkflowManager, WorkflowState
    
    manager = WorkflowManager(Path("output/workflows/test"))
    
    # Start workflow
    workflow_id = manager.start_workflow("test_pipeline")
    print(f"✓ Started workflow: {workflow_id}")
    
    # Execute stages
    stage1 = manager.start_stage("profile")
    assert stage1.state == WorkflowState.RUNNING
    manager.complete_stage(stage1, success=True, output={"tables": 31})
    assert stage1.state == WorkflowState.SUCCESS
    print("✓ Stage 1 (profile) completed successfully")
    
    stage2 = manager.start_stage("relationships")
    manager.complete_stage(stage2, success=True, output={"fk_count": 95})
    print("✓ Stage 2 (relationships) completed successfully")
    
    # Complete workflow
    execution = manager.complete_workflow()
    assert execution.success_count == 2
    assert execution.failed_count == 0
    print(f"✓ Workflow completed: {execution.success_count} stages successful")
    
    # Verify persistence
    loaded = manager.load_workflow(workflow_id)
    assert loaded is not None
    assert loaded.success_count == 2
    print("✓ Workflow persisted and loaded correctly")
    print()


def test_tool_registry():
    """Test tool registry."""
    print("TEST: Tool Registry")
    print("=" * 60)
    
    from core.tool_registry import get_tool_registry
    
    registry = get_tool_registry()
    
    # Get tool
    tool = registry.get("profile_file")
    assert tool is not None
    assert tool.category == "PROFILE"
    print(f"✓ Retrieved tool: {tool.name} ({tool.category})")
    
    # List by category
    profile_tools = registry.list_by_category("PROFILE")
    assert len(profile_tools) > 0
    print(f"✓ Found {len(profile_tools)} PROFILE tools")
    
    # Search tools
    matches = registry.search("relationship")
    assert len(matches) > 0
    print(f"✓ Search found {len(matches)} tools matching 'relationship'")
    
    # List categories
    categories = registry.get_categories()
    assert "PROFILE" in categories
    assert "RELATIONSHIP" in categories
    print(f"✓ Registry has {len(categories)} categories")
    print()


def test_agent_context():
    """Test agent context management."""
    print("TEST: Agent Context")
    print("=" * 60)
    
    from core.agent_context import ContextManager
    
    manager = ContextManager()
    context = manager.get_context()
    
    # Update selection
    context.update_selection(entity="sales_customers", node="node_123")
    assert context.current_entity == "sales_customers"
    assert context.selected_node == "node_123"
    print("✓ Selection updated correctly")
    
    # Update view
    context.update_view("er", {"zoom": 1.5})
    assert context.current_view == "er"
    assert context.view_params["zoom"] == 1.5
    print("✓ View state updated correctly")
    
    # Pending action
    context.set_pending_action({"action": "delete", "target": "table_x"})
    assert context.confirmation_required is True
    action = context.confirm_action()
    assert action["action"] == "delete"
    assert context.confirmation_required is False
    print("✓ Pending action workflow correct")
    
    # Filters
    context.add_filter("min_confidence", 0.8)
    context.add_filter("relationship_class", "TRUE_FK")
    assert len(context.active_filters) == 2
    print("✓ Filters managed correctly")
    
    # Summary
    summary = context.get_summary()
    assert summary["current_entity"] == "sales_customers"
    print("✓ Context summary generated")
    print()


def test_agent_memory():
    """Test agent memory system."""
    print("TEST: Agent Memory")
    print("=" * 60)
    
    from core.agent_memory import AgentMemory
    
    memory = AgentMemory(Path("output/memory/test"), short_term_limit=50)
    
    # Add entries
    memory.add_user_query("show profiles", intent="GET_PROFILE")
    memory.add_tool_call("list_profiles", {}, {"tables": 31})
    memory.add_agent_response("Here are your 31 tables...")
    print("✓ Added 3 memory entries")
    
    # Get recent
    recent = memory.get_recent(limit=3)
    assert len(recent) == 3
    print(f"✓ Retrieved {len(recent)} recent entries")
    
    # Get conversation context
    context = memory.get_conversation_context(turns=2)
    assert len(context) >= 2
    print(f"✓ Built conversation context with {len(context)} turns")
    
    # Learn patterns
    memory.learn_pattern("prefers_er_diagrams")
    memory.learn_pattern("prefers_er_diagrams")
    memory.learn_pattern("prefers_er_diagrams")
    frequency = memory.get_pattern_frequency("prefers_er_diagrams")
    assert frequency == 3
    print("✓ Pattern learning working (frequency: 3)")
    
    # Search
    matches = memory.search_memory("profiles")
    assert len(matches) > 0
    print(f"✓ Memory search found {len(matches)} matches")
    
    # Statistics
    stats = memory.get_statistics()
    assert stats["short_term_count"] == 3
    assert stats["learned_patterns"] == 1
    print("✓ Memory statistics generated")
    print()


def run_all_tests():
    """Run all Phase 1 V2 validation tests."""
    print()
    print("=" * 60)
    print("PHASE 1 V2 VALIDATION TESTS")
    print("=" * 60)
    print()
    
    try:
        test_workflow_manager()
        test_tool_registry()
        test_agent_context()
        test_agent_memory()
        
        print("=" * 60)
        print("✅ ALL PHASE 1 V2 TESTS PASSED!")
        print("=" * 60)
        print()
        print("New components validated:")
        print("1. ✓ Workflow Manager — orchestrates multi-stage pipelines")
        print("2. ✓ Tool Registry — central tool metadata management")
        print("3. ✓ Agent Context — tracks conversation and execution state")
        print("4. ✓ Agent Memory — learns patterns and maintains history")
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
