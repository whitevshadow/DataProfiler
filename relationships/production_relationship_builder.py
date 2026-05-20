"""
Production-grade relationship builder.

Consumes profiler outputs plus canonical samples and emits a business-valid
relationship graph with explicit PK/FK ownership reasoning, composite key
support, audit references, invalid match filtering, and ERD/DBML artifacts.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TABLE_PREFIXES = ("sales_", "application_", "warehouse_", "purchasing_")
AUDIT_PATTERNS = (
    "createdby",
    "modifiedby",
    "lasteditedby",
    "editedby",
    "approvedby",
    "deletedby",
    "reviewedby",
    "insertedby",
    "updatedby",
    "userid",
    "editorid",
    "creatorid",
)
SELF_REFERENCE_PATTERNS = (
    "managerid",
    "parentid",
    "parentcustomerid",
    "billtocustomerid",
)
TEMPORAL_COMPONENT_PATTERNS = (
    "validfrom",
    "validto",
    "effectivefrom",
    "effectiveto",
    "version",
    "sequence",
    "sequenceno",
    "sequencenumber",
    "lineid",
    "orderlineid",
    "invoicelineid",
    "purchaseorderlineid",
)
MUTABLE_PATTERNS = ("phone", "email", "website", "postal", "address")
MEASURE_PATTERNS = ("price", "amount", "cost", "population", "count", "percentage", "quantity", "rate", "tax")
ENUM_ENTITY_HINTS = ("method", "type", "category", "group", "color", "package")
TRANSACTION_ROOTS = {"invoice", "order", "purchaseorder", "transaction", "orderline", "invoiceline", "purchaseorderline"}
ACCEPTED_EDGE_CLASSES = {
    "FOREIGN_KEY",
    "AUDIT_REFERENCE",
    "ENUM_REFERENCE",
    "DIMENSION_REFERENCE",
    "TRANSACTION_REFERENCE",
    "SELF_REFERENCE",
}


@dataclass
class ColumnContext:
    table_name: str
    table_root: str
    column_name: str
    profile: dict[str, Any]
    root: str
    is_identifier: bool
    is_audit: bool
    is_temporal: bool
    is_measure: bool
    is_text: bool
    coverage_ratio: float
    uniqueness_ratio: float
    entropy: float
    distinct_count: int
    non_null_count: int
    total_count: int
    physical_type: str
    semantic_type: str
    logical_type: str
    sample_values: list[Any]


class ProductionRelationshipBuilder:
    def __init__(self, output_base: str | Path = "output") -> None:
        self.output_base = Path(output_base)
        self.profiles_dir = self.output_base / "profiles"
        self.canonical_dir = self.output_base / "canonical"
        self.relationships_dir = self.output_base / "relationships"
        self.erd_dir = self.output_base / "erd"
        self.graph_dir = self.output_base / "graph"
        self.descriptions_path = self.output_base / "descriptions" / "descriptions.json"

        self.profiles: dict[str, dict[str, Any]] = {}
        self.canonicals: dict[str, dict[str, Any]] = {}
        self.descriptions: dict[tuple[str, str], dict[str, Any]] = {}
        self.table_roots: dict[str, str] = {}
        self.root_to_tables: dict[str, list[str]] = defaultdict(list)
        self.columns: dict[tuple[str, str], ColumnContext] = {}
        self.primary_keys: dict[str, dict[str, Any]] = {}
        self.composite_keys: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> dict[str, Any]:
        self._load_inputs()
        self._discover_primary_keys()

        fk_edges: list[dict[str, Any]] = []
        audit_refs: list[dict[str, Any]] = []
        enum_refs: list[dict[str, Any]] = []
        self_refs: list[dict[str, Any]] = []
        invalid_matches: list[dict[str, Any]] = []

        for ctx in self.columns.values():
            if self._is_primary_key_column(ctx.table_name, ctx.column_name):
                continue
            if not ctx.is_identifier and not ctx.is_audit:
                continue

            if ctx.is_audit:
                audit_rel = self._build_audit_reference(ctx)
                if audit_rel:
                    audit_refs.append(audit_rel)
                continue

            self_rel = self._build_self_reference(ctx)
            if self_rel:
                self_refs.append(self_rel)
                continue

            edge, rejected = self._build_best_fk(ctx)
            invalid_matches.extend(rejected)
            if edge:
                fk_edges.append(edge)

        bridge_tables = self._detect_bridge_tables(fk_edges)
        enum_refs.extend(self._promote_enum_refs(fk_edges))

        relationships = self._build_relationship_records(
            fk_edges=fk_edges,
            audit_refs=audit_refs,
            enum_refs=enum_refs,
            self_refs=self_refs,
            invalid_matches=invalid_matches,
            bridge_tables=bridge_tables,
        )
        erd_edges = [rel for rel in relationships if rel["relationship_class"] in ACCEPTED_EDGE_CLASSES]

        payload = {
            "metadata": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "builder": "production_relationship_builder",
                "tables_analyzed": len(self.profiles),
                "columns_analyzed": len(self.columns),
                "validated_relationships": len(erd_edges),
                "primary_keys": len(self.primary_keys),
                "composite_primary_keys": len(self.composite_keys),
                "invalid_matches": len(invalid_matches),
            },
            "pk": sorted(self.primary_keys.values(), key=lambda item: item["table"]),
            "composite_pk": sorted(self.composite_keys.values(), key=lambda item: item["table"]),
            "fk": sorted(fk_edges, key=lambda item: (item["fk_table"].lower(), item["fk_column"].lower(), item["pk_table"].lower())),
            "audit_refs": sorted(audit_refs, key=lambda item: (item["fk_table"].lower(), item["fk_column"].lower())),
            "enum_refs": sorted(enum_refs, key=lambda item: (item["fk_table"].lower(), item["fk_column"].lower())),
            "bridge_tables": sorted(bridge_tables, key=lambda item: item["table"].lower()),
            "invalid_matches": sorted(invalid_matches, key=lambda item: (item["fk_table"].lower(), item["fk_column"].lower(), item["pk_table"].lower(), item["pk_column"].lower())),
            "self_refs": sorted(self_refs, key=lambda item: (item["fk_table"].lower(), item["fk_column"].lower())),
            "erd_edges": erd_edges,
            "relationships": relationships,
        }

        self._write_outputs(payload)
        return payload

    # ------------------------------------------------------------------
    # Input loading
    # ------------------------------------------------------------------

    def _load_inputs(self) -> None:
        for path in sorted(self.profiles_dir.glob("*.profile.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            table_name = data["table_name"]
            self.profiles[table_name] = data

        for path in sorted(self.canonical_dir.glob("*.canonical.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            table_name = data["table_name"]
            self.canonicals[table_name] = data

        if self.descriptions_path.exists():
            try:
                descriptions = json.loads(self.descriptions_path.read_text(encoding="utf-8"))
                if isinstance(descriptions, list):
                    for item in descriptions:
                        table = item.get("table_name")
                        column = item.get("column_name")
                        if table and column:
                            self.descriptions[(str(table).lower(), str(column).lower())] = item
            except Exception:
                pass

        for table_name, profile in self.profiles.items():
            table_root = _table_root(table_name)
            self.table_roots[table_name] = table_root
            self.root_to_tables[table_root].append(table_name)
            for column in profile.get("columns", []):
                ctx = self._make_column_context(table_name, table_root, column)
                self.columns[(table_name, ctx.column_name)] = ctx

    def _make_column_context(self, table_name: str, table_root: str, column: dict[str, Any]) -> ColumnContext:
        stats = column.get("statistics") or {}
        hints = column.get("profile_hints") or {}
        column_name = str(column.get("column_name") or "").lower()
        root = _column_root(column_name, set(self.root_to_tables.keys()))
        return ColumnContext(
            table_name=table_name,
            table_root=table_root,
            column_name=column_name,
            profile=column,
            root=root,
            is_identifier=bool(hints.get("is_identifier")) or str(column.get("semantic_type")) == "identifier",
            is_audit=bool(hints.get("is_audit")) or str(column.get("logical_type")) == "audit_reference",
            is_temporal=bool(hints.get("is_temporal")) or "date" in column_name or "time" in column_name,
            is_measure=bool(hints.get("is_measure")) or _name_contains_measure_token(column_name),
            is_text=bool(hints.get("is_text")),
            coverage_ratio=float(stats.get("coverage_ratio") or 0.0),
            uniqueness_ratio=float(stats.get("uniqueness_ratio") or 0.0),
            entropy=float(stats.get("entropy_normalized") or 0.0),
            distinct_count=int(stats.get("distinct_count") or 0),
            non_null_count=int(stats.get("non_null_count") or 0),
            total_count=int(stats.get("total_count") or 0),
            physical_type=str(column.get("physical_type") or "unknown"),
            semantic_type=str(column.get("semantic_type") or "unknown"),
            logical_type=str(column.get("logical_type") or "unknown"),
            sample_values=self._sample_values(table_name, column_name, fallback=column.get("sample_values") or []),
        )

    # ------------------------------------------------------------------
    # PK discovery
    # ------------------------------------------------------------------

    def _discover_primary_keys(self) -> None:
        for table_name, profile in self.profiles.items():
            columns = [self.columns[(table_name, str(col["column_name"]).lower())] for col in profile.get("columns", [])]
            scored: list[tuple[ColumnContext, float, dict[str, Any]]] = []

            for ctx in columns:
                if not ctx.is_identifier or ctx.is_audit:
                    continue
                score, breakdown = self._pk_score(ctx)
                scored.append((ctx, score, breakdown))

            scored.sort(key=lambda item: item[1], reverse=True)

            composite = self._discover_composite_key(table_name, columns, scored)
            composite_reason = ""
            if composite and composite.get("reasoning"):
                composite_reason = str(composite["reasoning"][0])
            bridge_like = composite_reason in {"line_item_composite", "bridge_table_composite"}

            strong_owner = [item for item in scored if item[2]["ownership"] >= 1.0 and item[1] >= 0.80]
            strong_any = [item for item in scored if item[1] >= 0.80]
            candidate_any = [item for item in scored if item[1] >= 0.60]

            chosen: tuple[ColumnContext, float, dict[str, Any]] | None = None
            if not bridge_like:
                if strong_owner:
                    chosen = strong_owner[0]
                elif strong_any:
                    chosen = strong_any[0]

            if chosen is not None:
                ctx, score, breakdown = chosen
                self.primary_keys[table_name] = {
                    "table": table_name,
                    "table_root": self.table_roots[table_name],
                    "column": ctx.column_name,
                    "pk_score": round(score, 4),
                    "pk_type": "PRIMARY_KEY",
                    "ownership": round(breakdown["ownership"], 4),
                    "uniqueness": round(ctx.uniqueness_ratio, 4),
                    "coverage_ratio": round(ctx.coverage_ratio, 4),
                    "entropy": round(ctx.entropy, 4),
                    "naming": round(breakdown["naming"], 4),
                    "stability": round(breakdown["stability"], 4),
                    "candidate_columns": [item[0].column_name for item in candidate_any[:5]],
                    "reasoning": breakdown["reasoning"],
                }
                if composite and bridge_like:
                    self.composite_keys[table_name] = composite
            elif composite:
                self.composite_keys[table_name] = composite

        for table_name in self.profiles:
            if table_name not in self.primary_keys and table_name not in self.composite_keys:
                columns = [self.columns[(table_name, str(col["column_name"]).lower())] for col in self.profiles[table_name].get("columns", [])]
                composite = self._discover_composite_key(table_name, columns, [])
                if composite:
                    self.composite_keys[table_name] = composite

    def _pk_score(self, ctx: ColumnContext) -> tuple[float, dict[str, Any]]:
        ownership = 1.0 if ctx.root == ctx.table_root else 0.0
        naming = 1.0 if re.search(r"(id|key)$", ctx.column_name) else 0.5 if ctx.is_identifier else 0.0
        if ownership == 1.0 and ctx.column_name == f"{ctx.table_root}id":
            naming = 1.0

        stability = 1.0
        if ctx.is_temporal or ctx.is_audit or ctx.is_measure or ctx.is_text:
            stability = 0.0
        elif any(token in ctx.column_name for token in MUTABLE_PATTERNS):
            stability = 0.2

        score = (
            0.35 * ctx.uniqueness_ratio
            + 0.25 * ownership
            + 0.15 * ctx.coverage_ratio
            + 0.10 * ctx.entropy
            + 0.10 * naming
            + 0.05 * stability
        )

        reasons = []
        if ownership:
            reasons.append("owner_identifier")
        if ctx.uniqueness_ratio > 0.95:
            reasons.append("high_uniqueness")
        if ctx.coverage_ratio >= 0.99:
            reasons.append("complete")
        if ctx.entropy > 0.80:
            reasons.append("high_entropy")
        if any(token in ctx.column_name for token in ("invoiceid", "orderid", "customerid", "supplierid", "cityid", "stateprovinceid", "countryid", "personid")) and ownership:
            score = max(score, 0.90)
            reasons.append("owner_id_boost")
        if ctx.is_audit or ctx.is_temporal or ctx.is_measure:
            score = min(score, 0.20)

        return score, {
            "ownership": ownership,
            "naming": naming,
            "stability": stability,
            "reasoning": reasons,
        }

    def _discover_composite_key(
        self,
        table_name: str,
        columns: list[ColumnContext],
        scored: list[tuple[ColumnContext, float, dict[str, Any]]],
    ) -> dict[str, Any] | None:
        id_columns = [ctx for ctx in columns if ctx.is_identifier and not ctx.is_audit]
        temporal_components = [ctx for ctx in columns if ctx.column_name in TEMPORAL_COMPONENT_PATTERNS or ctx.column_name in {"validfrom", "effectivefrom", "version", "sequence"}]
        line_component = next((ctx for ctx in id_columns if ctx.column_name in {"lineid", "orderlineid", "invoicelineid", "purchaseorderlineid"}), None)
        owner_component = next((ctx for ctx in id_columns if ctx.root == ctx.table_root), None)
        parent_component = next((ctx for ctx in id_columns if ctx.root != ctx.table_root and ctx.root in self.root_to_tables), None)

        if owner_component and temporal_components and owner_component.uniqueness_ratio < 0.95:
            second = temporal_components[0]
            return self._composite_payload(table_name, [owner_component.column_name, second.column_name], "temporal_composite")

        if _is_line_or_bridge_table(table_name):
            if parent_component and line_component:
                return self._composite_payload(table_name, [parent_component.column_name, line_component.column_name], "line_item_composite")
            fk_like = [ctx for ctx in id_columns if ctx.root in self.root_to_tables and ctx.root != self.table_roots[table_name]]
            distinct_roots = []
            for ctx in fk_like:
                if ctx.root not in distinct_roots:
                    distinct_roots.append(ctx.root)
            if len(distinct_roots) >= 2:
                chosen = []
                seen = set()
                for ctx in fk_like:
                    if ctx.root in seen:
                        continue
                    chosen.append(ctx.column_name)
                    seen.add(ctx.root)
                    if len(chosen) == 2:
                        break
                if len(chosen) == 2:
                    return self._composite_payload(table_name, chosen, "bridge_table_composite")

        if not scored and owner_component and temporal_components:
            return self._composite_payload(table_name, [owner_component.column_name, temporal_components[0].column_name], "fallback_temporal_composite")

        return None

    def _composite_payload(self, table_name: str, columns: list[str], reason: str) -> dict[str, Any]:
        return {
            "table": table_name,
            "table_root": self.table_roots[table_name],
            "pk_type": "COMPOSITE",
            "columns": columns,
            "reasoning": [reason],
        }

    # ------------------------------------------------------------------
    # Relationship discovery
    # ------------------------------------------------------------------

    def _build_audit_reference(self, ctx: ColumnContext) -> dict[str, Any] | None:
        target_table = self._best_root_table("person") or self._best_root_table("user") or self._best_root_table("employee")
        if not target_table:
            return None
        target_column = self._target_key_column(target_table)
        if not target_column:
            return None
        return {
            "fk_table": ctx.table_name,
            "fk_column": ctx.column_name,
            "pk_table": target_table,
            "pk_column": target_column,
            "relationship_class": "AUDIT_REFERENCE",
            "confidence_score": 0.82,
            "containment_ratio": self._containment_ratio(ctx.sample_values, self._sample_values(target_table, target_column)),
            "semantic_similarity": 0.6,
            "fk_hint": "possible",
            "audit_profile": ctx.profile.get("audit_profile") or {},
            "reasoning": ["audit_identifier", "possible_people_reference"],
        }

    def _build_self_reference(self, ctx: ColumnContext) -> dict[str, Any] | None:
        if ctx.column_name not in SELF_REFERENCE_PATTERNS:
            return None
        if not self._is_valid_self_reference(ctx):
            return None
        target_column = self._target_key_column(ctx.table_name)
        if not target_column:
            return None
        containment = self._containment_ratio(ctx.sample_values, self._sample_values(ctx.table_name, target_column))
        return {
            "fk_table": ctx.table_name,
            "fk_column": ctx.column_name,
            "pk_table": ctx.table_name,
            "pk_column": target_column,
            "relationship_class": "SELF_REFERENCE",
            "confidence_score": round(0.75 + 0.15 * containment, 4),
            "containment_ratio": containment,
            "semantic_similarity": 0.5,
            "reasoning": ["self_reference_pattern"],
        }

    def _build_best_fk(self, ctx: ColumnContext) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        invalid: list[dict[str, Any]] = []
        candidates = self._candidate_targets(ctx)
        if not candidates:
            return None, invalid

        scored = []
        for target_table, target_column in candidates:
            result = self._score_fk_candidate(ctx, target_table, target_column)
            if result["relationship_class"] == "INVALID_MATCH":
                invalid.append(result)
                continue
            scored.append(result)

        if not scored:
            return None, invalid

        scored.sort(key=lambda item: item["confidence_score"], reverse=True)
        best = scored[0]
        if best["confidence_score"] < 0.75:
            best["relationship_class"] = "INVALID_MATCH"
            invalid.append(best)
            return None, invalid
        return best, invalid

    def _candidate_targets(self, ctx: ColumnContext) -> list[tuple[str, str]]:
        if ctx.root == ctx.table_root:
            return []
        candidates: list[tuple[str, str]] = []
        target_roots = [ctx.root] if ctx.root else []
        for root in target_roots:
            for table in self.root_to_tables.get(root, []):
                target_column = self._target_key_column(table)
                if target_column:
                    candidates.append((table, target_column))
        if ctx.root == "person":
            for table in self.root_to_tables.get("person", []):
                target_column = self._target_key_column(table)
                if target_column:
                    candidates.append((table, target_column))
        return _dedupe_pairs(candidates)

    def _score_fk_candidate(self, ctx: ColumnContext, target_table: str, target_column: str) -> dict[str, Any]:
        target_root = self.table_roots.get(target_table, _table_root(target_table))
        target_samples = self._sample_values(target_table, target_column)
        containment = self._containment_ratio(ctx.sample_values, target_samples)
        entity_match = 1.0 if ctx.root == target_root else 0.0
        exact_name = 1.0 if ctx.column_name == target_column else 0.85 if ctx.root == _column_root(target_column, set(self.root_to_tables.keys())) else 0.0
        type_compatibility = 1.0 if _compatible_physical_types(ctx.physical_type, self.columns.get((target_table, target_column), ctx).physical_type) else 0.0
        cardinality = self._cardinality_score(ctx, target_table, target_column)
        semantic = self._semantic_score(ctx, target_table)

        if entity_match == 0.0:
            return {
                "fk_table": ctx.table_name,
                "fk_column": ctx.column_name,
                "pk_table": target_table,
                "pk_column": target_column,
                "relationship_class": "INVALID_MATCH",
                "confidence_score": 0.0,
                "containment_ratio": containment,
                "semantic_similarity": semantic,
                "reasoning": ["entity_mismatch"],
            }

        score = (
            0.30 * containment
            + 0.25 * entity_match
            + 0.20 * exact_name
            + 0.10 * type_compatibility
            + 0.10 * cardinality
            + 0.05 * semantic
        )

        rel_class = "FOREIGN_KEY"
        if target_root in TRANSACTION_ROOTS:
            rel_class = "TRANSACTION_REFERENCE"
        elif ctx.distinct_count < 20 and any(token in ctx.root for token in ENUM_ENTITY_HINTS):
            rel_class = "ENUM_REFERENCE"
        elif ctx.distinct_count < 100 and target_table.lower().startswith(("application_", "warehouse_")):
            rel_class = "DIMENSION_REFERENCE"

        return {
            "fk_table": ctx.table_name,
            "fk_column": ctx.column_name,
            "pk_table": target_table,
            "pk_column": target_column,
            "relationship_class": rel_class,
            "confidence_score": round(score, 4),
            "containment_ratio": round(containment, 4),
            "semantic_similarity": round(semantic, 4),
            "entity_match": round(entity_match, 4),
            "exact_name": round(exact_name, 4),
            "type_compatibility": round(type_compatibility, 4),
            "cardinality_score": round(cardinality, 4),
            "reasoning": [f"root:{ctx.root}", f"target:{target_root}"],
        }

    def _cardinality_score(self, fk_ctx: ColumnContext, pk_table: str, pk_column: str) -> float:
        pk_ctx = self.columns.get((pk_table, pk_column))
        if not pk_ctx:
            return 0.0
        fk_distinct = fk_ctx.distinct_count or 0
        pk_distinct = pk_ctx.distinct_count or 0
        if pk_distinct <= 0:
            return 0.0
        if fk_distinct > pk_distinct:
            return 0.0
        if fk_ctx.uniqueness_ratio > pk_ctx.uniqueness_ratio + 1e-9:
            return 0.0
        return 1.0

    def _semantic_score(self, ctx: ColumnContext, target_table: str) -> float:
        desc = self.descriptions.get((ctx.table_name.lower(), ctx.column_name.lower()), {})
        pk = self.primary_keys.get(target_table, {})
        pk_desc = self.descriptions.get((target_table.lower(), str(pk.get("column", "")).lower()), {})
        if desc and pk_desc:
            left = str(desc.get("data_domain") or "").upper()
            right = str(pk_desc.get("data_domain") or "").upper()
            if left == "FOREIGN_KEY" and right == "PRIMARY_KEY":
                return 1.0
        return 0.6 if ctx.is_identifier else 0.0

    def _detect_bridge_tables(self, fk_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rel in fk_edges:
            by_table[rel["fk_table"]].append(rel)

        bridge_tables: list[dict[str, Any]] = []
        for table_name, rels in by_table.items():
            if len(rels) < 2:
                continue
            composite = self.composite_keys.get(table_name)
            if composite or _is_line_or_bridge_table(table_name):
                bridge_tables.append(
                    {
                        "table": table_name,
                        "relationship_class": "BRIDGE_TABLE",
                        "fk_columns": [rel["fk_column"] for rel in rels],
                        "targets": [rel["pk_table"] for rel in rels],
                        "composite_pk": composite["columns"] if composite else [],
                    }
                )
        return bridge_tables

    def _promote_enum_refs(self, fk_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        promoted = []
        for rel in fk_edges:
            if rel["relationship_class"] == "ENUM_REFERENCE":
                promoted.append(rel)
        return promoted

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _build_relationship_records(
        self,
        fk_edges: list[dict[str, Any]],
        audit_refs: list[dict[str, Any]],
        enum_refs: list[dict[str, Any]],
        self_refs: list[dict[str, Any]],
        invalid_matches: list[dict[str, Any]],
        bridge_tables: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        relationships: list[dict[str, Any]] = []

        for pk in self.primary_keys.values():
            relationships.append(
                {
                    "fk_table": pk["table"],
                    "fk_column": pk["column"],
                    "pk_table": pk["table"],
                    "pk_column": pk["column"],
                    "relationship_class": "PRIMARY_KEY",
                    "confidence_score": pk["pk_score"],
                    "containment_ratio": 1.0,
                    "semantic_similarity": 1.0,
                }
            )

        for composite in self.composite_keys.values():
            for column in composite["columns"]:
                relationships.append(
                    {
                        "fk_table": composite["table"],
                        "fk_column": column,
                        "pk_table": composite["table"],
                        "pk_column": column,
                        "relationship_class": "COMPOSITE_KEY",
                        "confidence_score": 0.85,
                        "containment_ratio": 1.0,
                        "semantic_similarity": 1.0,
                    }
                )

        relationships.extend(fk_edges)
        relationships.extend(audit_refs)
        relationships.extend(self_refs)
        relationships.extend(enum_refs)
        relationships.extend(invalid_matches)

        for bridge in bridge_tables:
            relationships.append(
                {
                    "fk_table": bridge["table"],
                    "fk_column": ",".join(bridge["fk_columns"]),
                    "pk_table": bridge["table"],
                    "pk_column": ",".join(bridge.get("composite_pk") or bridge["fk_columns"][:2]),
                    "relationship_class": "BRIDGE_TABLE",
                    "confidence_score": 0.85,
                    "containment_ratio": 1.0,
                    "semantic_similarity": 0.8,
                }
            )

        deduped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        for rel in relationships:
            key = (
                rel["fk_table"].lower(),
                rel["fk_column"].lower(),
                rel["pk_table"].lower(),
                rel["pk_column"].lower(),
                rel["relationship_class"],
            )
            existing = deduped.get(key)
            if existing is None or float(rel.get("confidence_score") or 0.0) > float(existing.get("confidence_score") or 0.0):
                deduped[key] = rel
        return sorted(deduped.values(), key=lambda rel: (rel["relationship_class"], -float(rel.get("confidence_score") or 0.0), rel["fk_table"].lower(), rel["fk_column"].lower()))

    def _write_outputs(self, payload: dict[str, Any]) -> None:
        self.relationships_dir.mkdir(parents=True, exist_ok=True)
        self.erd_dir.mkdir(parents=True, exist_ok=True)
        self.graph_dir.mkdir(parents=True, exist_ok=True)

        relationships_path = self.relationships_dir / "relationships.json"
        relationships_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        erd_json = {
            "nodes": [{"id": table, "label": table} for table in sorted(self.profiles.keys(), key=str.lower)],
            "edges": [
                {
                    "source": rel["fk_table"],
                    "target": rel["pk_table"],
                    "type": rel["relationship_class"],
                    "label": f'{rel["fk_column"]} -> {rel["pk_column"]}',
                    "confidence": rel["confidence_score"],
                }
                for rel in payload["erd_edges"]
            ],
        }
        (self.erd_dir / "erd.json").write_text(json.dumps(erd_json, indent=2), encoding="utf-8")
        (self.graph_dir / "graph.json").write_text(json.dumps(erd_json, indent=2), encoding="utf-8")

        dbml = self._build_dbml(payload)
        (self.erd_dir / "schema.dbml").write_text(dbml, encoding="utf-8")
        (self.erd_dir / "erd.html").write_text(self._build_erd_html(payload["erd_edges"]), encoding="utf-8")

    def _build_dbml(self, payload: dict[str, Any]) -> str:
        pk_lookup: dict[str, set[str]] = defaultdict(set)
        for pk in payload["pk"]:
            pk_lookup[pk["table"]].add(pk["column"])
        for composite in payload["composite_pk"]:
            for column in composite["columns"]:
                pk_lookup[composite["table"]].add(column)

        lines: list[str] = []
        for table_name in sorted(self.profiles.keys(), key=str.lower):
            lines.append(f"Table {_dbml_ident(table_name)} {{")
            for column in self.profiles[table_name].get("columns", []):
                name = str(column.get("column_name") or "")
                dtype = _dbml_type(column.get("physical_type"))
                if dtype == "boolean" and re.search(r"(id|key)$", name.lower()):
                    dtype = "int"
                tags = []
                if name in pk_lookup.get(table_name, set()):
                    tags.append("pk")
                if bool(column.get("profile_hints", {}).get("is_identifier")) and "pk" not in tags:
                    tags.append("note: 'identifier'")
                tag_text = f" [{', '.join(tags)}]" if tags else ""
                lines.append(f"  {_dbml_ident(name)} {dtype}{tag_text}")
            lines.append("}")
            lines.append("")

        emitted = set()
        for rel in payload["erd_edges"]:
            key = (rel["fk_table"], rel["fk_column"], rel["pk_table"], rel["pk_column"])
            if key in emitted:
                continue
            emitted.add(key)
            lines.append(
                f"Ref: {_dbml_ident(rel['fk_table'])}.{_dbml_ident(rel['fk_column'])} > "
                f"{_dbml_ident(rel['pk_table'])}.{_dbml_ident(rel['pk_column'])}"
            )
        return "\n".join(lines).strip() + "\n"

    def _build_erd_html(self, edges: list[dict[str, Any]]) -> str:
        lines = ["erDiagram"]
        if edges:
            for rel in edges:
                left = _mermaid_ident(rel["fk_table"])
                right = _mermaid_ident(rel["pk_table"])
                label = f'{rel["fk_column"]} -> {rel["pk_column"]}'.replace('"', "'")
                lines.append(f'    {left} }}o--|| {right} : "{label}"')
        else:
            lines.append('    EMPTY ||--|| EMPTY : "no validated relationships"')
        mermaid_code = "\n".join(lines)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Relationship ERD</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #f7f8fb; color: #1f2937; }}
    main {{ padding: 24px; }}
    .panel {{ background: #fff; border: 1px solid #dbe2ea; border-radius: 8px; padding: 24px; overflow: auto; }}
  </style>
</head>
<body>
  <main>
    <div class="panel">
      <pre class="mermaid">
{mermaid_code}
      </pre>
    </div>
  </main>
  <script>mermaid.initialize({{ startOnLoad: true, theme: "default", er: {{ useMaxWidth: false }} }});</script>
</body>
</html>
"""

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def _is_primary_key_column(self, table_name: str, column_name: str) -> bool:
        pk = self.primary_keys.get(table_name)
        return bool(pk and pk["column"] == column_name)

    def _sample_values(self, table_name: str, column_name: str, fallback: list[Any] | None = None) -> list[Any]:
        canonical = self.canonicals.get(table_name) or {}
        for column in canonical.get("columns", []):
            normalized = str(column.get("normalized_name") or "").lower()
            original = str(column.get("original_name") or "").lower()
            if column_name == normalized or column_name == original:
                return column.get("sample_values") or []
        return fallback or []

    def _containment_ratio(self, fk_values: list[Any], pk_values: list[Any]) -> float:
        fk_set = {str(v).strip().lower() for v in fk_values if str(v).strip() not in {"", "none", "null"}}
        pk_set = {str(v).strip().lower() for v in pk_values if str(v).strip() not in {"", "none", "null"}}
        if not fk_set or not pk_set:
            return 0.0
        return len(fk_set & pk_set) / max(len(fk_set), 1)

    def _best_root_table(self, root: str) -> str | None:
        tables = self.root_to_tables.get(root, [])
        if not tables:
            return None
        return sorted(
            tables,
            key=lambda table: (
                0 if table.lower().startswith("application_") else 1,
                0 if self._target_key_column(table) else 1,
                table.lower(),
            ),
        )[0]

    def _target_key_column(self, table_name: str) -> str | None:
        pk = self.primary_keys.get(table_name)
        if pk:
            return str(pk["column"])
        composite = self.composite_keys.get(table_name)
        if composite:
            for column in composite.get("columns", []):
                ctx = self.columns.get((table_name, str(column).lower()))
                if ctx and ctx.root == self.table_roots.get(table_name):
                    return str(column)
            columns = composite.get("columns") or []
            if columns:
                return str(columns[0])
        return None

    def _is_valid_self_reference(self, ctx: ColumnContext) -> bool:
        if ctx.column_name in {"parentcustomerid", "billtocustomerid"}:
            return ctx.table_root == "customer"
        if ctx.column_name == "managerid":
            return ctx.table_root in {"person", "employee", "user"}
        if ctx.column_name == "parentid":
            return True
        return False


def build_relationship_graph(output_base: str | Path = "output") -> dict[str, Any]:
    builder = ProductionRelationshipBuilder(output_base=output_base)
    return builder.build()


def _table_root(table_name: str) -> str:
    value = table_name.lower()
    for prefix in TABLE_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    parts = [part for part in value.split("_") if part]
    if not parts:
        return value
    return _singularize(parts[-1])


def _column_root(column_name: str, known_roots: set[str]) -> str:
    value = column_name.lower()
    for suffix in ("identifier", "number", "num", "no", "code", "key", "id"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    value = value.rstrip("_")
    normalized = re.sub(r"[^a-z0-9]", "", value)
    if normalized in known_roots:
        return normalized
    for root in sorted(known_roots, key=len, reverse=True):
        if normalized.endswith(root):
            return root
    return _singularize(normalized)


def _singularize(value: str) -> str:
    irregular = {
        "people": "person",
        "men": "man",
        "women": "woman",
        "children": "child",
    }
    if value in irregular:
        return irregular[value]
    if value.endswith("ies") and len(value) > 3:
        return value[:-3] + "y"
    if value.endswith("ses") and len(value) > 3:
        return value[:-2]
    if value.endswith("s") and not value.endswith("ss") and len(value) > 1:
        return value[:-1]
    return value


def _is_line_or_bridge_table(table_name: str) -> bool:
    lowered = table_name.lower()
    return any(token in lowered for token in ("lines", "line", "stockitemstockgroups", "bridge", "mapping"))


def _compatible_physical_types(left: str, right: str) -> bool:
    left_norm = left.lower()
    right_norm = right.lower()
    if left_norm == right_norm:
        return True
    int_family = {"integer", "bigint", "smallint", "int"}
    str_family = {"string", "varchar", "text"}
    if left_norm in int_family and right_norm in int_family:
        return True
    if left_norm in str_family and right_norm in str_family:
        return True
    return False


def _dbml_ident(value: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        return value
    return f'"{value}"'


def _dbml_type(value: Any) -> str:
    dtype = str(value or "string").lower()
    return {
        "integer": "int",
        "float": "float",
        "decimal": "decimal",
        "datetime": "datetime",
        "date": "date",
        "boolean": "boolean",
        "uuid": "uuid",
        "json": "json",
    }.get(dtype, "varchar")


def _name_contains_measure_token(column_name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", column_name.lower()).strip("_")
    tokens = [token for token in normalized.split("_") if token]
    for token in tokens:
        if token in MEASURE_PATTERNS:
            return True
    return False


def _mermaid_ident(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned or "unknown_table"


def _dedupe_pairs(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen = set()
    ordered = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
