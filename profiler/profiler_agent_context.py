from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PREFIX_RE = re.compile(r"^(sales_|application_|warehouse_|purchasing_)", re.IGNORECASE)
AUDIT_RE = re.compile(r"(createdby|modifiedby|lasteditedby|deletedby|approvedby|reviewedby|editorid)$", re.IGNORECASE)
TEMPORAL_RE = re.compile(r"(validfrom|validto|effectivefrom|effectiveto)$", re.IGNORECASE)
MEASURE_RE = re.compile(r"(amount|price|cost|quantity|count|total|rate|population)$", re.IGNORECASE)
GEO_RE = re.compile(r"(location|latitude|longitude|geom|polygon|point)$", re.IGNORECASE)
SCD_RE = re.compile(r"(validfrom|validto)$", re.IGNORECASE)
IDENTIFIER_RE = re.compile(r"(id|key)$", re.IGNORECASE)


DOMAIN_BY_ROOT = {
    "city": "Geography",
    "country": "Geography",
    "stateprovince": "Geography",
    "invoice": "Sales",
    "order": "Sales",
    "transaction": "Sales",
    "customer": "Sales",
    "supplier": "Purchasing",
    "purchaseorder": "Purchasing",
    "stockitem": "Warehouse",
    "stockgroup": "Warehouse",
    "deliverymethod": "Operations",
    "paymentmethod": "Operations",
    "transactiontype": "Operations",
    "person": "Reference",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(v: str) -> str:
    return (v or "").strip().lower()


def _singularize(name: str) -> str:
    n = _norm(name)
    if n.endswith("ies") and len(n) > 3:
        return n[:-3] + "y"
    if n.endswith("ses") and len(n) > 3:
        return n[:-2]
    if n.endswith("s") and not n.endswith("ss") and len(n) > 2:
        return n[:-1]
    return n


def _table_root(table_name: str) -> str:
    base = _norm(table_name)
    base = PREFIX_RE.sub("", base)
    return _singularize(base)


def _column_root(column_name: str) -> str:
    col = _norm(column_name)
    for suffix in ("_id", "id", "_key", "key"):
        if col.endswith(suffix):
            col = col[: -len(suffix)]
            break
    return _singularize(col)


def _column_map(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(c.get("column_name")): c for c in profile.get("columns", [])}


def _sample_values(canonical_table: dict[str, Any], column_name: str) -> list[Any]:
    for col in canonical_table.get("columns", []):
        if col.get("original_name") == column_name or col.get("normalized_name") == column_name:
            return col.get("sample_values", []) or []
    return []


def _nonnull_distinct(values: list[Any]) -> set[str]:
    out: set[str] = set()
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s == "":
            continue
        out.add(s)
    return out


def _subset_ratio(left_values: list[Any], right_values: list[Any]) -> float:
    left = _nonnull_distinct(left_values)
    right = _nonnull_distinct(right_values)
    if not left:
        return 0.0
    return len(left & right) / len(left)


def _classify_column(table_root: str, table_name: str, column: dict[str, Any], col_map: dict[str, dict[str, Any]]) -> str:
    name = str(column.get("column_name", ""))
    n = _norm(name)
    stats = column.get("statistics", {}) or {}
    distinct_count = int(stats.get("distinct_count", 0) or 0)
    uniqueness = float(stats.get("uniqueness_ratio", 0.0) or 0.0)

    if AUDIT_RE.search(n):
        return "AUDIT_REFERENCE"
    if TEMPORAL_RE.search(n):
        return "SCD_COLUMN"
    if GEO_RE.search(n):
        return "GEO"
    if MEASURE_RE.search(n):
        return "MEASURE"

    # Mark likely bridge keys first for common line-item tables.
    if any(token in _norm(table_name) for token in ["line", "bridge", "mapping"]):
        if IDENTIFIER_RE.search(n):
            return "BRIDGE_KEY"

    if IDENTIFIER_RE.search(n):
        c_root = _column_root(n)
        if c_root == table_root:
            return "PRIMARY_OWNER"
        if c_root in {"deliverymethod", "paymentmethod", "suppliercategory", "customercategory", "transactiontype"}:
            return "ENUM_REFERENCE"
        if c_root in {"person", "user", "employee"}:
            return "AUDIT_REFERENCE" if AUDIT_RE.search(n) else "FOREIGN_REFERENCE"
        if uniqueness < 0.95 or distinct_count < 20:
            return "FOREIGN_REFERENCE"
        return "FOREIGN_REFERENCE"

    physical = _norm(str(column.get("physical_type", "")))
    if physical in {"date", "datetime", "timestamp"}:
        return "TEMPORAL_COLUMN"
    return "DESCRIPTIVE"


@dataclass
class TableContext:
    table_name: str
    table_root: str
    domain: str
    pk_candidates: list[dict[str, Any]]
    composite_candidates: list[list[str]]
    fk_hints: list[dict[str, Any]]
    audit_refs: list[str]
    enum_refs: list[str]
    bridge_type: str
    temporal_pattern: dict[str, Any]
    invalid_targets: list[dict[str, Any]]
    domain_cluster: str
    semantic_neighbors: list[str]


def build_profiler_context(output_base: str = "output") -> dict[str, Any]:
    base = Path(output_base)
    canonical_dir = base / "canonical"
    profiles_dir = base / "profiles"
    descriptions_path = base / "descriptions" / "descriptions.json"
    output_path = base / "profiler_context.json"

    profiles: dict[str, dict[str, Any]] = {}
    for p in sorted(profiles_dir.glob("*.profile.json")):
        obj = json.loads(p.read_text(encoding="utf-8"))
        t = obj.get("table_name")
        if t:
            profiles[str(t)] = obj

    canonical: dict[str, dict[str, Any]] = {}
    for p in sorted(canonical_dir.glob("*.canonical.json")):
        obj = json.loads(p.read_text(encoding="utf-8"))
        t = obj.get("table_name")
        if t:
            canonical[str(t)] = obj

    descriptions = []
    if descriptions_path.exists():
        loaded = json.loads(descriptions_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            descriptions = loaded

    table_roots = {table: _table_root(table) for table in profiles.keys()}
    table_domains = {table: DOMAIN_BY_ROOT.get(root, root.title()) for table, root in table_roots.items()}

    owner_columns: dict[str, list[str]] = defaultdict(list)
    table_roles: dict[str, dict[str, str]] = {}

    for table, profile in profiles.items():
        root = table_roots[table]
        roles: dict[str, str] = {}
        cmap = _column_map(profile)
        for col in profile.get("columns", []):
            col_name = str(col.get("column_name", ""))
            role = _classify_column(root, table, col, cmap)
            roles[col_name] = role
            if role == "PRIMARY_OWNER":
                owner_columns[table].append(col_name)
        table_roles[table] = roles

    # Ensure explicit PK candidates are always considered owner when root matches.
    for table, profile in profiles.items():
        root = table_roots[table]
        pk_candidates = profile.get("table_profile", {}).get("pk_candidates", []) or []
        for col_name in pk_candidates:
            if _column_root(str(col_name)) == root:
                if col_name not in owner_columns[table]:
                    owner_columns[table].append(col_name)
                table_roles[table][str(col_name)] = "PRIMARY_OWNER"

    fk_hints_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    invalid_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for src_table, profile in profiles.items():
        src_domain = table_domains[src_table]
        src_canon = canonical.get(src_table, {})
        for col in profile.get("columns", []):
            src_col = str(col.get("column_name", ""))
            src_role = table_roles[src_table].get(src_col, "")
            if src_role not in {"FOREIGN_REFERENCE", "ENUM_REFERENCE", "BRIDGE_KEY", "AUDIT_REFERENCE"}:
                continue

            src_type = _norm(str(col.get("physical_type", "")))
            src_stats = col.get("statistics", {}) or {}
            src_uniq = float(src_stats.get("uniqueness_ratio", 0.0) or 0.0)
            src_values = _sample_values(src_canon, src_col)

            for tgt_table, tgt_profile in profiles.items():
                if tgt_table == src_table:
                    continue

                tgt_domain = table_domains[tgt_table]
                tgt_canon = canonical.get(tgt_table, {})
                for tgt_col in owner_columns.get(tgt_table, []):
                    tgt_info = _column_map(tgt_profile).get(tgt_col, {})
                    tgt_type = _norm(str(tgt_info.get("physical_type", "")))
                    if src_type and tgt_type and src_type != tgt_type:
                        continue

                    tgt_values = _sample_values(tgt_canon, tgt_col)
                    subset = _subset_ratio(src_values, tgt_values)
                    if subset <= 0.0:
                        continue

                    entity_match = _column_root(src_col) == _column_root(tgt_col)
                    same_domain = src_domain == tgt_domain
                    confidence = 0.0
                    confidence += 0.35 if entity_match else 0.05
                    confidence += 0.25 * min(1.0, subset)
                    confidence += 0.20 if same_domain else 0.0
                    confidence += 0.10 if src_uniq < 0.95 else 0.0
                    confidence += 0.10 if src_role == "ENUM_REFERENCE" else 0.0

                    if not same_domain and not entity_match:
                        invalid_by_table[src_table].append(
                            {
                                "source_column": src_col,
                                "target_table": tgt_table,
                                "target_column": tgt_col,
                                "reason": "entity_mismatch_or_parallel_dimension",
                            }
                        )
                        continue

                    fk_hints_by_table[src_table].append(
                        {
                            "source_table": src_table,
                            "source_column": src_col,
                            "target_table": tgt_table,
                            "target_column": tgt_col,
                            "confidence": round(min(1.0, confidence), 4),
                            "reason": "ownership+subset+type",
                        }
                    )

    # Composite key suggestions and bridge detection.
    table_contexts: list[TableContext] = []
    for table, profile in profiles.items():
        roles = table_roles[table]
        id_columns = [c for c, r in roles.items() if r in {"FOREIGN_REFERENCE", "ENUM_REFERENCE", "BRIDGE_KEY"}]
        descriptive_count = sum(1 for r in roles.values() if r == "DESCRIPTIVE")

        composite_candidates: list[list[str]] = []
        if len(id_columns) >= 2:
            for i in range(min(len(id_columns), 4)):
                for j in range(i + 1, min(len(id_columns), 4)):
                    composite_candidates.append([id_columns[i], id_columns[j]])

        bridge_type = "BRIDGE_TABLE" if len(id_columns) >= 2 and descriptive_count <= 2 else "NONE"

        audit_refs = [c for c, r in roles.items() if r == "AUDIT_REFERENCE"]
        enum_refs = [c for c, r in roles.items() if r == "ENUM_REFERENCE"]
        temporal_cols = [c for c, r in roles.items() if r in {"SCD_COLUMN", "TEMPORAL_COLUMN"}]

        temporal_pattern = {
            "scd2": any(SCD_RE.search(_norm(c)) for c in temporal_cols),
            "effective_dating": any(_norm(c) in {"effectivefrom", "effectiveto"} for c in temporal_cols),
            "open_ended": False,
            "columns": temporal_cols,
        }

        # SCD open-ended check from canonical values.
        canon = canonical.get(table, {})
        valid_to_vals = []
        for c in temporal_cols:
            if _norm(c) == "validto":
                valid_to_vals.extend(_sample_values(canon, c))
        if any("9999" in str(v) for v in valid_to_vals if v is not None):
            temporal_pattern["open_ended"] = True

        profile_pk = profile.get("table_profile", {}).get("pk_candidates", []) or []
        pk_candidates = []
        for col in profile_pk:
            cmeta = _column_map(profile).get(col, {})
            cstats = cmeta.get("statistics", {}) or {}
            ownership_score = 1.0 if _column_root(str(col)) == table_roots[table] else 0.0
            pk_score = float(cmeta.get("pk_confidence", cmeta.get("pk_score", 0.0)) or 0.0)
            pk_candidates.append(
                {
                    "column": col,
                    "pk_score": round(pk_score, 4),
                    "ownership_score": ownership_score,
                    "distinct_count": int(cstats.get("distinct_count", 0) or 0),
                }
            )

        same_domain_neighbors = [t for t, d in table_domains.items() if t != table and d == table_domains[table]]

        table_contexts.append(
            TableContext(
                table_name=table,
                table_root=table_roots[table],
                domain=table_domains[table],
                pk_candidates=pk_candidates,
                composite_candidates=composite_candidates,
                fk_hints=sorted(fk_hints_by_table.get(table, []), key=lambda x: x["confidence"], reverse=True)[:30],
                audit_refs=audit_refs,
                enum_refs=enum_refs,
                bridge_type=bridge_type,
                temporal_pattern=temporal_pattern,
                invalid_targets=invalid_by_table.get(table, [])[:30],
                domain_cluster=table_domains[table],
                semantic_neighbors=same_domain_neighbors[:10],
            )
        )

    payload = {
        "generated_at": _now(),
        "input": {
            "canonical_dir": str(canonical_dir),
            "profiles_dir": str(profiles_dir),
            "descriptions_file": str(descriptions_path),
        },
        "tables": [
            {
                "table_name": t.table_name,
                "table_root": t.table_root,
                "domain": t.domain,
                "pk_candidates": t.pk_candidates,
                "composite_candidates": t.composite_candidates,
                "fk_hints": t.fk_hints,
                "audit_refs": t.audit_refs,
                "enum_refs": t.enum_refs,
                "bridge_type": t.bridge_type,
                "temporal_pattern": t.temporal_pattern,
                "invalid_targets": t.invalid_targets,
                "domain_cluster": t.domain_cluster,
                "semantic_neighbors": t.semantic_neighbors,
                "column_roles": table_roles[t.table_name],
            }
            for t in table_contexts
        ],
        "invalid_edges": [
            {
                "source_table": t.table_name,
                "source_column": item["source_column"],
                "target_table": item["target_table"],
                "target_column": item["target_column"],
                "reason": item["reason"],
            }
            for t in table_contexts
            for item in t.invalid_targets
        ],
    }

    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
