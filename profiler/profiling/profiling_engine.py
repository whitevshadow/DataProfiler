"""
Profiling Engine — Main Orchestrator

Coordinates all profiling components to generate complete FileProfile from CanonicalTable.
"""

import json
import logging
import re
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
    PhysicalType,
    SemanticType,
    LogicalType,
    QualityFlag,
    CardinalityClass,
    ProfileHints,
)
from profiler.profiling.statistics_engine import DuckDBProfileContext, compute_statistics
from profiler.profiling.pk_detector import compute_pk_score, rank_pk_candidates, select_single_pk, extract_table_root, extract_column_root
from profiler.profiling.quality_engine import detect_quality_flags

log = logging.getLogger(__name__)

__version__ = "1.0.0"


def classify_cardinality(cardinality_ratio: float) -> CardinalityClass:
    """
    Classify column cardinality based on distinct value count.
    
    Args:
        distinct_count: Number of distinct values
        
    Returns:
        CardinalityClass enum value
    """
    if cardinality_ratio >= 0.80:
        return CardinalityClass.HIGH
    if cardinality_ratio >= 0.20:
        return CardinalityClass.MEDIUM
    return CardinalityClass.LOW


def profile(raw: Dict[str, Any]) -> ColumnProfile:
    """Public single-column profiling entry point."""
    table_metadata = raw.get("table_metadata", {}) if isinstance(raw, dict) else {}
    table_name = raw.get("table_name", "unknown") if isinstance(raw, dict) else "unknown"
    return _profile_column(dict(raw), table_metadata, table_name)


def _is_nullish(value: Any) -> bool:
    return value is None or value == "" or str(value).strip().lower() in {"null", "none", "nan"}


def _non_null_values(values: list[Any]) -> list[Any]:
    return [v for v in values if not _is_nullish(v)]


def _is_identifier_like(column_name: str, semantic_type: Optional[SemanticType] = None) -> bool:
    name = (column_name or "").lower()
    return (
        semantic_type in {SemanticType.IDENTIFIER, SemanticType.NATURAL_KEY, SemanticType.SURROGATE_KEY}
        or bool(re.search(r'(^id$|id$|_id$|key$|_key$|code$|identifier$)', name))
    )


def _is_audit_identifier_name(column_name: str) -> bool:
    name = (column_name or "").lower()
    patterns = (
        r'createdby$',
        r'modifiedby$',
        r'lasteditedby$',
        r'editedby$',
        r'approvedby$',
        r'deletedby$',
        r'reviewedby$',
        r'insertedby$',
        r'updatedby$',
        r'userid$',
        r'editorid$',
        r'creatorid$',
        r'user_id$',
        r'editor_id$',
        r'creator_id$',
    )
    return any(re.search(pattern, name) for pattern in patterns)


def _all_whole_numbers(values: list[Any]) -> bool:
    non_null = _non_null_values(values)
    if not non_null:
        return False
    for value in non_null:
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            return False
        if not number.is_integer():
            return False
    return True


def _boolean_like(values: list[Any]) -> bool:
    non_null = [str(v).strip().lower() for v in _non_null_values(values)]
    if not non_null:
        return False
    boolean_values = {"true", "false", "yes", "no", "0", "1", "t", "f", "y", "n"}
    distinct_values = set(non_null)
    return len(distinct_values) == 2 and distinct_values.issubset(boolean_values)


def _normalize_physical_type(
    column_name: str,
    physical_type: PhysicalType,
    sample_values: list[Any],
    semantic_type: Optional[SemanticType],
) -> tuple[PhysicalType, float]:
    """Normalize physical type without forcing weak evidence into a bad guess."""
    non_null = _non_null_values(sample_values)
    if not non_null:
        return PhysicalType.UNKNOWN, 0.0

    if _is_audit_identifier_name(column_name) and _all_whole_numbers(sample_values):
        return PhysicalType.INTEGER, 0.95

    if _boolean_like(sample_values):
        return PhysicalType.BOOLEAN, 0.95

    if physical_type == PhysicalType.FLOAT and _is_identifier_like(column_name, semantic_type) and _all_whole_numbers(sample_values):
        return PhysicalType.INTEGER, 0.95

    if physical_type == PhysicalType.UNKNOWN:
        if len(non_null) < 5:
            return PhysicalType.UNKNOWN, 0.40
        if _is_identifier_like(column_name, semantic_type) and _all_whole_numbers(sample_values):
            return PhysicalType.INTEGER, 0.90
        if _all_whole_numbers(sample_values):
            return PhysicalType.INTEGER, 0.80
        if _looks_temporal(column_name, sample_values):
            return PhysicalType.DATETIME, 0.80

    return physical_type, 0.90 if physical_type != PhysicalType.UNKNOWN else 0.50


def _looks_temporal(column_name: str, values: list[Any]) -> bool:
    name = (column_name or "").lower()
    if any(token in name for token in ("date", "time", "timestamp", "validfrom", "validto", "createdat", "updatedat")):
        return True
    patterns = [
        r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}',
        r'^\d{1,2}[-/]\d{1,2}[-/]\d{4}',
    ]
    non_null = [str(v).strip() for v in _non_null_values(values)]
    if not non_null:
        return False
    matches = sum(1 for value in non_null[:20] if any(re.match(pattern, value) for pattern in patterns))
    return matches >= max(1, int(len(non_null[:20]) * 0.8))


def _infer_semantic_type(column_name: str, physical_type: PhysicalType, existing: Optional[SemanticType]) -> SemanticType:
    if existing:
        return existing
    name = (column_name or "").lower()
    if _is_audit_identifier_name(name):
        return SemanticType.IDENTIFIER
    if _is_identifier_like(name, existing):
        return SemanticType.IDENTIFIER
    if any(token in name for token in ("validfrom", "validto", "createdat", "updatedat", "timestamp", "date")):
        return SemanticType.TEMPORAL
    if any(token in name for token in ("latitude", "longitude", "location", "geometry", "shape")):
        return SemanticType.GEOSPATIAL_COORDINATE
    if any(token in name for token in ("amount", "price", "quantity", "total", "count", "balance", "population", "revenue", "cost", "rate", "percentage")):
        return SemanticType.MEASURE
    if any(token in name for token in ("description", "comment", "remarks")):
        return SemanticType.DESCRIPTION
    if any(token in name for token in ("name", "title", "label")):
        return SemanticType.NAME
    if physical_type == PhysicalType.BOOLEAN:
        return SemanticType.BOOLEAN_FLAG
    return SemanticType.UNKNOWN


def _infer_logical_type(column_name: str, physical_type: PhysicalType, semantic_type: SemanticType) -> LogicalType:
    name = (column_name or "").lower()
    if _is_audit_identifier_name(name):
        return LogicalType.AUDIT_REFERENCE
    if semantic_type in {SemanticType.IDENTIFIER, SemanticType.NATURAL_KEY, SemanticType.SURROGATE_KEY}:
        return LogicalType.IDENTIFIER
    if semantic_type in {SemanticType.TIMESTAMP, SemanticType.TEMPORAL, SemanticType.TEMPORAL_START, SemanticType.TEMPORAL_END}:
        return LogicalType.TIMESTAMP
    if any(token in name for token in ("createdby", "updatedby", "modifiedby", "lasteditedby", "audit_")):
        return LogicalType.AUDIT
    if semantic_type in {SemanticType.MEASURE, SemanticType.COUNT, SemanticType.PERCENTAGE, SemanticType.AMOUNT, SemanticType.PRICE}:
        return LogicalType.MEASURE
    if semantic_type in {SemanticType.LATITUDE, SemanticType.LONGITUDE, SemanticType.GEO_POINT, SemanticType.GEOSPATIAL_POINT, SemanticType.GEOSPATIAL_COORDINATE}:
        return LogicalType.GEOSPATIAL
    if semantic_type in {SemanticType.DESCRIPTION, SemanticType.COMMENT, SemanticType.FREE_TEXT, SemanticType.NAME}:
        return LogicalType.DESCRIPTION
    if physical_type == PhysicalType.BOOLEAN or semantic_type in {SemanticType.CATEGORY, SemanticType.ENUM, SemanticType.BOOLEAN_FLAG}:
        return LogicalType.CATEGORY
    return LogicalType.UNKNOWN


def _normalize_entity_token(value: str) -> str:
    token = re.sub(r'[^a-z0-9]', '', (value or "").lower())
    if token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _matches_table_identifier(column_name: str, table_name: str) -> bool:
    name = _normalize_entity_token(column_name)
    if name in {"id", "key"}:
        return True
    if not name.endswith(("id", "key")):
        return False
    stem = re.sub(r'(id|key)$', '', name)
    table_parts = re.split(r'[_\W]+', (table_name or "").lower())
    table_tokens = [_normalize_entity_token(part) for part in table_parts if part]
    table_tokens.append(_normalize_entity_token(table_name))
    return stem in table_tokens


def _detect_temporal_pattern(column_name: str, table_columns: set[str], sample_values: list[Any]) -> Optional[dict[str, Any]]:
    name = (column_name or "").lower()
    start_names = {"validfrom", "effective_from", "effectivefrom", "startdate", "start_date"}
    end_names = {"validto", "effective_to", "effectiveto", "enddate", "end_date"}
    compact_columns = {_normalize_entity_token(c): c for c in table_columns}
    normalized_start_names = [_normalize_entity_token(v) for v in start_names]
    normalized_end_names = [_normalize_entity_token(v) for v in end_names]
    is_start = _normalize_entity_token(name) in normalized_start_names
    is_end = _normalize_entity_token(name) in normalized_end_names
    if not (is_start or is_end):
        return None

    open_ended = any("9999" in str(v) for v in sample_values if v is not None)
    return {
        "type": "effective_dating",
        "subtype": "SCD2",
        "start_column": compact_columns.get("validfrom") or compact_columns.get("effectivefrom") or "validfrom",
        "end_column": compact_columns.get("validto") or compact_columns.get("effectiveto") or "validto",
        "open_ended": open_ended or is_end,
    }


def _parse_geo_profile(sample_values: list[Any]) -> Optional[dict[str, Any]]:
    lats: list[float] = []
    lons: list[float] = []
    for value in sample_values:
        match = re.search(r'POINT\s*\(\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*\)', str(value), re.IGNORECASE)
        if match:
            lon = float(match.group(1))
            lat = float(match.group(2))
            lons.append(lon)
            lats.append(lat)
    if not lats:
        return None
    return {
        "format": "WKT",
        "subtype": "POINT",
        "latitude_range": [min(lats), max(lats)],
        "longitude_range": [min(lons), max(lons)],
        "extracted_lat": lats[:10],
        "extracted_lon": lons[:10],
    }


def _detect_audit_profile(column_name: str) -> Optional[dict[str, Any]]:
    name = (column_name or "").lower()
    patterns = {
        "createdby": ("user_reference", "creator"),
        "modifiedby": ("user_reference", "modifier"),
        "updatedby": ("user_reference", "updater"),
        "lasteditedby": ("user_reference", "editor"),
        "editedby": ("user_reference", "editor"),
        "approvedby": ("user_reference", "approver"),
        "deletedby": ("user_reference", "deleter"),
        "reviewedby": ("user_reference", "reviewer"),
        "insertedby": ("user_reference", "creator"),
        "userid": ("user_reference", "user"),
        "editorid": ("user_reference", "editor"),
        "creatorid": ("user_reference", "creator"),
        "createddate": ("timestamp", "created"),
        "modifieddate": ("timestamp", "modified"),
    }
    compact = _normalize_entity_token(name)
    for token, (role, audit_type) in patterns.items():
        if token in compact:
            return {
                "role": role,
                "audit_type": audit_type,
                "system_generated": True,
            }
    return None


def _infer_composite_pk_candidates(
    table_name: str,
    column_profiles: list[ColumnProfile],
    pk_candidate_names: list[str],
) -> list[list[str]]:
    """Infer composite PK candidates for history, bridge, and holdings-style tables."""
    table_name_l = (table_name or "").lower()
    by_name = {c.column_name: c for c in column_profiles}
    existing = set(pk_candidate_names)
    composites: list[list[str]] = []

    id_like = [
        c for c in column_profiles
        if _is_identifier_like(c.column_name, c.semantic_type) and not c.audit_profile
    ]
    temporal_start = [
        c.column_name for c in column_profiles
        if c.column_name in {"validfrom", "effectivefrom", "effective_from", "startdate", "start_date"}
    ]
    descriptive_count = sum(
        1 for c in column_profiles
        if c.logical_type in {LogicalType.DESCRIPTION, LogicalType.DIMENSION, LogicalType.CATEGORY}
    )

    # History/SCD support: if owner ID is repeated and temporal boundary exists.
    table_root = extract_table_root(table_name)
    owner_cols = [c for c in id_like if extract_column_root(c.column_name) == table_root]
    if owner_cols and temporal_start:
        owner = sorted(owner_cols, key=lambda c: c.uniqueness, reverse=True)[0]
        if owner.uniqueness < 0.99:
            composites.append([owner.column_name, temporal_start[0]])

    # Bridge table support: 2+ FK-like IDs and few descriptive attributes.
    likely_bridge = any(token in table_name_l for token in ["line", "bridge", "mapping", "stockitemstockgroups", "orderlines", "invoicelines", "purchaseorderlines"])
    if likely_bridge:
        fk_like = [c for c in id_like if c.column_name not in existing]
        fk_like = sorted(fk_like, key=lambda c: c.uniqueness, reverse=True)
        if len(fk_like) >= 2:
            composites.append([fk_like[0].column_name, fk_like[1].column_name])

    # Holding/inventory/balance/status support.
    if any(token in table_name_l for token in ["holdings", "inventory", "balances", "stock", "status"]):
        anchor = next((c.column_name for c in id_like if c.column_name in {"stockitemid", "stock_item_id", "itemid"}), None)
        if anchor:
            for secondary in ["binlocation", "warehouseid", "location"]:
                if secondary in by_name:
                    composites.append([anchor, secondary])
                    break

    # Deduplicate while preserving order.
    unique: list[list[str]] = []
    seen: set[tuple[str, str]] = set()
    for pair in composites:
        if len(pair) != 2:
            continue
        key = (pair[0], pair[1])
        if key in seen:
            continue
        seen.add(key)
        unique.append(pair)
    return unique


def _quality_breakdown(statistics, quality_flags: list[QualityFlag]) -> Dict[str, float]:
    completeness = statistics.coverage_ratio
    uniqueness = max(0.0, 1.0 - statistics.duplicate_ratio)
    consistency = 0.6 if QualityFlag.TYPE_CONFLICT in quality_flags else 1.0
    validity_penalty = 0.0
    for flag in quality_flags:
        if flag in {QualityFlag.INVALID_EMAIL, QualityFlag.INVALID_BOOLEAN, QualityFlag.INVALID_RANGE, QualityFlag.ZERO_ENTROPY}:
            validity_penalty += 0.2
    validity = max(0.0, 1.0 - validity_penalty)
    anomaly_score = 0.5 if any(flag in quality_flags for flag in {QualityFlag.EXTREME_SKEWNESS, QualityFlag.SKEWED_DISTRIBUTION}) else 1.0
    return {
        "completeness": round(completeness, 4),
        "uniqueness": round(uniqueness, 4),
        "consistency": round(consistency, 4),
        "validity": round(validity, 4),
        "anomaly_score": round(anomaly_score, 4),
    }


def _weighted_quality_score(breakdown: Dict[str, float]) -> float:
    return round(
        breakdown.get("completeness", 0.0) * 0.30
        + breakdown.get("uniqueness", 0.0) * 0.20
        + breakdown.get("consistency", 0.0) * 0.20
        + breakdown.get("validity", 0.0) * 0.20
        + breakdown.get("anomaly_score", 0.0) * 0.10,
        4,
    )


def _build_profile_hints(
    physical_type: PhysicalType,
    semantic_type: SemanticType,
    logical_type: LogicalType,
) -> ProfileHints:
    return ProfileHints(
        is_identifier=logical_type in {LogicalType.IDENTIFIER, LogicalType.AUDIT_REFERENCE},
        is_temporal=logical_type == LogicalType.TIMESTAMP,
        is_audit=logical_type in {LogicalType.AUDIT, LogicalType.AUDIT_REFERENCE},
        is_measure=logical_type == LogicalType.MEASURE,
        is_dimension=logical_type in {LogicalType.CATEGORY, LogicalType.DESCRIPTION} or semantic_type in {SemanticType.NAME, SemanticType.CATEGORY, SemanticType.ENUM},
        is_text=physical_type == PhysicalType.STRING and logical_type == LogicalType.DESCRIPTION,
    )


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
    sampling_info = canonical_dict.get("sampling", {})
    row_count = (
        sampling_info.get("total_rows_estimate")
        or sampling_info.get("sample_size")
        or metadata.get("sample_row_count")
    )
    table_column_names = {str(c.get("normalized_name")) for c in columns_data if c.get("normalized_name")}
    duckdb_context = DuckDBProfileContext(canonical_dict, source_path)
    row_count = duckdb_context.total_rows()
    
    log.info(f"Profiling table: {table_name} ({len(columns_data)} columns)")
    
    # Profile each column
    column_profiles = []
    
    try:
        for col_data in columns_data:
            try:
                col_profile = _profile_column(
                    dict(col_data),
                    metadata,
                    table_name,
                    table_column_names=table_column_names,
                    duckdb_context=duckdb_context,
                )
                column_profiles.append(col_profile)
            
            except Exception as e:
                log.error(f"Failed to profile column {col_data.get('column_id')}: {e}")
                continue
    finally:
        duckdb_context.close()
    
    # Collect PK candidates based on strict PK scoring only.
    pk_candidates_with_scores = []
    
    for col_profile in column_profiles:
        if col_profile.pk_candidate:
            pk_candidates_with_scores.append((
                col_profile.column_name,
                col_profile.pk_confidence,
                col_profile.pk_evidence
            ))
    
    # Enforce single PK selection per table
    pk_candidate_names = select_single_pk(pk_candidates_with_scores, table_name)

    # Owner fallback: never leave clear owner identifiers unselected.
    if not pk_candidate_names:
        table_root = extract_table_root(table_name)
        owner_fallbacks = [
            c for c in column_profiles
            if _is_identifier_like(c.column_name, c.semantic_type)
            and extract_column_root(c.column_name) == table_root
            and not c.audit_profile
        ]
        if owner_fallbacks:
            winner = sorted(owner_fallbacks, key=lambda c: (c.completeness, c.uniqueness), reverse=True)[0]
            pk_candidate_names = [winner.column_name]
            winner.pk_candidate = True
            winner.pk_score = max(winner.pk_score, 0.75)
            winner.pk_confidence = winner.pk_score
            winner.pk_evidence.pk_candidate = True
            winner.pk_evidence.pk_score = winner.pk_score
            winner.pk_evidence.pk_confidence = winner.pk_confidence

    composite_pk_candidates = _infer_composite_pk_candidates(table_name, column_profiles, pk_candidate_names)
    
    # Table-level aggregates
    # FIXED: Correct row_count_estimate mapping from canonical JSON
    table_profile = _compute_table_profile(
        column_profiles,
        pk_candidate_names,
        row_count,
        composite_pk_candidates
    )
    
    # Profiling metadata
    profiling_metadata = ProfilingMetadata(
        profiled_at=datetime.now(),
        profiler_version=__version__,
        execution_time_ms=0.0,  # Updated by caller
        sample_based=sampling_info.get("is_sample", False),
        sample_size=sampling_info.get("sample_size"),
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


def _profile_column(
    col_data: Dict[str, Any],
    table_metadata: Dict[str, Any],
    table_name: str,
    table_column_names: Optional[set[str]] = None,
    duckdb_context: Optional[DuckDBProfileContext] = None,
) -> ColumnProfile:
    """
    Profile a single column from CanonicalTable data.
    
    Args:
        col_data: Column data from CanonicalTable
        table_metadata: Table-level metadata
        table_name: Table name
        
    Returns:
        ColumnProfile
    """
    
    # Extract column info
    column_id = col_data.get("column_id")
    original_name = col_data.get("original_name")
    normalized_name = str(col_data.get("normalized_name") or col_data.get("original_name") or "")
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
    
    if duckdb_context is not None:
        sample_values = duckdb_context.get_sample_values(normalized_name, limit=1000)

    physical_type, type_confidence = _normalize_physical_type(
        normalized_name,
        physical_type,
        sample_values,
        semantic_type,
    )
    semantic_type = _infer_semantic_type(normalized_name, physical_type, semantic_type)
    logical_type = _infer_logical_type(normalized_name, physical_type, semantic_type)

    table_column_names = table_column_names or set()

    # Compute statistics
    if duckdb_context is not None:
        statistics = duckdb_context.compute_column_statistics(normalized_name, physical_type)
    else:
        statistics = compute_statistics(
            sample_values=sample_values,
            physical_type=physical_type,
            existing_stats=existing_stats
        )

    if physical_type == PhysicalType.BOOLEAN and statistics.distinct_count > 2 and _all_whole_numbers(sample_values):
        physical_type = PhysicalType.INTEGER
        type_confidence = max(type_confidence, 0.85)
        semantic_type = _infer_semantic_type(normalized_name, physical_type, None)
        logical_type = _infer_logical_type(normalized_name, physical_type, semantic_type)
    
    # PK detection with suppression rules and table ownership
    pk_score, pk_evidence, is_pk_candidate = compute_pk_score(
        column_name=normalized_name,
        uniqueness_ratio=statistics.uniqueness_ratio,
        null_ratio=statistics.null_ratio,
        entropy_normalized=statistics.entropy_normalized,
        type_confidence=type_confidence,
        distinct_count=statistics.distinct_count,
        sample_size=statistics.total_count,
        physical_type=physical_type.name,
        sample_values=sample_values,
        table_name=table_name
    )

    table_identifier_match = _matches_table_identifier(normalized_name, table_name)
    owner_identifier_match = extract_column_root(normalized_name) == extract_table_root(table_name)
    if (
        not is_pk_candidate
        and table_identifier_match
        and _is_identifier_like(normalized_name, semantic_type)
        and physical_type in {PhysicalType.INTEGER, PhysicalType.UUID}
        and statistics.uniqueness_ratio >= 0.99
        and statistics.coverage_ratio >= 0.99
        and statistics.distinct_count >= 5
    ):
        pk_score = min(1.0, pk_score + 0.20)
        pk_evidence.pk_score = pk_score
        pk_evidence.pk_confidence = pk_score
        pk_evidence.positive_evidence.append("Table-aligned identifier")
        pk_evidence.reasons.append("Table-aligned identifier")
        is_pk_candidate = pk_score >= 0.70
        pk_evidence.pk_candidate = is_pk_candidate

    if (
        is_pk_candidate
        and _is_identifier_like(normalized_name, semantic_type)
        and not table_identifier_match
        and not owner_identifier_match
    ):
        pk_score = max(0.0, pk_score - 0.25)
        pk_evidence.pk_score = pk_score
        pk_evidence.pk_confidence = pk_score
        pk_evidence.negative_evidence.append(
            f"Identifier name does not align with table identity '{table_name}'"
        )
        pk_evidence.warnings.append(
            f"Identifier name does not align with table identity '{table_name}'"
        )
        is_pk_candidate = pk_score >= 0.70
        pk_evidence.pk_candidate = is_pk_candidate
    
    geo_profile = _parse_geo_profile(sample_values)
    if geo_profile:
        semantic_type = SemanticType.GEO_POINT
        logical_type = LogicalType.GEOSPATIAL

    temporal_pattern = _detect_temporal_pattern(normalized_name, table_column_names, sample_values)
    if temporal_pattern:
        semantic_type = SemanticType.TEMPORAL
        logical_type = LogicalType.TIMESTAMP

    audit_profile = _detect_audit_profile(normalized_name)
    if audit_profile:
        logical_type = LogicalType.AUDIT_REFERENCE
        semantic_type = SemanticType.IDENTIFIER
        if physical_type == PhysicalType.BOOLEAN or (physical_type == PhysicalType.UNKNOWN and _all_whole_numbers(sample_values)):
            physical_type = PhysicalType.INTEGER
            type_confidence = max(type_confidence, 0.95)
        pk_score = 0.0
        is_pk_candidate = False
        pk_evidence.pk_score = 0.0
        pk_evidence.pk_candidate = False
        pk_evidence.pk_confidence = 0.0
        if "Audit field suppressed for PK scoring" not in pk_evidence.negative_evidence:
            pk_evidence.negative_evidence.append("Audit field suppressed for PK scoring")

    # Quality flags
    quality_flags = detect_quality_flags(
        column_name=normalized_name,
        physical_type=physical_type,
        semantic_type=semantic_type,
        null_ratio=statistics.null_ratio,
        distinct_count=statistics.distinct_count,
        total_count=statistics.total_count,
        entropy_normalized=statistics.entropy_normalized,
        skewness=statistics.skewness,
        uniqueness_ratio=statistics.uniqueness_ratio,
        duplicate_ratio=statistics.duplicate_ratio,
        kurtosis=statistics.kurtosis,
        type_confidence=type_confidence,
        logical_type=logical_type,
        audit_profile=audit_profile,
        sample_values=sample_values,
    )
    
    quality_breakdown = _quality_breakdown(statistics, quality_flags)
    quality_score = _weighted_quality_score(quality_breakdown)
    
    # Classify cardinality
    cardinality_class = classify_cardinality(statistics.cardinality_ratio)
    profile_hints = _build_profile_hints(physical_type, semantic_type, logical_type)
    
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
        pk_candidate=is_pk_candidate,
        pk_score=pk_score,
        pk_confidence=pk_score,
        pk_evidence=pk_evidence,
        suppressed=pk_evidence.suppressed,
        suppression_reasons=pk_evidence.suppression_reasons,
        temporal_pattern=temporal_pattern,
        geo_profile=geo_profile,
        audit_profile=audit_profile,
        quality_flags=quality_flags,
        quality_score=quality_score,
        quality_breakdown=quality_breakdown,
        statistics=statistics,
        profile_hints=profile_hints,
        sample_values=sample_values[:10] if sample_values else None,
    )
    
    return column_profile


def _compute_table_profile(
    column_profiles: list,
    pk_candidate_names: list,
    row_count_estimate: int,
    composite_pk_candidates: Optional[list[list[str]]] = None,
) -> TableProfile:
    """
    Compute table-level profile aggregates.
    
    Args:
        column_profiles: List of ColumnProfile objects
        pk_candidate_names: List of PK candidate column names
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
        composite_pk_candidates=composite_pk_candidates or [],
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
