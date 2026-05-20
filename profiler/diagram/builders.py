"""Build diagram state and insight payloads from existing output artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PRIMARY_KEY = "PRIMARY_KEY"
FOREIGN_KEY = "FOREIGN_KEY"
COMPOSITE_KEY = "COMPOSITE_KEY"
AUDIT_REFERENCE = "AUDIT_REFERENCE"
ENUM_REFERENCE = "ENUM_REFERENCE"
DIMENSION_REFERENCE = "DIMENSION_REFERENCE"
TRANSACTION_REFERENCE = "TRANSACTION_REFERENCE"
SEMANTIC_ONLY = "SEMANTIC_ONLY"
INVALID_MATCH = "INVALID_MATCH"
SELF_REFERENCE = "SELF_REFERENCE"
BRIDGE_TABLE = "BRIDGE_TABLE"

TRUE_FK = "TRUE_FK"
SEMANTICALLY_RELATED = "SEMANTICALLY_RELATED"
SHARED_ENTITY_DOMAIN = "SHARED_ENTITY_DOMAIN"
POSSIBLE_REFERENCE = "POSSIBLE_REFERENCE"

DEFAULT_REL_CLASSES = {
    FOREIGN_KEY,
    TRANSACTION_REFERENCE,
    DIMENSION_REFERENCE,
    ENUM_REFERENCE,
    AUDIT_REFERENCE,
    SELF_REFERENCE,
    BRIDGE_TABLE,
    TRUE_FK,
}
REL_CLASS_RANK = {
    PRIMARY_KEY: 0,
    FOREIGN_KEY: 1,
    TRANSACTION_REFERENCE: 2,
    DIMENSION_REFERENCE: 3,
    ENUM_REFERENCE: 4,
    AUDIT_REFERENCE: 5,
    SELF_REFERENCE: 6,
    BRIDGE_TABLE: 7,
    COMPOSITE_KEY: 8,
    TRUE_FK: 0,
    SEMANTICALLY_RELATED: 9,
    SHARED_ENTITY_DOMAIN: 10,
    POSSIBLE_REFERENCE: 11,
    SEMANTIC_ONLY: 12,
    INVALID_MATCH: 13,
    "UNKNOWN": 9,
}

AUTO_TOP_K_SMALL = 50
AUTO_TOP_K_MEDIUM = 100
AUTO_TOP_K_LARGE = 200
AUTO_TOP_K_HUGE = 500


@dataclass
class TableIndex:
    table_case: dict[str, str]
    table_ids: dict[str, str]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_table_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def _auto_top_k(table_count: int, relationship_count: int) -> int:
    if relationship_count > 10000:
        return AUTO_TOP_K_HUGE
    if table_count < 50:
        return AUTO_TOP_K_SMALL
    if table_count <= 200:
        return AUTO_TOP_K_MEDIUM
    return AUTO_TOP_K_LARGE


def _ensure_table_index(tables: Iterable[str]) -> TableIndex:
    table_case: dict[str, str] = {}
    table_ids: dict[str, str] = {}

    for table in tables:
        if not table:
            continue
        key = _normalize_table_key(table)
        if key not in table_case:
            table_case[key] = table

    for key, name in table_case.items():
        table_ids[key] = name

    return TableIndex(table_case=table_case, table_ids=table_ids)


def _load_profiles(output_root: Path) -> dict[str, dict[str, Any]]:
    profiles_dir = output_root / "profiles"
    profiles: dict[str, dict[str, Any]] = {}
    if not profiles_dir.exists():
        return profiles

    for path in profiles_dir.glob("*.profile.json"):
        try:
            data = _read_json(path)
        except Exception:
            continue
        table_name = data.get("table_name") or path.stem.replace(".profile", "")
        profiles[table_name] = data

    return profiles


def _load_relationships(output_root: Path) -> list[dict[str, Any]]:
    rel_path = output_root / "relationships" / "relationships.json"
    if not rel_path.exists():
        return []
    data = _read_json(rel_path)
    if isinstance(data, dict):
        rels = data.get("relationships", [])
        if isinstance(rels, list):
            return rels
    return data if isinstance(data, list) else []


def _load_descriptions(output_root: Path) -> list[dict[str, Any]]:
    desc_path = output_root / "descriptions" / "descriptions.json"
    if not desc_path.exists():
        return []
    data = _read_json(desc_path)
    return data if isinstance(data, list) else []


def _load_lcil(output_root: Path) -> list[dict[str, Any]]:
    lcil_path = output_root / "low_cardinality" / "low_cardinality_insights.json"
    if not lcil_path.exists():
        return []
    data = _read_json(lcil_path)
    insights = data.get("insights") if isinstance(data, dict) else None
    return insights if isinstance(insights, list) else []


def _description_map(items: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    mapping: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        table = item.get("table_name")
        column = item.get("column_name")
        if not table or not column:
            continue
        mapping[(table.lower(), column.lower())] = item
    return mapping


def _lcil_map(items: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    mapping: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        table = item.get("table_name")
        column = item.get("column_name")
        if not table or not column:
            continue
        mapping[(table.lower(), column.lower())] = item
    return mapping


def _infer_module(table_name: str) -> str:
    lowered = table_name.lower()
    for prefix in ("sales_", "warehouse_", "purchasing_", "application_"):
        if lowered.startswith(prefix):
            return prefix.rstrip("_")
    return "core"


def _collect_tables(profiles: dict[str, Any], relationships: list[dict[str, Any]]) -> list[str]:
    tables = set(profiles.keys())
    for rel in relationships:
        fk_table = rel.get("fk_table")
        pk_table = rel.get("pk_table")
        if fk_table:
            tables.add(fk_table)
        if pk_table:
            tables.add(pk_table)
    return sorted(tables, key=lambda t: t.lower())


def _relationship_class(value: Any) -> str:
    return str(value or "UNKNOWN").upper()


def _relationship_confidence(rel: dict[str, Any]) -> float:
    return float(rel.get("confidence_score") or rel.get("confidence") or 0.0)


def _relationship_key(rel: dict[str, Any]) -> tuple:
    return (
        rel.get("fk_table", "").lower(),
        rel.get("fk_column", "").lower(),
        rel.get("pk_table", "").lower(),
        rel.get("pk_column", "").lower(),
        _relationship_class(rel.get("relationship_class")),
    )


def _dedupe_relationships(relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple, dict[str, Any]] = {}
    for rel in relationships:
        key = _relationship_key(rel)
        if key not in best or _relationship_confidence(rel) > _relationship_confidence(best[key]):
            best[key] = rel
    return list(best.values())


def _filter_relationships(
    relationships: list[dict[str, Any]],
    min_confidence: float,
    relationship_classes: set[str],
    top_k: int | None,
    table_count: int,
) -> list[dict[str, Any]]:
    filtered = [
        rel for rel in relationships
        if _relationship_confidence(rel) >= min_confidence
        and _relationship_class(rel.get("relationship_class")) in relationship_classes
    ]
    filtered.sort(
        key=lambda r: (
            REL_CLASS_RANK.get(_relationship_class(r.get("relationship_class")), 9),
            -_relationship_confidence(r),
            (r.get("fk_table") or "").lower(),
            (r.get("pk_table") or "").lower(),
        )
    )

    if top_k is None:
        top_k = _auto_top_k(table_count, len(filtered))

    if top_k and top_k > 0:
        filtered = filtered[:top_k]

    return filtered


def _column_summary(col: dict[str, Any], pk_cols: set[str], fk_cols: set[str]) -> dict[str, Any]:
    col_name = col.get("column_name") or col.get("name")
    if not col_name:
        return {}
    return {
        "name": col_name,
        "type": col.get("physical_type") or col.get("type") or "unknown",
        "pk": col_name.lower() in pk_cols,
        "fk": col_name.lower() in fk_cols,
        "quality": col.get("quality_score", 0.0),
        "cardinality": col.get("cardinality_class") or col.get("cardinality") or "unknown",
    }


def _build_column_insight(
    table: str,
    column: dict[str, Any],
    desc_map: dict[tuple[str, str], dict[str, Any]],
    lcil_map: dict[tuple[str, str], dict[str, Any]],
    fk_confidence: float,
    relationships: list[str],
) -> dict[str, Any]:
    col_name = column.get("column_name") or column.get("name") or ""
    key = (table.lower(), col_name.lower())
    desc = desc_map.get(key, {})
    lcil = lcil_map.get(key, {})

    stats = column.get("statistics") or {}
    top_values_raw = stats.get("top_values") or []
    top_values = []
    for item in top_values_raw:
        if isinstance(item, (list, tuple)) and item:
            top_values.append(str(item[0]))
        elif item:
            top_values.append(str(item))
    top_values = top_values[:5]

    semantic = desc.get("data_domain") or column.get("semantic_type") or column.get("logical_type") or "UNKNOWN"

    business_meaning = desc.get("business_purpose") or desc.get("semantic_description") or ""

    return {
        "table": table,
        "column": col_name,
        "type": column.get("physical_type") or "unknown",
        "semantic": semantic,
        "quality": column.get("quality_score", 0.0),
        "cardinality": column.get("cardinality_class") or "unknown",
        "null_ratio": stats.get("null_ratio", 0.0),
        "pk_confidence": column.get("pk_confidence", 0.0),
        "fk_confidence": fk_confidence,
        "relationships": relationships,
        "top_values": top_values,
        "business_meaning": business_meaning,
        "ontology_tags": lcil.get("ontology_tags") or [],
    }


def build_diagram_state(
    output_base: str | Path = "output",
    min_confidence: float = 0.5,
    top_k: int | None = None,
    relationship_classes: Iterable[str] | None = None,
) -> dict[str, Any]:
    output_root = Path(output_base)
    profiles = _load_profiles(output_root)
    relationships = _dedupe_relationships(_load_relationships(output_root))

    classes = {c.upper() for c in relationship_classes} if relationship_classes else DEFAULT_REL_CLASSES

    tables = _collect_tables(profiles, relationships)
    table_index = _ensure_table_index(tables)

    filtered_relationships = _filter_relationships(
        relationships,
        min_confidence,
        classes,
        top_k,
        len(tables),
    )

    fk_columns: dict[str, set[str]] = {}
    pk_columns: dict[str, set[str]] = {}
    for rel in filtered_relationships:
        fk_table = rel.get("fk_table")
        pk_table = rel.get("pk_table")
        fk_col = rel.get("fk_column")
        pk_col = rel.get("pk_column")
        if fk_table and fk_col:
            fk_columns.setdefault(fk_table.lower(), set()).add(fk_col.lower())
        if pk_table and pk_col:
            pk_columns.setdefault(pk_table.lower(), set()).add(pk_col.lower())

    nodes: list[dict[str, Any]] = []
    for table in tables:
        profile = profiles.get(table) or {}
        table_profile = profile.get("table_profile") or {}
        cols = profile.get("columns") or []

        pk_cols = set()
        for name in table_profile.get("pk_candidates") or []:
            pk_cols.add(str(name).lower())
        pk_cols.update(pk_columns.get(table.lower(), set()))

        fk_cols = fk_columns.get(table.lower(), set())

        columns = [
            _column_summary(c, pk_cols, fk_cols)
            for c in cols
            if c.get("column_name") or c.get("name")
        ]

        row_count = table_profile.get("row_count_estimate")
        quality = table_profile.get("quality_score")
        if quality is None:
            qualities = [c.get("quality_score", 0.0) for c in cols]
            quality = sum(qualities) / len(qualities) if qualities else 0.0

        nodes.append(
            {
                "id": table_index.table_ids[_normalize_table_key(table)],
                "name": table_index.table_ids[_normalize_table_key(table)],
                "module": _infer_module(table),
                "collapsed": True,
                "row_count": row_count or 0,
                "quality": round(float(quality or 0.0), 4),
                "column_count": len(cols),
                "pk_columns": sorted(pk_cols),
                "fk_columns": sorted(fk_cols),
                "columns": [c for c in columns if c],
            }
        )

    edges: list[dict[str, Any]] = []
    for rel in filtered_relationships:
        fk_table = rel.get("fk_table")
        pk_table = rel.get("pk_table")
        fk_col = rel.get("fk_column")
        pk_col = rel.get("pk_column")
        if not (fk_table and pk_table and fk_col and pk_col):
            continue
        rel_class = _relationship_class(rel.get("relationship_class"))
        edge_id = f"{fk_table}.{fk_col}->{pk_table}.{pk_col}:{rel_class}"
        edges.append(
            {
                "id": edge_id,
                "source": table_index.table_ids[_normalize_table_key(fk_table)],
                "target": table_index.table_ids[_normalize_table_key(pk_table)],
                "source_column": fk_col,
                "target_column": pk_col,
                "relationship_class": rel_class,
                "confidence": _relationship_confidence(rel),
                "containment_ratio": float(rel.get("containment_ratio") or 0.0),
                "semantic_similarity": float(rel.get("semantic_similarity") or 0.0),
                "reasoning": rel.get("reasoning") or [],
            }
        )

    metrics = {
        "table_count": len(nodes),
        "relationship_count": len(edges),
        "min_confidence": min_confidence,
        "relationship_classes": sorted(classes),
    }

    return {
        "nodes": nodes,
        "edges": edges,
        "metrics": metrics,
    }


def get_table_detail(
    table_id: str,
    output_base: str | Path = "output",
) -> dict[str, Any]:
    output_root = Path(output_base)
    profiles = _load_profiles(output_root)
    descriptions = _description_map(_load_descriptions(output_root))
    lcil = _lcil_map(_load_lcil(output_root))

    profile = profiles.get(table_id)
    if profile is None:
        # Try case-insensitive lookup
        for key, value in profiles.items():
            if key.lower() == table_id.lower():
                profile = value
                table_id = key
                break

    if profile is None:
        return {"error": f"Table not found: {table_id}"}

    relationships = _load_relationships(output_root)
    fk_conf = _fk_confidence_by_column(relationships)
    rel_map = _relationships_by_column(relationships)

    columns = profile.get("columns") or []
    column_insights = []
    for c in columns:
        col_name = str(c.get("column_name") or "")
        if not col_name:
            continue
        key = (table_id.lower(), col_name.lower())
        column_insights.append(
            _build_column_insight(
                table_id,
                c,
                descriptions,
                lcil,
                fk_conf.get(key, 0.0),
                rel_map.get(key, []),
            )
        )

    table_profile = profile.get("table_profile") or {}
    return {
        "table": table_id,
        "row_count": table_profile.get("row_count_estimate") or 0,
        "quality": table_profile.get("quality_score") or 0.0,
        "pk_columns": table_profile.get("pk_candidates") or [],
        "columns": column_insights,
    }


def _fk_confidence_by_column(relationships: list[dict[str, Any]]) -> dict[tuple[str, str], float]:
    scores: dict[tuple[str, str], float] = {}
    for rel in relationships:
        fk_table = rel.get("fk_table")
        fk_col = rel.get("fk_column")
        if not fk_table or not fk_col:
            continue
        score = _relationship_confidence(rel)
        key = (fk_table.lower(), fk_col.lower())
        scores[key] = max(scores.get(key, 0.0), score)
    return scores


def _relationships_by_column(relationships: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    mapping: dict[tuple[str, str], list[str]] = {}
    for rel in relationships:
        fk_table = rel.get("fk_table")
        fk_col = rel.get("fk_column")
        pk_table = rel.get("pk_table")
        pk_col = rel.get("pk_column")
        if not (fk_table and fk_col and pk_table and pk_col):
            continue
        fk_key = (fk_table.lower(), fk_col.lower())
        pk_key = (pk_table.lower(), pk_col.lower())
        mapping.setdefault(fk_key, []).append(f"{pk_table}.{pk_col}")
        mapping.setdefault(pk_key, []).append(f"{fk_table}.{fk_col}")
    for key, values in mapping.items():
        mapping[key] = sorted(set(values))
    return mapping


def get_column_insight(
    column_id: str,
    output_base: str | Path = "output",
) -> dict[str, Any]:
    output_root = Path(output_base)
    profiles = _load_profiles(output_root)
    descriptions = _description_map(_load_descriptions(output_root))
    lcil = _lcil_map(_load_lcil(output_root))

    table_name, column_name = _split_column_id(column_id)
    if not table_name or not column_name:
        return {"error": "Invalid column id. Use table.column"}

    table_key = None
    for name in profiles.keys():
        if name.lower() == table_name.lower():
            table_key = name
            break

    if not table_key:
        return {"error": f"Table not found: {table_name}"}

    profile = profiles.get(table_key) or {}
    columns = profile.get("columns") or []

    relationships = _load_relationships(output_root)
    fk_conf = _fk_confidence_by_column(relationships)
    rel_map = _relationships_by_column(relationships)

    for col in columns:
        col_name = col.get("column_name")
        if col_name and col_name.lower() == column_name.lower():
            key = (table_key.lower(), col_name.lower())
            return _build_column_insight(
                table_key,
                col,
                descriptions,
                lcil,
                fk_conf.get(key, 0.0),
                rel_map.get(key, []),
            )

    return {"error": f"Column not found: {column_id}"}


def get_relationship_detail(
    edge_id: str,
    output_base: str | Path = "output",
) -> dict[str, Any]:
    output_root = Path(output_base)
    relationships = _load_relationships(output_root)

    for rel in relationships:
        fk_table = rel.get("fk_table")
        pk_table = rel.get("pk_table")
        fk_col = rel.get("fk_column")
        pk_col = rel.get("pk_column")
        if not (fk_table and pk_table and fk_col and pk_col):
            continue
        rel_class = _relationship_class(rel.get("relationship_class"))
        candidate_id = f"{fk_table}.{fk_col}->{pk_table}.{pk_col}:{rel_class}"
        if candidate_id == edge_id:
            return {
                "id": candidate_id,
                "relationship_class": rel_class,
                "confidence": _relationship_confidence(rel),
                "containment_ratio": float(rel.get("containment_ratio") or 0.0),
                "semantic_similarity": float(rel.get("semantic_similarity") or 0.0),
                "reasoning": rel.get("reasoning") or [],
                "fk_table": fk_table,
                "fk_column": fk_col,
                "pk_table": pk_table,
                "pk_column": pk_col,
            }

    return {"error": f"Relationship not found: {edge_id}"}


def export_dbml_schema(
    output_base: str | Path = "output",
    min_confidence: float = 0.5,
    top_k: int | None = None,
) -> dict[str, Any]:
    from profiler.erve import ERVEConfig, ERVEEngine

    output_root = Path(output_base)
    engine = ERVEEngine(
        config=ERVEConfig(
            relationships_path=output_root / "relationships" / "relationships.json",
            output_base=output_root,
            min_confidence=min_confidence,
            top_k=top_k,
        )
    )
    result = engine.generate_dbml()
    return {
        "path": result["outputs"]["dbml"],
        "tables": result.get("tables"),
        "true_fk_relationships": result.get("true_fk_relationships"),
    }


def _split_column_id(column_id: str) -> tuple[str | None, str | None]:
    if not column_id:
        return None, None
    if ":" in column_id:
        table, column = column_id.split(":", 1)
        return table, column
    if "." in column_id:
        table, column = column_id.split(".", 1)
        return table, column
    return None, None
