"""
Quick Start: LLM-Powered Semantic Relationship Detection

This script helps you get started with the LLM-powered semantic relationship
detection pipeline.

Usage:
    python quickstart_llm_pipeline.py
"""

import os
import sys
from pathlib import Path

def check_prerequisites():
    """Check if all prerequisites are met."""
    print("Checking prerequisites...")
    
    issues = []
    
    # Check API key
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        # Check .env file
        env_file = Path(".env")
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("NVIDIA_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
    
    if not api_key:
        issues.append("NVIDIA_API_KEY not found. Set it in environment or .env file.")
        issues.append("Get your key from: https://integrate.api.nvidia.com")
    else:
        print("  ✓ NVIDIA API key found")
    
    # Check for profiles
    profile_dir = Path("output/profiles")
    if not profile_dir.exists() or not list(profile_dir.glob("*.json")):
        issues.append(f"No profile files found in {profile_dir}")
        issues.append("Run profiling_agent.py first to generate profiles.")
    else:
        profile_count = len(list(profile_dir.glob("*.json")))
        print(f"  ✓ Found {profile_count} profile files")
    
    # Check for canonical tables (optional)
    canonical_dir = Path("output/canonical")
    if canonical_dir.exists() and list(canonical_dir.glob("*.json")):
        canonical_count = len(list(canonical_dir.glob("*.json")))
        print(f"  ✓ Found {canonical_count} canonical files (for containment validation)")
    else:
        print("  ⚠ No canonical files found (validation will be limited)")
        print("    Run profiling_agent.py with canonical output enabled for better results")
    
    # Check dependencies
    try:
        import openai
        print("  ✓ openai package installed")
    except ImportError:
        issues.append("openai package not installed. Run: pip install openai")
    
    try:
        import sklearn
        print("  ✓ scikit-learn package installed")
    except ImportError:
        issues.append("scikit-learn package not installed. Run: pip install scikit-learn")
    
    try:
        from dotenv import load_dotenv
        print("  ✓ python-dotenv package installed")
    except ImportError:
        issues.append("python-dotenv package not installed. Run: pip install python-dotenv")
    
    return issues


def setup_env_file():
    """Help user set up .env file."""
    print("\nLet's set up your .env file with the NVIDIA API key.")
    print("Get your key from: https://integrate.api.nvidia.com")
    
    api_key = input("\nEnter your NVIDIA API key (nvapi-...): ").strip()
    
    if not api_key.startswith("nvapi-"):
        print("  ⚠ Warning: API key should start with 'nvapi-'")
    
    with open(".env", "w") as f:
        f.write(f"NVIDIA_API_KEY={api_key}\n")
    
    print(f"  ✓ Saved to .env")


def main():
    print("\n" + "=" * 80)
    print("LLM-Powered Semantic Relationship Detection - Quick Start")
    print("=" * 80)
    
    # Check prerequisites
    issues = check_prerequisites()
    
    if issues:
        print("\n" + "!" * 80)
        print("SETUP REQUIRED")
        print("!" * 80)
        for issue in issues:
            print(f"  • {issue}")
        
        # Offer to set up .env if that's the issue
        if any("NVIDIA_API_KEY" in issue for issue in issues):
            response = input("\nWould you like to set up your NVIDIA API key now? (y/N): ").strip().lower()
            if response == 'y':
                setup_env_file()
                print("\n  ✓ .env file created!")
                print("\nPlease re-run this script to continue.")
            else:
                print("\nPlease resolve the issues above and try again.")
        else:
            print("\nPlease resolve the issues above and try again.")
        
        sys.exit(1)
    
    print("\n" + "=" * 80)
    print("All prerequisites met! Ready to run the pipeline.")
    print("=" * 80)
    
    print("\nThe pipeline will:")
    print("  1. Load table profiles from output/profiles/")
    print("  2. Generate LLM descriptions using NVIDIA API")
    print("  3. Save descriptions to output/descriptions.json")
    print("  4. Perform ANN candidate retrieval + DBSCAN clustering")
    print("  5. Validate candidates with containment")
    print("  6. Save relationships to output/relationships.json")
    
    response = input("\nRun the pipeline now? (Y/n): ").strip().lower()
    
    if response in ['', 'y', 'yes']:
        print("\n" + "=" * 80)
        print("Starting pipeline...")
        print("=" * 80)
        
        # Import and run pipeline
        try:
            from demo_llm_semantic_pipeline import LLMSemanticPipeline
            
            pipeline = LLMSemanticPipeline(
                min_semantic_similarity=0.30,
                use_clustering=True,
            )
            
            summary = pipeline.run_full_pipeline(
                profile_json_path="output/profiles",
                canonical_json_path="output/canonical" if Path("output/canonical").exists() else None,
                output_dir="output",
            )
            
            print("\n" + "=" * 80)
            print("✓ PIPELINE COMPLETED SUCCESSFULLY!")
            print("=" * 80)
            print(f"\nResults:")
            print(f"  Total Relationships: {summary['total_relationships']}")
            print(f"    TRUE_FK: {summary['true_fk_count']}")
            print(f"    SEMANTICALLY_RELATED: {summary['semantically_related_count']}")
            print(f"    POSSIBLE_REFERENCE: {summary['possible_reference_count']}")
            print(f"\nOutput Files:")
            print(f"  Descriptions: {summary['output_files']['descriptions']}")
            print(f"  Relationships: {summary['output_files']['relationships']}")
            
            print("\nNext Steps:")
            print("  • Review relationships.json for detected relationships")
            print("  • Use descriptions.json for documentation or lineage")
            print("  • Run test_semantic_relationships.py to validate the system")
            print("  • See docs/LLM_SEMANTIC_PIPELINE.md for detailed documentation")
            
        except Exception as e:
            print(f"\n[ERROR] Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        print("\nPipeline not started. To run manually:")
        print("  python demo_llm_semantic_pipeline.py")


if __name__ == "__main__":
    main()
