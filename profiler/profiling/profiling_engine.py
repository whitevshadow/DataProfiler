"""
Profiling Engine — Main Orchestrator

Coordinates all profiling components to generate complete FileProfile from CanonicalTable.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from profiler.profiling.profiling_models import (
    FileProfile,
    ColumnProfile,
    TableProfile,
    ProfilingMetadata,
    ColumnStatistics,
    PhysicalType,
    SemanticType,
    FKEvidence,
    RelationalRole,
    LogicalType,
    QualityFlag,
    CardinalityClass,
)
from profiler.profiling.statistics_engine import compute_statistics
from profiler.profiling.pk_detector import compute_pk_score, rank_pk_candidates
from profiler.profiling.fk_detector import detect_foreign_key, classify_relational_role
from profiler.profiling.quality_engine import detect_quality_flags, compute_quality_score

log = logging.getLogger(__name__)

__version__ = "1.0.0"


def classify_cardinality(distinct_count: int) -> CardinalityClass:
    """
    Classify column cardinality based on distinct value count.
    
    Args:
        distinct_count: Number of distinct values
        
    Returns:
        CardinalityClass enum value
    """
    if distinct_count <= 50:
        return CardinalityClass.LOW
    elif distinct_count <= 1000:
        return CardinalityClass.MEDIUM
    else:
        return CardinalityClass.HIGH


def profile_canonical_table(
    canonical_json_path: Path,
    output_dir: Optional[Path] = None
) -> FileProfile:
    """
    Profile a CanonicalTable JSON artifact.
    
    Args:
        canonical_json_path: Path to .canonical.json file
        output_dir: Where to save profile output (optional)
        
    Returns:
        FileProfile object
        
    Raises:
        ValueError: Invalid canonical JSON
        FileNotFoundError: File not found
    """
    
    start_time = time.time()
    
    # Load canonical JSON
    with open(canonical_json_path, 'r', encoding='utf-8') as f:
        canonical_data = json.load(f)
    
    # Profile from dict
    profile = profile_from_dict(canonical_data, str(canonical_json_path))
    
    # Update execution time
    execution_time_ms = (time.time() - start_time) * 1000
    profile.profiling_metadata.execution_time_ms = execution_time_ms
    
    # Save to output dir if specified
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_filename = f"{profile.table_name}.profile.json"
        output_path = output_dir / output_filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(profile.model_dump_json(indent=2))
        
        log.info(f"Saved profile: {output_path}")
    
    return profile


def profile_from_dict(
    canonical_dict: Dict[str, Any],
    source_path: str = None
) -> FileProfile:
    """
    Profile from in-memory canonical dict.
    
    Args:
        canonical_dict: CanonicalTable as dict
        source_path: Source file path (for reference)
        
    Returns:
        FileProfile object
    """
    
    table_id = canonical_dict.get("table_id", "unknown")
    table_name = canonical_dict.get("table_name", "unknown")
    metadata = canonical_dict.get("metadata", {})
    columns_data = canonical_dict.get("columns", [])
    
    log.info(f"Profiling table: {table_name} ({len(columns_data)} columns)")
    
    # Profile each column
    column_profiles = []
    
    for col_data in columns_data:
        try:
            col_profile = _profile_column(col_data, metadata, table_name)
            column_profiles.append(col_profile)
        
        except Exception as e:
            log.error(f"Failed to profile column {col_data.get('column_id')}: {e}")
            continue
    
    # Collect PK/FK candidates based on final relational role
    pk_candidates_with_scores = []
    fk_candidates_with_scores = []
    
    for col_profile in column_profiles:
        # Use relational role as final authority
        if col_profile.relational_role == RelationalRole.PRIMARY_KEY:
            pk_candidates_with_scores.append((
                col_profile.column_name,
                col_profile.pk_confidence,
                col_profile.pk_evidence
            ))
        elif col_profile.relational_role == RelationalRole.FOREIGN_KEY:
            fk_candidates_with_scores.append((
                col_profile.column_name,
                col_profile.fk_confidence,
                col_profile.fk_evidence
            ))
    
    # Rank PK candidates
    ranked_pks = rank_pk_candidates(pk_candidates_with_scores)
    pk_candidate_names = [name for name, score, _ in ranked_pks]
    
    # Rank FK candidates (by confidence desc)
    fk_candidates_with_scores.sort(key=lambda x: x[1], reverse=True)
    fk_candidate_names = [name for name, score, _ in fk_candidates_with_scores]
    
    # Table-level aggregates
    table_profile = _compute_table_profile(
        column_profiles,
        pk_candidate_names,
        fk_candidate_names,
        metadata.get("sample_row_count")
    )
    
    # Profiling metadata
    profiling_metadata = ProfilingMetadata(
        profiled_at=datetime.now(),
        profiler_version=__version__,
        execution_time_ms=0.0,  # Updated by caller
        sample_based=metadata.get("is_sample", True),
        sample_size=metadata.get("sample_row_count"),
        canonical_table_id=table_id
    )
    
    # Generate profile ID
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    profile_id = f"prof_{table_id}_{timestamp}"
    
    # Build FileProfile
    profile = FileProfile(
        profile_id=profile_id,
        table_name=table_name,
        profiling_metadata=profiling_metadata,
        table_profile=table_profile,
        columns=column_profiles,
        source_canonical_path=source_path
    )
    
    log.info(
        f"Profiling complete: {table_name} "
        f"(PK candidates: {len(pk_candidate_names)}, "
        f"Quality score: {table_profile.quality_score:.2f})"
    )
    
    return profile


def _profile_column(col_data: Dict[str, Any], table_metadata: Dict[str, Any], table_name: str) -> ColumnProfile:
    """
    Profile a single column from CanonicalTable data.
    
    Args:
        col_data: Column data from CanonicalTable
        table_metadata: Table-level metadata
        table_name: Table name (for FK self-referential detection)
        
    Returns:
        ColumnProfile
    """
    
    # Extract column info
    column_id = col_data.get("column_id")
    original_name = col_data.get("original_name")
    normalized_name = col_data.get("normalized_name")
    position = col_data.get("position", 0)
    physical_type_str = col_data.get("physical_type", "UNKNOWN")
    semantic_type_str = col_data.get("semantic_type")
    observed_nullable = col_data.get("observed_nullable", True)
    sample_values = col_data.get("sample_values", [])
    existing_stats = col_data.get("statistics", {})
    
    # Parse types
    try:
        physical_type = PhysicalType[physical_type_str.upper()]
    except (KeyError, AttributeError):
        physical_type = PhysicalType.UNKNOWN
    
    try:
        semantic_type = SemanticType[semantic_type_str.upper()] if semantic_type_str else None
    except (KeyError, AttributeError):
        semantic_type = None
    
    # Compute statistics
    statistics = compute_statistics(
        sample_values=sample_values,
        physical_type=physical_type,
        existing_stats=existing_stats
    )
    
    # Type confidence (from existing implementation)
    type_confidence = 0.9  # Default high confidence from Layer 5
    
    # PK detection with suppression rules
    pk_score, pk_evidence, is_pk_candidate = compute_pk_score(
        column_name=normalized_name,
        uniqueness_ratio=statistics.uniqueness_ratio,
        null_ratio=statistics.null_ratio,
        entropy_normalized=statistics.entropy_normalized,
        type_confidence=type_confidence,
        distinct_count=statistics.distinct_count,
        sample_size=len(sample_values),
        physical_type=physical_type_str,  # Pass for temporal detection
        sample_values=sample_values  # Pass for sentinel value detection
    )
    
    # Quality flags
    quality_flags = detect_quality_flags(
        column_name=normalized_name,
        physical_type=physical_type,
        semantic_type=semantic_type,
        null_ratio=statistics.null_ratio,
        distinct_count=statistics.distinct_count,
        total_count=len(sample_values),
        entropy_normalized=statistics.entropy_normalized,
        skewness=statistics.skewness
    )
    
    # Quality score
    quality_score = compute_quality_score(quality_flags)
    
    # FK detection (detect relational references)
    fk_evidence_obj = detect_foreign_key(
        column_name=normalized_name,
        table_name=table_name,
        physical_type=physical_type_str,
        uniqueness_ratio=statistics.uniqueness_ratio,
        null_ratio=statistics.null_ratio,
        entropy_normalized=statistics.entropy_normalized,
        is_pk_candidate=is_pk_candidate,
        pk_confidence=pk_score
    )
    
    is_fk_candidate = fk_evidence_obj.is_fk_candidate
    fk_score = fk_evidence_obj.fk_confidence
    
    # Convert FK evidence to model format
    fk_evidence_model = None
    if is_fk_candidate:
        fk_evidence_model = FKEvidence(
            fk_pattern_match=fk_evidence_obj.fk_pattern_match,
            referenced_entity=fk_evidence_obj.referenced_entity,
            entity_mismatch_score=fk_evidence_obj.entity_mismatch_score,
            reasons=fk_evidence_obj.reasoning,
            warnings=fk_evidence_obj.warnings
        )
    
    semantic_value = semantic_type.value if semantic_type else ""
    normalized_for_role = (normalized_name or "").lower()

    # Determine flags for relational role classification
    is_temporal = (
        physical_type in {PhysicalType.DATE, PhysicalType.DATETIME, PhysicalType.TIME}
        or semantic_value in {"timestamp", "temporal", "temporal_start", "temporal_end"}
        or any(token in normalized_for_role for token in ("validfrom", "validto", "createdat", "updatedat"))
    )
    is_audit = any(
        token in normalized_for_role
        for token in ("lasteditedby", "createdby", "modifiedby", "updatedby", "lastmodifiedby")
    )
    is_measure = (
        QualityFlag.SKEWED_DISTRIBUTION in quality_flags
        or semantic_value in {"measure", "count", "percentage", "numeric", "amount", "price"}
    )
    is_geospatial = semantic_value in {
        "geospatial_point",
        "geographic_entity",
        "geospatial_coordinate",
        "latitude",
        "longitude",
    }
    
    # Relational role classification
    relational_classification = classify_relational_role(
        column_name=normalized_name,
        physical_type=physical_type_str,
        is_pk_candidate=is_pk_candidate,
        is_fk_candidate=is_fk_candidate,
        pk_confidence=pk_score,
        fk_confidence=fk_score,
        is_temporal=is_temporal,
        is_audit=is_audit,
        is_measure=is_measure,
        is_geospatial=is_geospatial
    )
    
    # Convert enums to model enums
    try:
        relational_role = RelationalRole(relational_classification.relational_role.value)
    except (ValueError, AttributeError):
        relational_role = None
    
    try:
        logical_type = LogicalType(relational_classification.logical_type.value)
    except (ValueError, AttributeError):
        logical_type = None
    
    # Classify cardinality
    cardinality_class = classify_cardinality(statistics.distinct_count)
    
    # Build ColumnProfile
    column_profile = ColumnProfile(
        column_name=normalized_name,
        original_name=original_name,
        position=position,
        physical_type=physical_type,
        semantic_type=semantic_type,
        logical_type=logical_type,
        type_confidence=type_confidence,
        completeness=1.0 - statistics.null_ratio,
        uniqueness=statistics.uniqueness_ratio,
        entropy_normalized=statistics.entropy_normalized,
        cardinality_class=cardinality_class,
        relational_role=relational_role,
        pk_candidate=is_pk_candidate,
        pk_confidence=pk_score,
        pk_evidence=pk_evidence if is_pk_candidate else None,
        fk_candidate=is_fk_candidate,
        fk_confidence=fk_score,
        fk_evidence=fk_evidence_model,
        quality_flags=quality_flags,
        quality_score=quality_score,
        statistics=statistics,
        sample_values=sample_values[:10] if sample_values else None  # Keep first 10 for debugging
    )
    
    return column_profile


def _compute_table_profile(
    column_profiles: list,
    pk_candidate_names: list,
    fk_candidate_names: list,
    row_count_estimate: int
) -> TableProfile:
    """
    Compute table-level profile aggregates.
    
    Args:
        column_profiles: List of ColumnProfile objects
        pk_candidate_names: List of PK candidate column names
        fk_candidate_names: List of FK candidate column names
        row_count_estimate: Estimated row count
        
    Returns:
        TableProfile
    """
    
    column_count = len(column_profiles)
    
    # Completeness score (average of column completeness)
    if column_profiles:
        completeness_score = sum(c.completeness for c in column_profiles) / len(column_profiles)
    else:
        completeness_score = 0.0
    
    # Quality score (average of column quality scores)
    if column_profiles:
        quality_score = sum(c.quality_score for c in column_profiles) / len(column_profiles)
    else:
        quality_score = 0.0
    
    # Count quality flags
    total_quality_flags = sum(len(c.quality_flags) for c in column_profiles)
    columns_with_issues = sum(1 for c in column_profiles if c.quality_flags)
    
    return TableProfile(
        row_count_estimate=row_count_estimate,
        column_count=column_count,
        completeness_score=completeness_score,
        quality_score=quality_score,
        pk_candidates=pk_candidate_names,
        fk_candidates=fk_candidate_names,
        total_quality_flags=total_quality_flags,
        columns_with_issues=columns_with_issues
    )


def batch_profile(
    canonical_dir: Path,
    output_dir: Path = Path("output/profiles"),
    parallel: bool = True,
    max_workers: int = 4
) -> Dict[str, FileProfile]:
    """
    Profile multiple canonical files in parallel.
    
    Args:
        canonical_dir: Directory containing .canonical.json files
        output_dir: Where to save profile outputs
        parallel: Whether to use parallel processing
        max_workers: Number of parallel workers
        
    Returns:
        {filename: FileProfile}
    """
    
    canonical_files = list(Path(canonical_dir).glob("*.canonical.json"))
    
    if not canonical_files:
        log.warning(f"No canonical JSON files found in {canonical_dir}")
        return {}
    
    log.info(f"Batch profiling {len(canonical_files)} files...")
    
    profiles = {}
    
    if parallel and len(canonical_files) > 1:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(profile_canonical_table, f, output_dir): f
                for f in canonical_files
            }
            
            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    profile = future.result()
                    profiles[file_path.name] = profile
                    log.info(f"✓ Profiled: {file_path.name}")
                except Exception as e:
                    log.error(f"✗ Failed: {file_path.name} - {e}")
    else:
        # Sequential processing
        for file_path in canonical_files:
            try:
                profile = profile_canonical_table(file_path, output_dir)
                profiles[file_path.name] = profile
                log.info(f"✓ Profiled: {file_path.name}")
            except Exception as e:
                log.error(f"✗ Failed: {file_path.name} - {e}")
    
    log.info(f"Batch profiling complete: {len(profiles)}/{len(canonical_files)} succeeded")
    
    return profiles
