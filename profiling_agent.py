"""
Profiling Agent — Master Orchestrator

Single command to run the complete profiling pipeline:
    1. Generate Canonical JSON from CSV files
    2. Generate Profile JSON from Canonical JSON
    3. Generate LLM Descriptions from Profile JSON
    4. Detect Relationships using Semantic Pipeline
    5. Enrich Low-Cardinality Columns (LCIL)
    6. Generate ERD DBML schema

Usage:
    python profiling_agent.py
    
Environment:
    NVIDIA_API_KEY or NVIDIA_API_KEY_1..N must be set in .env file
"""

import sys
import json
import time
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import asdict

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-15s | %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger(__name__)


class ProfilingAgent:
    """
    Master orchestrator for the complete profiling pipeline.
    """
    
    def __init__(
        self,
        data_dir: str = "data",
        output_base: str = "output",
        sample_size: int = 100,
        max_workers: int = 15,
    ):
        """
        Initialize the profiling agent.
        
        Args:
            data_dir: Directory containing CSV files
            output_base: Base output directory
            sample_size: Number of rows to sample per file
            max_workers: Max parallel workers for LLM generation
        """
        self.data_dir = Path(data_dir)
        self.output_base = Path(output_base)
        self.sample_size = sample_size
        self.max_workers = max_workers

        # Output directories
        self.canonical_dir = self.output_base / "canonical"
        self.profiles_dir = self.output_base / "profiles"
        self.descriptions_dir = self.output_base / "descriptions"
        self.relationships_dir = self.output_base / "relationships"
        self.enrichment_dir = self.output_base / "enrichment"
        self.tree_dir = self.output_base / "tree"
        self.ui_dir = self.output_base / "ui"

        # Create directories
        for dir_path in [
            self.canonical_dir, self.profiles_dir,
            self.descriptions_dir, self.relationships_dir,
            self.enrichment_dir, self.tree_dir, self.ui_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def run_full_pipeline(self) -> Dict[str, Any]:
        """
        Run the original 5-stage pipeline from CSV to relationships.
        Kept for backward compatibility. Use run_full_pipeline_v2() for the full 9-stage chain.

        Returns:
            Summary dictionary with statistics from all stages
        """
        log.info("=" * 80)
        log.info("PROFILING AGENT — FULL PIPELINE EXECUTION")
        log.info("=" * 80)
        
        pipeline_start = time.time()
        summary = {
            "stages": {},
            "total_time_seconds": 0,
        }
        
        try:
            # Stage 1: Generate Canonical JSON
            log.info("\n[STAGE 1/6] Generating Canonical JSON from CSV files...")
            stage1_result = self._stage1_canonical_generation()
            summary["stages"]["canonical_generation"] = stage1_result
            
            # Stage 2: Generate Profile JSON
            log.info("\n[STAGE 2/6] Generating Profile JSON from Canonical JSON...")
            stage2_result = self._stage2_profile_generation()
            summary["stages"]["profile_generation"] = stage2_result
            
            # Stage 3: Generate LLM Descriptions
            log.info("\n[STAGE 3/6] Generating LLM Descriptions from Profile JSON...")
            stage3_result = self._stage3_llm_descriptions()
            summary["stages"]["llm_descriptions"] = stage3_result
            
            # Stage 4: Detect Relationships
            log.info("\n[STAGE 4/6] Detecting Relationships using Semantic Pipeline...")
            stage4_result = self._stage4_relationship_detection()
            summary["stages"]["relationship_detection"] = stage4_result
            
            # Stage 5: Low Cardinality Intelligence Layer (LCIL)
            log.info("\n[STAGE 5/6] Enriching Low Cardinality Columns with LCIL...")
            stage5_result = self._stage5_low_cardinality_enrichment()
            summary["stages"]["low_cardinality_enrichment"] = stage5_result

            # Stage 6: ERD DBML generation
            log.info("\n[STAGE 6/6] Generating ERD DBML from relationships...")
            stage6_result = self._stage6_generate_erd_dbml()
            summary["stages"]["erd_dbml_generation"] = stage6_result
            
            # Calculate total time
            summary["total_time_seconds"] = time.time() - pipeline_start
            summary["success"] = True
            
            # Print final summary
            self._print_summary(summary)
            
            return summary
            
        except Exception as e:
            log.error(f"Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            summary["success"] = False
            summary["error"] = str(e)
            return summary
    
    def _stage1_canonical_generation(self) -> Dict[str, Any]:
        """Stage 1: Generate canonical JSON files from CSV data."""
        from profiler.engines import registry
        
        stage_start = time.time()
        
        # Find all CSV files
        csv_files = list(self.data_dir.glob("*.csv"))
        log.info(f"Found {len(csv_files)} CSV files in {self.data_dir}")
        
        canonical_files = []
        errors = []
        
        for csv_file in csv_files:
            try:
                # Parse with format engine
                table = registry.parse(
                    file_path=csv_file,
                    file_format="csv",
                    encoding="utf-8",
                    sample_size=self.sample_size
                )
                table.compute_lightweight_statistics()
                
                # Derive table name from filename
                table_name = csv_file.stem  # filename without extension
                
                # Save canonical JSON (using dataclass asdict)
                output_file = self.canonical_dir / f"{table_name}.canonical.json"
                table_dict = asdict(table)
                # Remove internal fields that can't be serialized
                table_dict.pop('_row_iterator', None)
                # Add table_name field for profiling engine
                table_dict['table_name'] = table_name
                table_dict['table_id'] = table_name
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(table_dict, f, indent=2, default=str)
                
                canonical_files.append(str(output_file))
                log.info(f"  ✓ {csv_file.name} → {output_file.name}")
                
            except Exception as e:
                log.error(f"  ✗ {csv_file.name}: {e}")
                errors.append({"file": csv_file.name, "error": str(e)})
        
        return {
            "files_processed": len(csv_files),
            "files_generated": len(canonical_files),
            "errors": errors,
            "output_dir": str(self.canonical_dir),
            "time_seconds": time.time() - stage_start,
        }
    
    def _stage2_profile_generation(self) -> Dict[str, Any]:
        """Stage 2: Generate canonical+profile JSON files using the stable services pipeline."""
        from profiler import services

        stage_start = time.time()
        result = services.profile_directory(
            path=str(self.data_dir),
            output_base=str(self.output_base),
            sample_size=self.sample_size,
        )

        generated = int(result.get("profiles_generated", 0))
        log.info("Generated %d profile files via profiler.services.profile_directory", generated)

        return {
            "profiles_generated": generated,
            "output_dir": str(self.profiles_dir),
            "time_seconds": time.time() - stage_start,
            "source": "profiler.services.profile_directory",
        }
    
    def _transform_canonical_for_profiling(self):
        """Transform canonical JSON format to match profiling engine expectations."""
        import re
        
        for canonical_file in self.canonical_dir.glob("*.canonical.json"):
            with open(canonical_file, 'r', encoding='utf-8') as f:
                canon_data = json.load(f)
            
            # Extract sample values from rows
            rows = canon_data.get('rows', [])
            row_count = len(rows)
            
            # Transform columns to expected format
            if 'columns' in canon_data:
                transformed_columns = []
                for col_idx, col in enumerate(canon_data['columns']):
                    # Normalize column name
                    name = col.get('name', 'unknown')
                    normalized = self._normalize_column_name(name)
                    
                    # Extract physical type from data_type string
                    data_type_str = col.get('data_type', 'UNKNOWN')
                    if 'ColumnType.' in data_type_str:
                        physical_type = data_type_str.split('.')[-1]
                    else:
                        physical_type = str(data_type_str).upper()
                    
                    # Extract sample values from rows (transpose rows to column values)
                    sample_values = []
                    if rows and len(rows) > 0:
                        for row in rows:
                            if col_idx < len(row):
                                sample_values.append(row[col_idx])
                    
                    semantic_type = self._infer_semantic_type(
                        name,
                        normalized,
                        physical_type,
                        sample_values,
                    )

                    transformed_col = {
                        'column_id': f"{canon_data.get('table_name', 'unknown')}_{normalized}",
                        'original_name': name,
                        'normalized_name': normalized,
                        'position': col.get('index', 0),
                        'physical_type': physical_type,
                        'semantic_type': semantic_type,
                        'observed_nullable': col.get('observed_nullable', True),
                        'sample_values': sample_values,
                        'statistics': {}
                    }
                    transformed_columns.append(transformed_col)
                
                canon_data['columns'] = transformed_columns
                
                # Add metadata
                canon_data['metadata'] = {
                    'is_sample': canon_data.get('is_sample', True),
                    'sample_row_count': row_count,
                }
            
            # Save transformed canonical
            with open(canonical_file, 'w', encoding='utf-8') as f:
                json.dump(canon_data, f, indent=2)
    
    @staticmethod
    def _normalize_column_name(name: str) -> str:
        """Normalize column name to lowercase with underscores."""
        import re
        # Convert to lowercase
        normalized = name.lower()
        # Replace spaces, hyphens, dots, slashes with underscore
        normalized = re.sub(r'[\s\-\./]+', '_', normalized)
        # Remove special characters
        normalized = re.sub(r'[^\w]', '', normalized)
        # Remove leading/trailing underscores
        normalized = normalized.strip('_')
        # Collapse multiple underscores
        normalized = re.sub(r'_+', '_', normalized)
        return normalized

    @staticmethod
    def _infer_semantic_type(
        original_name: str,
        normalized_name: str,
        physical_type: str,
        sample_values: List[Any],
    ) -> str:
        """Infer semantic type from header names plus lightweight value patterns."""
        import re

        name = (normalized_name or original_name or "").lower()
        compact = re.sub(r"[^a-z0-9]", "", name)
        values = [str(v).strip() for v in sample_values if v is not None and str(v).strip() != ""]
        first_values = values[:25]

        if compact.endswith("id"):
            return "identifier" if compact == "id" or compact.endswith("cityid") else "foreign_key_candidate"

        if "email" in compact:
            return "email"
        if "phone" in compact or "mobile" in compact:
            return "phone"
        if "postcode" in compact or "postalcode" in compact or "zipcode" in compact or compact == "zip":
            return "zip_code"
        if "city" in compact and "id" not in compact:
            return "city"
        if "stateprovince" in compact or "province" in compact or compact == "state":
            return "state_province"
        if "country" in compact:
            return "country"
        if "latitude" in compact or compact == "lat":
            return "latitude"
        if "longitude" in compact or compact in {"lon", "lng"}:
            return "longitude"
        if "location" in compact or any(v.upper().startswith("POINT (") for v in first_values):
            return "geospatial_point"
        if "validfrom" in compact or compact.endswith("fromdate") or compact.endswith("startdate"):
            return "temporal_start"
        if "validto" in compact or compact.endswith("todate") or compact.endswith("enddate"):
            return "temporal_end"
        if "editedby" in compact or "createdby" in compact or "modifiedby" in compact:
            return "identifier"
        if any(token in compact for token in ("population", "count", "quantity", "amount", "price", "total")):
            return "measure"
        if physical_type.upper() in {"DATE", "DATETIME", "TIME"}:
            return "timestamp"

        return "dimension" if physical_type.upper() == "STRING" else "numeric"
    
    def _stage3_llm_descriptions(self) -> Dict[str, Any]:
        """Stage 3: Generate LLM descriptions from profile JSON."""
        from relationships.llm_description_generator import (
            NVIDIADescriptionGenerator,
            save_descriptions_to_json,
        )
        
        stage_start = time.time()
        
        # Initialize LLM generator
        llm_generator = NVIDIADescriptionGenerator(max_workers=self.max_workers)
        
        # Load all profile files
        profile_files = list(self.profiles_dir.glob("*.profile.json"))
        log.info(f"Found {len(profile_files)} profile files")
        
        # Convert profiles to table format for LLM generator
        table_profiles = {}
        for profile_file in profile_files:
            with open(profile_file, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
            
            table_name = profile_data["table_name"]
            table_profiles[table_name] = self._profile_to_table_format(profile_data)
        
        # Generate descriptions in parallel
        log.info(f"Generating descriptions with {self.max_workers} workers...")
        try:
            all_descriptions = llm_generator.generate_descriptions_for_tables(table_profiles)
        except Exception as e:
            log.warning("LLM description generation failed, switching to deterministic fallback: %s", e)
            all_descriptions = self._generate_fallback_descriptions(table_profiles)
        
        # Save descriptions
        descriptions_file = self.descriptions_dir / "descriptions.json"
        save_descriptions_to_json(all_descriptions, str(descriptions_file))
        log.info(f"Saved {len(all_descriptions)} descriptions to {descriptions_file}")
        
        return {
            "descriptions_generated": len(all_descriptions),
            "output_file": str(descriptions_file),
            "time_seconds": time.time() - stage_start,
        }

    def _generate_fallback_descriptions(self, table_profiles: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deterministic description fallback when LLM is unavailable."""
        rows: List[Dict[str, Any]] = []
        for table_name, table_data in table_profiles.items():
            for col in table_data.get("columns", []):
                col_name = str(col.get("column_name", ""))
                lower = col_name.lower()
                if lower.endswith("id") or lower.endswith("_id"):
                    domain = "PRIMARY_KEY" if lower == f"{table_name.lower()}id" else "FOREIGN_KEY"
                elif any(x in lower for x in ["validfrom", "validto", "date", "time", "timestamp"]):
                    domain = "TEMPORAL"
                elif any(x in lower for x in ["lasteditedby", "createdby", "modifiedby", "updatedby"]):
                    domain = "AUDIT"
                elif any(x in lower for x in ["amount", "price", "cost", "quantity", "count", "total", "tax"]):
                    domain = "MEASURE"
                elif any(x in lower for x in ["location", "latitude", "longitude", "geom", "point", "polygon"]):
                    domain = "GEOSPATIAL"
                elif str(col.get("physical_type", "")).lower() in {"string", "varchar", "text"}:
                    domain = "DIMENSION"
                else:
                    domain = "IDENTIFIER"

                rows.append(
                    {
                        "table_name": table_name,
                        "column_name": col_name,
                        "semantic_description": f"Semantic profile for {table_name}.{col_name}",
                        "business_purpose": f"Supports analytics and joins for {table_name}",
                        "data_domain": domain,
                        "likely_relationships": [],
                    }
                )
        return rows
    
    def _stage4_relationship_detection(self) -> Dict[str, Any]:
        """Stage 4: Detect relationships using the validated Chroma+ANN pipeline."""
        from run_neuleap_relationship_validation import _ensure_dirs, _run_relationship_validation

        stage_start = time.time()
        _ensure_dirs()
        summary = _run_relationship_validation()

        relationships_file = self.relationships_dir / "relationship.json"
        log.info("Saved domain-aware relationship output to %s", relationships_file)

        return {
            "relationships_detected": int(summary.get("accepted", 0)),
            "true_fk_count": int(summary.get("accepted", 0)),
            "output_file": str(relationships_file),
            "time_seconds": time.time() - stage_start,
            "mode": "chroma_ann_domain_validated",
        }
    
    def _stage5_low_cardinality_enrichment(self) -> Dict[str, Any]:
        """Stage 5: Enrich low-cardinality columns with LCIL (requires descriptions + relationships)."""
        from profiler.lcil import enrich_low_cardinality_intelligence
        
        stage_start = time.time()
        
        try:
            result = enrich_low_cardinality_intelligence(
                output_base=str(self.output_base),
                batch_size=10,
                max_workers=self.max_workers,
                provider="nvidia",
                model=None,
                min_confidence=0.6,
            )
            
            return {
                "success": result.get("success", False),
                "report_path": result.get("report_path"),
                "candidates_count": result.get("candidates_count", 0),
                "insights_count": result.get("insights_count", 0),
                "time_seconds": time.time() - stage_start,
            }
        
        except Exception as e:
            log.warning(f"LCIL enrichment failed (non-critical): {e}")
            return {
                "success": False,
                "error": str(e),
                "time_seconds": time.time() - stage_start,
            }

    def _stage6_generate_erd_dbml(self) -> Dict[str, Any]:
        """Stage 6: Generate ERD artifacts (DBML + graph/html) from validated relationships."""
        from profiler import services

        stage_start = time.time()
        relationship_file = self.relationships_dir / "relationship.json"
        erve_result = services.generate_er_visualizations(
            relationships_path=str(relationship_file),
            output_base=str(self.output_base),
            mode="full",
            min_confidence=0.5,
        )

        diagram_state = services.build_diagram_state(output_base=str(self.output_base), min_confidence=0.5)
        erd_json = self.output_base / "erd" / "erd.json"
        erd_json.parent.mkdir(parents=True, exist_ok=True)
        with open(erd_json, "w", encoding="utf-8") as f:
            json.dump(diagram_state, f, indent=2)

        dbml_file = self.output_base / "erd" / "schema.dbml"
        graph_json = self.output_base / "graph" / "graph.json"
        graph_html = self.output_base / "graph" / "graph.html"
        return {
            "success": dbml_file.exists(),
            "dbml_file": str(dbml_file),
            "erd_json": str(erd_json),
            "graph_json": str(graph_json),
            "graph_html": str(graph_html),
            "erve_outputs": erve_result.get("outputs", {}),
            "time_seconds": time.time() - stage_start,
        }

    @staticmethod
    def _type_compatibility_score(fk_type: str, pk_type: str) -> float:
        """Simple compatibility score for relationship confidence."""
        if not fk_type or not pk_type:
            return 0.5
        if fk_type == pk_type:
            return 1.0
        numeric_types = {"integer", "float", "decimal"}
        if fk_type in numeric_types and pk_type in numeric_types:
            return 0.8
        if "string" in {fk_type, pk_type}:
            return 0.5
        return 0.3

    @staticmethod
    def _overlap_ratio(fk_values: List[Any], pk_values: List[Any]) -> float:
        """Compute distinct-value overlap relative to PK distinct count."""
        fk_set = {v for v in fk_values if v not in (None, "")}
        pk_set = {v for v in pk_values if v not in (None, "")}
        if not pk_set:
            return 0.0
        return len(fk_set & pk_set) / len(pk_set)

    @staticmethod
    def _name_similarity(left: str, right: str) -> float:
        """Cheap name similarity for confidence scoring."""
        left = (left or "").lower()
        right = (right or "").lower()
        if left == right:
            return 1.0
        if left in right or right in left:
            return 0.8
        left_tokens = set(filter(None, re.split(r"[_\W]+", left)))
        right_tokens = set(filter(None, re.split(r"[_\W]+", right)))
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    
    def _profile_to_table_format(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert profile JSON to format expected by LLM generator."""
        table_format = {
            "table_name": profile_data["table_name"],
            "columns": []
        }
        
        for col in profile_data["columns"]:
            col_format = {
                "column_name": col["column_name"],
                "physical_type": col["physical_type"],
                "semantic_type": col.get("semantic_type", "UNKNOWN"),
                "sample_values": col.get("sample_values", []),
                "statistics": col.get("statistics", {}),
            }
            table_format["columns"].append(col_format)
        
        return table_format
    
    def _print_summary(self, summary: Dict[str, Any]):
        """Print final pipeline summary."""
        log.info("\n" + "=" * 80)
        log.info("PIPELINE COMPLETE")
        log.info("=" * 80)
        
        stages = summary.get("stages", {})
        
        # Stage 1
        if "canonical_generation" in stages:
            s1 = stages["canonical_generation"]
            log.info(f"\n[STAGE 1] Canonical Generation:")
            log.info(f"  Files processed: {s1['files_processed']}")
            log.info(f"  Files generated: {s1['files_generated']}")
            log.info(f"  Time: {s1['time_seconds']:.2f}s")
        
        # Stage 2
        if "profile_generation" in stages:
            s2 = stages["profile_generation"]
            log.info(f"\n[STAGE 2] Profile Generation:")
            log.info(f"  Profiles generated: {s2['profiles_generated']}")
            log.info(f"  Time: {s2['time_seconds']:.2f}s")
        
        # Stage 3
        if "llm_descriptions" in stages:
            s3 = stages["llm_descriptions"]
            log.info(f"\n[STAGE 3] LLM Descriptions:")
            log.info(f"  Descriptions generated: {s3['descriptions_generated']}")
            log.info(f"  Time: {s3['time_seconds']:.2f}s")
        
        # Stage 4
        if "relationship_detection" in stages:
            s4 = stages["relationship_detection"]
            log.info(f"\n[STAGE 4] Relationship Detection:")
            log.info(f"  Relationships detected: {s4['relationships_detected']}")
            log.info(f"  TRUE_FK count: {s4['true_fk_count']}")
            log.info(f"  Time: {s4['time_seconds']:.2f}s")
        
        # Stage 5
        if "low_cardinality_enrichment" in stages:
            s5 = stages["low_cardinality_enrichment"]
            log.info(f"\n[STAGE 5] Low Cardinality Intelligence (LCIL):")
            log.info(f"  Candidates identified: {s5.get('candidates_count', 0)}")
            log.info(f"  Insights generated: {s5.get('insights_count', 0)}")
            log.info(f"  Success: {'✓' if s5.get('success') else '✗'}")
            log.info(f"  Time: {s5['time_seconds']:.2f}s")

        # Stage 6
        if "erd_dbml_generation" in stages:
            s6 = stages["erd_dbml_generation"]
            log.info(f"\n[STAGE 6] ERD DBML Generation:")
            log.info(f"  Success: {'✓' if s6.get('success') else '✗'}")
            log.info(f"  DBML file: {s6.get('dbml_file', 'output/erd/schema.dbml')}")
            log.info(f"  ERD JSON: {s6.get('erd_json', 'output/erd/erd.json')}")
            log.info(f"  Graph JSON: {s6.get('graph_json', 'output/graph/graph.json')}")
            log.info(f"  Graph HTML: {s6.get('graph_html', 'output/graph/graph.html')}")
            log.info(f"  Time: {s6['time_seconds']:.2f}s")
        
        # Total
        log.info(f"\n{'=' * 80}")
        log.info(f"TOTAL PIPELINE TIME: {summary['total_time_seconds']:.2f}s")
        log.info(f"{'=' * 80}")
        
        # Output files
        log.info(f"\nOutput Files:")
        log.info(f"  Canonical:     {self.canonical_dir}/*.canonical.json")
        log.info(f"  Profiles:      {self.profiles_dir}/*.profile.json")
        log.info(f"  LCIL Insights: output/low_cardinality/low_cardinality_insights.json")
        log.info(f"  Descriptions:  {self.descriptions_dir}/descriptions.json")
        log.info(f"  Relationships: {self.relationships_dir}/relationship.json")
        log.info(f"  ERD DBML:      output/erd/schema.dbml")
        log.info(f"  ERD JSON:      output/erd/erd.json")
        log.info(f"  ER Graph:      output/graph/graph.json, output/graph/graph.html")


def main():
    """Main entry point."""
    agent = ProfilingAgent(
        data_dir="data",
        output_base="output",
        sample_size=100,
        max_workers=15,
    )
    
    result = agent.run_full_pipeline()
    
    if result.get("success"):
        log.info("\n✅ Pipeline completed successfully!")
        return 0
    else:
        log.error(f"\n❌ Pipeline failed: {result.get('error')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
