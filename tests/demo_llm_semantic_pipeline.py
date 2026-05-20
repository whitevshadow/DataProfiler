"""
End-to-End Semantic Relationship Detection Pipeline

Pipeline Flow:
    1. Load profile.json (column statistics from profiling engine)
    2. Generate LLM descriptions using NVIDIA API → descriptions.json
    3. Load descriptions.json
    4. Generate embeddings and perform ANN retrieval
    5. Apply DBSCAN clustering for semantic grouping
    6. Validate candidates with deterministic containment
    7. Score and adjudicate relationships
    8. Save to relationships.json

Usage:
    python demo_llm_semantic_pipeline.py

Environment:
    NVIDIA_API_KEY must be set in environment or .env file
"""

import os
import sys
import json
import time
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from relationships.llm_description_generator import (
    NVIDIADescriptionGenerator,
    LLMColumnDescription,
    save_descriptions_to_json,
    load_descriptions_from_json,
)
from relationships.semantic_embedding_engine import (
    SemanticEmbeddingEngine,
    ANNCandidateRetriever,
)
from relationships.semantic_clustering import (
    SemanticClusteringEngine,
    SemanticRelationshipAdjudicator,
    RelationshipClass,
)
from relationships.containment_validator import ContainmentValidator
from relationships.confidence_engine import ConfidenceEngine
from relationships.type_compatibility import check_type_compatibility


class LLMSemanticPipeline:
    """
    Complete pipeline for LLM-powered semantic relationship detection.
    """
    
    def __init__(
        self,
        nvidia_api_keys: Optional[List[str]] = None,
        min_semantic_similarity: float = 0.30,
        use_clustering: bool = True,
        max_workers: int = 10,
    ):
        """
        Initialize pipeline.
        
        Args:
            nvidia_api_keys: List of NVIDIA API keys (uses env vars if None)
            min_semantic_similarity: Min cosine similarity for candidates
            use_clustering: Whether to use DBSCAN clustering
            max_workers: Max parallel workers for LLM generation
        """
        self.llm_generator = NVIDIADescriptionGenerator(
            api_keys=nvidia_api_keys,
            max_workers=max_workers
        )
        self.embedding_engine = SemanticEmbeddingEngine()
        self.ann_retriever = ANNCandidateRetriever(min_similarity=min_semantic_similarity)
        self.clustering_engine = SemanticClusteringEngine() if use_clustering else None
        self.containment_validator = ContainmentValidator()
        self.confidence_engine = ConfidenceEngine(use_semantic_signals=True)
        self.adjudicator = SemanticRelationshipAdjudicator()
        
        self.use_clustering = use_clustering
    
    def run_full_pipeline(
        self,
        profile_json_path: str,
        canonical_json_path: Optional[str] = None,
        output_dir: str = "output",
        descriptions_output: Optional[str] = None,
        relationships_output: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run complete pipeline: profiles → descriptions → relationships.
        
        Args:
            profile_json_path: Path to profile JSON files (directory)
            canonical_json_path: Path to canonical JSON files (optional, for sample values)
            output_dir: Output directory for artifacts
            descriptions_output: Custom path for descriptions.json
            relationships_output: Custom path for relationships.json
        
        Returns:
            Pipeline results summary
        """
        print("\n" + "=" * 80)
        print("LLM-POWERED SEMANTIC RELATIONSHIP DETECTION PIPELINE")
        print("=" * 80)
        
        pipeline_start = time.time()
        
        # Set default output paths
        if not descriptions_output:
            descriptions_output = os.path.join(output_dir, "descriptions", "descriptions.json")
        if not relationships_output:
            relationships_output = os.path.join(output_dir, "relationships", "relationships.json")
        
        # STAGE 1: Load profiles
        print("\n[STAGE 1] Loading table profiles...")
        table_profiles = self._load_profiles(profile_json_path)
        pk_candidates = self._extract_pk_candidates(table_profiles)
        print(f"Loaded {len(table_profiles)} tables")
        
        # STAGE 2: Generate LLM descriptions
        print("\n[STAGE 2] Generating LLM-powered semantic descriptions...")
        
        if os.path.exists(descriptions_output):
            print(f"Found existing descriptions at {descriptions_output}")
            user_input = input("Regenerate descriptions? (y/N): ").strip().lower()
            if user_input == 'y':
                descriptions = self._generate_llm_descriptions(
                    table_profiles, pk_candidates, descriptions_output
                )
            else:
                print("Loading existing descriptions...")
                descriptions = load_descriptions_from_json(descriptions_output)
        else:
            descriptions = self._generate_llm_descriptions(
                table_profiles, pk_candidates, descriptions_output
            )
        
        # Flatten descriptions for embedding
        all_descriptions = []
        for table_descs in descriptions.values():
            all_descriptions.extend(table_descs)
        
        # STAGE 3: Generate embeddings and ANN candidates
        print("\n[STAGE 3] Generating embeddings and retrieving ANN candidates...")
        embeddings = self.embedding_engine.fit_and_transform(all_descriptions)
        print(f"Generated {len(embeddings)} embeddings with {embeddings.shape[1]} dimensions")
        
        # Separate FK and PK descriptions
        pk_candidate_set = set()
        for table, pks in pk_candidates.items():
            for pk in pks:
                pk_candidate_set.add((table, pk["column"]))
        
        fk_descriptions = [d for d in all_descriptions if (d.table_name, d.column_name) not in pk_candidate_set]
        pk_descriptions = [d for d in all_descriptions if (d.table_name, d.column_name) in pk_candidate_set]
        
        fk_embeddings = self.embedding_engine.transform(fk_descriptions)
        pk_embeddings = self.embedding_engine.transform(pk_descriptions)
        
        semantic_candidates = self.ann_retriever.retrieve_candidates(
            fk_descriptions, pk_descriptions,
            fk_embeddings, pk_embeddings,
        )
        print(f"Retrieved {len(semantic_candidates)} semantic candidates via ANN")
        
        # STAGE 4: Semantic clustering (optional)
        clusters = {}
        if self.use_clustering and len(all_descriptions) > 2:
            print("\n[STAGE 4] Clustering columns by semantic similarity...")
            clusters = self.clustering_engine.cluster_columns(all_descriptions, embeddings)
            print(f"Found {len(clusters)} semantic clusters:")
            for cluster_id, cluster in clusters.items():
                print(f"  Cluster {cluster_id}: {cluster.cluster_label} ({len(cluster.columns)} columns)")
        else:
            print("\n[STAGE 4] Clustering disabled")
        
        # STAGE 5: Load canonical tables for containment validation
        print("\n[STAGE 5] Loading canonical tables for validation...")
        canonical_tables = {}
        if canonical_json_path and os.path.exists(canonical_json_path):
            canonical_tables = self._load_canonical_tables(canonical_json_path)
            print(f"Loaded {len(canonical_tables)} canonical tables with sample values")
        else:
            print("No canonical tables provided - validation will be limited")
        
        # STAGE 6: Validate and adjudicate relationships
        print("\n[STAGE 6] Validating candidates and adjudicating relationships...")
        adjudicated_relationships = self._validate_and_adjudicate(
            semantic_candidates,
            all_descriptions,
            canonical_tables,
            pk_candidates,
            clusters,
        )
        print(f"Validated {len(adjudicated_relationships)} relationships")
        
        # STAGE 7: Save relationships to JSON
        print("\n[STAGE 7] Saving relationships...")
        relationships_path = os.path.join(output_dir, "relationships.json")
        self._save_relationships(adjudicated_relationships, relationships_output)
        
        # Pipeline summary
        pipeline_time = time.time() - pipeline_start
        
        summary = {
            "total_tables": len(table_profiles),
            "total_columns": len(all_descriptions),
            "total_candidates": len(semantic_candidates),
            "total_relationships": len(adjudicated_relationships),
            "true_fk_count": sum(1 for r in adjudicated_relationships if r.relationship_class == RelationshipClass.TRUE_FK),
            "semantically_related_count": sum(1 for r in adjudicated_relationships if r.relationship_class == RelationshipClass.SEMANTICALLY_RELATED),
            "possible_reference_count": sum(1 for r in adjudicated_relationships if r.relationship_class == RelationshipClass.POSSIBLE_REFERENCE),
            "false_positive_count": sum(1 for r in adjudicated_relationships if r.relationship_class == RelationshipClass.FALSE_POSITIVE),
            "clusters_found": len(clusters),
            "pipeline_time_seconds": pipeline_time,
            "output_files": {
                "descriptions": descriptions_output,
                "relationships": relationships_output,
            },
        }
        
        print("\n" + "=" * 80)
        print("PIPELINE COMPLETE")
        print("=" * 80)
        print(f"  Total Relationships: {summary['total_relationships']}")
        print(f"    TRUE_FK: {summary['true_fk_count']}")
        print(f"    SEMANTICALLY_RELATED: {summary['semantically_related_count']}")
        print(f"    POSSIBLE_REFERENCE: {summary['possible_reference_count']}")
        print(f"    FALSE_POSITIVE: {summary['false_positive_count']}")
        print(f"  Semantic Clusters: {summary['clusters_found']}")
        print(f"  Pipeline Time: {summary['pipeline_time_seconds']:.2f}s")
        print("\nOutput Files:")
        print(f"  Canonical: {PROFILE_PATH}/*.canonical.json")
        print(f"  Descriptions: {summary['output_files']['descriptions']}")
        print(f"  Relationships: {summary['output_files']['relationships']}")
        print("=" * 80)
        
        return summary
    
    def _load_profiles(self, profile_path: str) -> Dict[str, Dict[str, Any]]:
        """Load profile JSON files from directory or single file."""
        table_profiles = {}
        
        if os.path.isdir(profile_path):
            import glob
            json_files = glob.glob(os.path.join(profile_path, "*.json"))
            for json_file in json_files:
                with open(json_file, 'r', encoding='utf-8') as f:
                    canonical = json.load(f)
                    table_name = canonical.get("table_name") or Path(json_file).stem.replace(".canonical", "")
                    
                    # Convert canonical format to profile format
                    profile = self._canonical_to_profile(canonical)
                    table_profiles[table_name] = profile
        else:
            with open(profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and "tables" in data:
                    table_profiles = data["tables"]
                else:
                    table_profiles = data
        
        return table_profiles
    
    def _canonical_to_profile(self, canonical: Dict[str, Any]) -> Dict[str, Any]:
        """Convert canonical JSON to profile format expected by LLM generator."""
        profile = {
            "table_name": canonical.get("table_name"),
            "columns": []
        }
        
        for col in canonical.get("columns", []):
            # Estimate statistics from sample values
            sample_values = col.get("sample_values", [])
            non_null_values = [v for v in sample_values if v is not None and v != ""]
            
            distinct_values = len(set(str(v) for v in non_null_values))
            row_count = len(sample_values)
            null_count = row_count - len(non_null_values)
            
            col_profile = {
                "column_name": col.get("normalized_name", col.get("original_name")),
                "original_name": col.get("original_name"),
                "physical_type": col.get("physical_type", "UNKNOWN"),
                "distinct_count": distinct_values,
                "null_count": null_count,
                "row_count": row_count,
                "sample_values": non_null_values[:10],  # First 10 non-null values
            }
            profile["columns"].append(col_profile)
        
        return profile
    
    def _extract_pk_candidates(
        self,
        table_profiles: Dict[str, Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Extract PK candidates from profiles."""
        pk_candidates = {}
        
        for table_name, profile in table_profiles.items():
            pks = profile.get("pk_candidates", [])
            if pks:
                pk_candidates[table_name] = pks
            else:
                # Fallback: look for columns with high uniqueness
                high_unique_cols = []
                for col in profile.get("columns", []):
                    row_count = col.get("row_count", 0)
                    distinct_count = col.get("distinct_count", 0)
                    uniqueness = distinct_count / row_count if row_count > 0 else 0
                    if uniqueness >= 0.95:
                        high_unique_cols.append({
                            "column": col["column_name"],
                            "confidence": 0.85,
                            "accepted": True,
                        })
                if high_unique_cols:
                    pk_candidates[table_name] = high_unique_cols
        
        return pk_candidates
    
    def _generate_llm_descriptions(
        self,
        table_profiles: Dict[str, Dict[str, Any]],
        pk_candidates: Dict[str, List[Dict[str, Any]]],
        output_path: str,
    ) -> Dict[str, List[LLMColumnDescription]]:
        """Generate LLM descriptions and save to JSON."""
        descriptions = self.llm_generator.generate_descriptions_for_tables(
            table_profiles, pk_candidates
        )
        save_descriptions_to_json(descriptions, output_path)
        return descriptions
    
    def _load_canonical_tables(self, canonical_path: str) -> Dict[str, Dict[str, Any]]:
        """Load canonical tables from JSON."""
        canonical_tables = {}
        
        if os.path.isdir(canonical_path):
            import glob
            json_files = glob.glob(os.path.join(canonical_path, "*.json"))
            for json_file in json_files:
                with open(json_file, 'r', encoding='utf-8') as f:
                    canonical = json.load(f)
                    table_name = canonical.get("table_name") or Path(json_file).stem
                    canonical_tables[table_name] = canonical
        else:
            with open(canonical_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                canonical_tables = data if isinstance(data, dict) else {}
        
        return canonical_tables
    
    def _validate_and_adjudicate(
        self,
        semantic_candidates: List[Any],
        all_descriptions: List[LLMColumnDescription],
        canonical_tables: Dict[str, Dict[str, Any]],
        pk_candidates: Dict[str, List[Dict[str, Any]]],
        clusters: Dict[int, Any],
    ) -> List[Any]:
        """Validate semantic candidates and adjudicate."""
        adjudicated = []
        
        for candidate in semantic_candidates:
            # Get descriptions
            fk_desc = next((d for d in all_descriptions if d.table_name == candidate.fk_table and d.column_name == candidate.fk_column), None)
            pk_desc = next((d for d in all_descriptions if d.table_name == candidate.pk_table and d.column_name == candidate.pk_column), None)
            
            if not fk_desc or not pk_desc:
                continue
            
            # Get sample values for containment
            fk_values = self._get_sample_values(candidate.fk_table, candidate.fk_column, canonical_tables)
            pk_values = self._get_sample_values(candidate.pk_table, candidate.pk_column, canonical_tables)
            
            if not fk_values or not pk_values:
                # Skip if no sample values
                continue
            
            # Validate containment (AUTHORITATIVE)
            containment = self.containment_validator.validate_containment_full(fk_values, pk_values)
            
            # Type compatibility
            type_result = check_type_compatibility(fk_desc.column_name, pk_desc.column_name)
            
            # PK confidence
            pk_confidence = 0.95
            for pk in pk_candidates.get(candidate.pk_table, []):
                if pk["column"] == candidate.pk_column:
                    pk_confidence = pk.get("confidence", 0.95)
                    break
            
            # Compute confidence with semantic signal
            confidence = self.confidence_engine.compute_confidence(
                containment_ratio=containment.containment_ratio,
                overlap_ratio=containment.containment_ratio,
                type_compatibility_score=type_result.compatibility_score,
                pk_confidence=pk_confidence,
                naming_similarity=0.5,
                semantic_similarity=candidate.semantic_similarity,
            )
            
            # Adjudicate
            from relationships.semantic_column_descriptor import ColumnDescription
            
            # Convert LLMColumnDescription to ColumnDescription for adjudicator
            fk_cd = ColumnDescription(
                column_name=fk_desc.column_name,
                table_name=fk_desc.table_name,
                semantic_role=fk_desc.semantic_role,
                business_meaning=fk_desc.business_meaning,
                identifier_type=fk_desc.identifier_type,
                entity_reference=fk_desc.entity_reference,
                relationship_hints=fk_desc.relationship_hints,
            )
            pk_cd = ColumnDescription(
                column_name=pk_desc.column_name,
                table_name=pk_desc.table_name,
                semantic_role=pk_desc.semantic_role,
                business_meaning=pk_desc.business_meaning,
                identifier_type=pk_desc.identifier_type,
                entity_reference=pk_desc.entity_reference,
                relationship_hints=pk_desc.relationship_hints,
            )
            
            adjudicated_rel = self.adjudicator.adjudicate(
                fk_table=candidate.fk_table,
                fk_column=candidate.fk_column,
                pk_table=candidate.pk_table,
                pk_column=candidate.pk_column,
                semantic_similarity=candidate.semantic_similarity,
                containment_ratio=containment.containment_ratio,
                type_compatibility=type_result.compatibility_score,
                confidence=confidence,
                fk_description=fk_cd,
                pk_description=pk_cd,
            )
            
            adjudicated.append(adjudicated_rel)
        
        return adjudicated
    
    def _get_sample_values(
        self,
        table: str,
        column: str,
        canonical_tables: Dict[str, Dict[str, Any]],
    ) -> Optional[List[Any]]:
        """Extract sample values for a column."""
        if table not in canonical_tables:
            return None
        
        canonical = canonical_tables[table]
        for col in canonical.get("columns", []):
            if col.get("normalized_name") == column or col.get("original_name") == column:
                return col.get("sample_values", [])
        
        return None
    
    def _save_relationships(self, relationships: List[Any], output_path: str) -> None:
        """Save adjudicated relationships to JSON."""
        output = {
            "schema_version": "v1.0.0_semantic",
            "artifact_type": "SemanticRelationships",
            "relationships": []
        }
        
        for rel in relationships:
            output["relationships"].append({
                "fk_table": rel.fk_table,
                "fk_column": rel.fk_column,
                "pk_table": rel.pk_table,
                "pk_column": rel.pk_column,
                "relationship_class": rel.relationship_class.value,
                "confidence": rel.confidence,
                "semantic_similarity": rel.semantic_similarity,
                "containment_ratio": rel.containment_ratio,
                "type_compatibility": rel.type_compatibility,
                "adjudication_reasoning": rel.adjudication_reasoning,
                "semantic_cluster_id": rel.semantic_cluster_id,
                "suppression_warnings": rel.suppression_warnings,
            })
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"  Saved to: {output_path}")


if __name__ == "__main__":
    print("\nLLM-Powered Semantic Relationship Detection Pipeline")
    print("This pipeline uses NVIDIA's seed-oss-36b-instruct to generate rich column descriptions")
    print("and combines semantic similarity with deterministic validation.\n")
    
    # Configuration - Separate directories for each artifact type
    CANONICAL_PATH = "output/canonical"      # Canonical table representations
    PROFILE_PATH = "output/profiles"         # NOT USED - we load from canonical
    DESCRIPTIONS_PATH = "output/descriptions"  # LLM-generated descriptions
    RELATIONSHIPS_PATH = "output/relationships"  # FK relationships
    OUTPUT_DIR = "output"
    
    # Use canonical files as input (they're already generated)
    if not os.path.exists(PROFILE_PATH):
        print(f"[INFO] Using canonical files from: {PROFILE_PATH}")
        print(f"       (Files named *.canonical.json contain all needed data)")
    
    if not os.path.exists(PROFILE_PATH):
        print(f"[ERROR] No profile/canonical files found in: {PROFILE_PATH}")
        print("Please run the profiling engine first to generate profiles.")
        sys.exit(1)
    
    # Initialize pipeline
    try:
        pipeline = LLMSemanticPipeline(
            min_semantic_similarity=0.30,
            use_clustering=True,
            max_workers=15,  # Parallel processing with 15 workers
        )
        
        # Run pipeline with organized output paths
        summary = pipeline.run_full_pipeline(
            profile_json_path=PROFILE_PATH,  # Load from canonical files
            canonical_json_path=PROFILE_PATH,  # Same location for sample values
            output_dir=OUTPUT_DIR,
            descriptions_output=os.path.join(DESCRIPTIONS_PATH, "descriptions.json"),
            relationships_output=os.path.join(RELATIONSHIPS_PATH, "relationships.json"),
        )
        
        print("\n✓ Pipeline completed successfully!")
        
    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
