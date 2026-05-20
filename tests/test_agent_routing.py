"""Test agent intent routing to verify proper tool classification."""

from profiler.agent.chatbot import _classify_user_intent


def test_conversation_intents():
    """Test that conversational messages are classified correctly."""
    conversation_messages = [
        "Hello",
        "Hi there",
        "Thanks",
        "What can you do?",
        "How do you work?",
        "Explain profiling",
        "Tell me about relationships",
        "Why use this tool?",
        "Who are you?",
        "What are your capabilities?",
        "Help me understand",
    ]
    
    for msg in conversation_messages:
        intent = _classify_user_intent(msg)
        status = "✓" if intent == "conversation" else "✗"
        print(f"{status} {intent:15s} | {msg}")
    
    print()


def test_data_request_intents():
    """Test that data requests are classified correctly."""
    data_messages = [
        # Discovery
        "List files in data",
        "Show me the files",
        "Find all CSV files",
        
        # Profiling
        "Profile data/customers.csv",
        "Analyze all files",
        "Scan the directory",
        "Profile everything in data",
        
        # Relationships
        "Detect relationships",
        "Find foreign keys",
        "Enrich relationships",
        "Show me the relationships",
        
        # Quality
        "Check data quality",
        "Get quality summary",
        
        # Visualization
        "Generate ER diagram",
        "Create ERD",
        "Draw relationships",
        "Generate visualizations",
        "Make a Mermaid diagram",
        
        # LCIL
        "Enrich low cardinality columns",
        "Run LCIL enrichment",
        
        # Mixed
        "List files and profile them",
        "Analyze data/customers.csv and detect relationships",
    ]
    
    for msg in data_messages:
        intent = _classify_user_intent(msg)
        status = "✓" if intent == "data_request" else "✗"
        print(f"{status} {intent:15s} | {msg}")
    
    print()


def test_edge_cases():
    """Test edge cases to ensure proper classification."""
    edge_cases = [
        ("What is a profile?", "conversation"),          # Asking about concept
        ("Profile data", "data_request"),                # Action request
        ("How does enrichment work?", "conversation"),   # Asking how
        ("Enrich data", "data_request"),                 # Action request
        ("Tell me about ERD", "conversation"),           # Asking about
        ("Generate ERD", "data_request"),                # Action request
    ]
    
    print("EDGE CASES:")
    for msg, expected in edge_cases:
        intent = _classify_user_intent(msg)
        status = "✓" if intent == expected else "✗"
        print(f"{status} Expected: {expected:15s} | Got: {intent:15s} | {msg}")
    
    print()


if __name__ == "__main__":
    print("=" * 80)
    print("AGENT INTENT ROUTING TEST")
    print("=" * 80)
    print()
    
    print("CONVERSATIONAL MESSAGES (should be 'conversation'):")
    print("-" * 80)
    test_conversation_intents()
    
    print("DATA REQUEST MESSAGES (should be 'data_request'):")
    print("-" * 80)
    test_data_request_intents()
    
    print("EDGE CASES:")
    print("-" * 80)
    test_edge_cases()
    
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
