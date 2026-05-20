"""
Staged Pipeline Test - Validates each component independently
"""

import os
import sys
import json
from pathlib import Path

print("\n" + "=" * 80)
print("STAGED PIPELINE TEST")
print("=" * 80)

# STAGE 1: Verify profiles exist
print("\n[STAGE 1] Checking profiles...")
profile_dir = Path("output/profiles")
if not profile_dir.exists():
    print("  ❌ Profile directory not found")
    sys.exit(1)

profile_files = list(profile_dir.glob("*.json"))
print(f"  ✓ Found {len(profile_files)} profile files")

# STAGE 2: Load and validate one profile
print("\n[STAGE 2] Loading sample profile...")
sample_profile = profile_files[0]
with open(sample_profile, 'r', encoding='utf-8') as f:
    data = json.load(f)
    table_name = data.get("table_name")
    columns = data.get("columns", [])
    print(f"  ✓ Loaded {table_name} with {len(columns)} columns")
    
    # Check column structure
    if columns:
        col = columns[0]
        required_fields = ["normalized_name", "physical_type", "sample_values"]
        missing = [f for f in required_fields if f not in col]
        if missing:
            print(f"  ❌ Missing fields: {missing}")
        else:
            print(f"  ✓ Column structure valid")

# STAGE 3: Test LLM generator with ONE column
print("\n[STAGE 3] Testing LLM generator on 1 column...")
try:
    from relationships.llm_description_generator import NVIDIADescriptionGenerator
    
    # Create generator with 1 worker for testing
    generator = NVIDIADescriptionGenerator(max_workers=1)
    
    # Convert canonical to profile format
    col_profile = {
        "column_name": columns[0].get("normalized_name"),
        "physical_type": columns[0].get("physical_type"),
        "distinct_count": 10,
        "null_count": 0,
        "row_count": 100,
        "sample_values": columns[0].get("sample_values", [])[:5],
    }
    
    print(f"  Testing with: {table_name}.{col_profile['column_name']}")
    desc = generator.generate_description(
        table_name=table_name,
        column_name=col_profile["column_name"],
        column_profile=col_profile,
    )
    
    print(f"  ✓ Generated description:")
    print(f"    Role: {desc.semantic_role}")
    print(f"    Meaning: {desc.business_meaning[:60]}...")
    print(f"    Entity: {desc.entity_reference}")
    
except Exception as e:
    print(f"  ❌ LLM generator failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# STAGE 4: Test profile conversion
print("\n[STAGE 4] Testing profile conversion...")
try:
    from demo_llm_semantic_pipeline import LLMSemanticPipeline
    
    pipeline = LLMSemanticPipeline(max_workers=1)
    
    # Load 3 profiles for testing
    test_profiles = {}
    for pfile in profile_files[:3]:
        with open(pfile, 'r', encoding='utf-8') as f:
            canonical = json.load(f)
            table_name = canonical.get("table_name")
            profile = pipeline._canonical_to_profile(canonical)
            test_profiles[table_name] = profile
            print(f"  ✓ Converted {table_name}: {len(profile['columns'])} columns")
    
except Exception as e:
    print(f"  ❌ Profile conversion failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# STAGE 5: Test batch LLM generation (3 columns)
print("\n[STAGE 5] Testing batch LLM generation (3 columns)...")
try:
    # Take first table, first 3 columns
    first_table = list(test_profiles.keys())[0]
    test_profile = {first_table: {"columns": test_profiles[first_table]["columns"][:3]}}
    
    descriptions = generator.generate_descriptions_for_tables(test_profile)
    
    total_descs = sum(len(descs) for descs in descriptions.values())
    print(f"  ✓ Generated {total_descs} descriptions")
    
    for table, descs in descriptions.items():
        for desc in descs:
            print(f"    {desc.column_name}: {desc.semantic_role}")
    
except Exception as e:
    print(f"  ❌ Batch generation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# STAGE 6: Test embedding engine
print("\n[STAGE 6] Testing embedding engine...")
try:
    from relationships.semantic_embedding_engine import SemanticEmbeddingEngine
    
    # Get descriptions from stage 5
    all_descs = []
    for table_descs in descriptions.values():
        all_descs.extend(table_descs)
    
    embedding_engine = SemanticEmbeddingEngine()
    embeddings = embedding_engine.fit_and_transform(all_descs)
    
    print(f"  ✓ Generated embeddings: shape {embeddings.shape}")
    
except Exception as e:
    print(f"  ❌ Embedding generation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("✓ ALL STAGES PASSED!")
print("=" * 80)
print("\nThe pipeline components are working. Ready for full run.")
print("\nTo run full pipeline:")
print("  python demo_llm_semantic_pipeline.py")
