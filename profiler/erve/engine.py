"""ER Visualization Engine (ERVE).

The engine consumes relationship.json and emits multiple ER intelligence
representations:
- dbdiagram DBML
- diagrams.net XML
- Mermaid ERD
- standalone HTML previews
- relationship charts
- graph JSON and graph HTML

The implementation is intentionally dependency-light for exporters and uses
matplotlib only for PNG chart generation.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import textwrap
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


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
POSSIBLE_REFERENCE = "POSSIBLE_REFERENCE"
SEMANTICALLY_RELATED = "SEMANTICALLY_RELATED"
SHARED_ENTITY_DOMAIN = "SHARED_ENTITY_DOMAIN"

ERD_CLASSES = {FOREIGN_KEY, AUDIT_REFERENCE, ENUM_REFERENCE, DIMENSION_REFERENCE, TRANSACTION_REFERENCE, SELF_REFERENCE, TRUE_FK}
DRAWIO_CLASSES = ERD_CLASSES | {SEMANTICALLY_RELATED, SHARED_ENTITY_DOMAIN, BRIDGE_TABLE}

CLASS_COLORS = {
    PRIMARY_KEY: "#0f766e",
    FOREIGN_KEY: "#10b981",
    COMPOSITE_KEY: "#2563eb",
    AUDIT_REFERENCE: "#8b5cf6",
    ENUM_REFERENCE: "#f59e0b",
    DIMENSION_REFERENCE: "#0ea5e9",
    TRANSACTION_REFERENCE: "#22c55e",
    SELF_REFERENCE: "#ef4444",
    BRIDGE_TABLE: "#64748b",
    INVALID_MATCH: "#9ca3af",
    TRUE_FK: "#10b981",
    POSSIBLE_REFERENCE: "#f59e0b",
    SEMANTICALLY_RELATED: "#3b82f6",
    SHARED_ENTITY_DOMAIN: "#8b5cf6",
    "UNKNOWN": "#6b7280",
}

# Auto-scaling constants for top_k computation
DEFAULT_TOP_K = 100
AUTO_TOP_K_SMALL = 50  # For < 50 tables
AUTO_TOP_K_MEDIUM = 100  # For 50-200 tables
AUTO_TOP_K_LARGE = 200  # For > 200 tables
AUTO_TOP_K_HUGE = 500  # For > 10000 relationships


@dataclass
class ERVEConfig:
    """Configuration for ERVE exports.
    
    top_k is optional and will be auto-computed based on dataset size if None:
    - < 50 tables: top_k = 50
    - 50-200 tables: top_k = 100
    - > 200 tables: top_k = 200
    - > 10000 relationships: top_k = 500
    """

    relationships_path: str | Path = "output/relationships/relationships.json"
    output_base: str | Path = "output"
    profiles_dir: str | Path | None = None
    canonical_dir: str | Path | None = None
    lcil_path: str | Path | None = None
    min_confidence: float = 0.5
    top_k: int | None = None  # Auto-computed if None
    max_render_edges: int = 500
    max_mermaid_edges: int = 450
    max_drawio_edges: int = 700
    max_drawio_nodes: int = 350
    max_tables_per_module: int = 120
    split_modules_over_tables: int = 240
    heatmap_top_n: int = 25


class ERVEEngine:
    """Generate ER visualizations and graph intelligence from relationship.json."""

    def __init__(
        self,
        relationships_path: str | Path | None = None,
        output_base: str | Path = "output",
        config: ERVEConfig | None = None,
    ) -> None:
        if config is None:
            config = ERVEConfig(
                relationships_path=relationships_path
                or "output/relationships/relationships.json",
                output_base=output_base,
            )
        elif relationships_path is not None:
            config.relationships_path = relationships_path
        self.config = config

        self.relationships_path = Path(config.relationships_path)
        self.output_base = Path(config.output_base)
        self.profiles_dir = Path(config.profiles_dir) if config.profiles_dir else self.output_base / "profiles"
        self.canonical_dir = Path(config.canonical_dir) if config.canonical_dir else self.output_base / "canonical"
        self.lcil_path = Path(config.lcil_path) if config.lcil_path else self.output_base / "low_cardinality" / "low_cardinality_insights.json"

        self.erd_dir = self.output_base / "erd"
        self.drawio_dir = self.output_base / "drawio"
        self.charts_dir = self.output_base / "charts"
        self.graph_dir = self.output_base / "graph"
        self.scripts_dir = self.output_base / "scripts"

        self.raw_data: dict[str, Any] = {}
        self.raw_relationships: list[dict[str, Any]] = []
        self.relationships: list[dict[str, Any]] = []
        self.tables: set[str] = set()
        self.table_case: dict[str, str] = {}
        self.table_columns: dict[str, list[dict[str, Any]]] = {}
        self.column_lookup: dict[tuple[str, str], dict[str, Any]] = {}
        self.pk_columns: dict[str, set[str]] = defaultdict(set)
        self.lcil_insights: list[dict[str, Any]] = []
        self.loaded = False

    # ------------------------------------------------------------------
    # Loading and normalization
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load relationships plus optional profile/canonical/LCIL context."""

        if self.loaded:
            return
        if not self.relationships_path.exists():
            raise FileNotFoundError(f"Relationships file not found: {self.relationships_path}")

        self.raw_data = _read_json(self.relationships_path)
        source_relationships = self.raw_data.get("relationships", self.raw_data)
        if not isinstance(source_relationships, list):
            raise ValueError("relationship.json must contain a relationships list")

        normalized = []
        for item in source_relationships:
            rel = self._normalize_relationship(item)
            if rel:
                normalized.append(rel)

        self.raw_relationships = self._dedupe_relationships(normalized)
        self.relationships = self._prune_relationships(self.raw_relationships)

        self._load_profiles()
        self._load_canonical()
        self._load_lcil()
        self._add_relationship_tables_and_columns()
        self.loaded = True

    def _normalize_relationship(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize current and legacy relationship shapes into one schema."""

        if not isinstance(item, dict):
            return None

        if "fk_table" in item or "pk_table" in item:
            fk_table = item.get("fk_table")
            fk_column = item.get("fk_column")
            pk_table = item.get("pk_table")
            pk_column = item.get("pk_column")
            rel_class = str(item.get("relationship_class") or "").upper().strip()
            if not rel_class or rel_class == "UNKNOWN":
                rel_type = str(item.get("relationship_type") or "").upper().strip()
                rel_class_map = {
                    "FK": FOREIGN_KEY,
                    "AUDIT": AUDIT_REFERENCE,
                    "ENUM": ENUM_REFERENCE,
                    "SELF": SELF_REFERENCE,
                    "BRIDGE": BRIDGE_TABLE,
                    "DIMENSION": DIMENSION_REFERENCE,
                    "TRANSACTION": TRANSACTION_REFERENCE,
                    "TRUE_FK": TRUE_FK,
                }
                rel_class = rel_class_map.get(rel_type, "UNKNOWN")
            confidence = item.get("confidence_score", item.get("confidence", 0.0))
            semantic_similarity = item.get("semantic_similarity", 0.0)
            containment_ratio = item.get("containment_ratio", 0.0)
        else:
            from_col = item.get("from") or {}
            to_col = item.get("to") or {}
            fk_table = from_col.get("table")
            fk_column = from_col.get("column")
            pk_table = to_col.get("table")
            pk_column = to_col.get("column")
            accepted = bool(item.get("accepted"))
            rel_type = str(item.get("relationship_type") or "").lower()
            rel_class = TRUE_FK if accepted and "foreign" in rel_type else POSSIBLE_REFERENCE
            confidence = item.get("confidence", 0.0)
            evidence = item.get("evidence") or {}
            semantic_similarity = evidence.get("semantic_similarity", 0.0) or 0.0
            containment_ratio = evidence.get("containment_ratio", 0.0) or 0.0

        if not all([fk_table, fk_column, pk_table, pk_column]):
            return None

        return {
            "fk_table": str(fk_table),
            "fk_column": str(fk_column),
            "pk_table": str(pk_table),
            "pk_column": str(pk_column),
            "relationship_class": rel_class,
            "confidence_score": _safe_float(confidence),
            "semantic_similarity": _safe_float(semantic_similarity),
            "containment_ratio": _safe_float(containment_ratio),
            "reasoning": item.get("reasoning") or [],
        }

    def _dedupe_relationships(self, relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        for rel in relationships:
            key = (
                rel["fk_table"].lower(),
                rel["fk_column"].lower(),
                rel["pk_table"].lower(),
                rel["pk_column"].lower(),
                rel["relationship_class"],
            )
            current = best.get(key)
            if current is None or rel["confidence_score"] > current["confidence_score"]:
                best[key] = rel
        return sorted(
            best.values(),
            key=lambda r: (
                _class_rank(r["relationship_class"]),
                -r["confidence_score"],
                r["fk_table"].lower(),
                r["fk_column"].lower(),
                r["pk_table"].lower(),
                r["pk_column"].lower(),
            ),
        )

    def _auto_compute_top_k(self, relationship_count: int) -> int:
        """Auto-compute top_k based on dataset characteristics.
        
        Args:
            relationship_count: Number of relationships after confidence filtering
            
        Returns:
            Computed top_k value
        """
        table_count = len(self.tables)
        
        # Priority 1: If we have a huge number of relationships, cap higher
        if relationship_count > 10000:
            return AUTO_TOP_K_HUGE
        
        # Priority 2: Scale based on table count
        if table_count < 50:
            return AUTO_TOP_K_SMALL
        elif table_count <= 200:
            return AUTO_TOP_K_MEDIUM
        else:
            return AUTO_TOP_K_LARGE

    def _prune_relationships(self, relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter and prune relationships by confidence and top_k.
        
        Applies min_confidence filtering, sorts by class and confidence,
        and limits to top_k (auto-computed if not specified).
        """
        # Filter by confidence threshold
        filtered = [
            rel
            for rel in relationships
            if rel.get("confidence_score", 0.0) >= self.config.min_confidence
        ]
        
        # Sort by relationship class priority and confidence
        filtered.sort(
            key=lambda r: (
                _class_rank(r["relationship_class"]),
                -r["confidence_score"],
                r["fk_table"].lower(),
                r["pk_table"].lower(),
            )
        )
        
        # Apply top_k (auto-compute if None)
        effective_top_k = self.config.top_k
        if effective_top_k is None:
            effective_top_k = self._auto_compute_top_k(len(filtered))
        
        if effective_top_k > 0:
            filtered = filtered[:effective_top_k]
        
        return filtered

    def _load_profiles(self) -> None:
        if not self.profiles_dir.exists():
            return
        for path in sorted(self.profiles_dir.glob("*.profile.json")):
            try:
                profile = _read_json(path)
            except Exception:
                continue
            table = str(profile.get("table_name") or path.name.replace(".profile.json", ""))
            table = self._remember_table(table)
            table_profile = profile.get("table_profile") or {}
            for pk in table_profile.get("pk_candidates") or []:
                self.pk_columns[table].add(str(pk))
            columns = []
            for col in profile.get("columns") or []:
                name = str(col.get("column_name") or col.get("normalized_name") or col.get("original_name") or "")
                if not name:
                    continue
                meta = {
                    "name": name,
                    "original_name": col.get("original_name") or name,
                    "position": col.get("position", len(columns)),
                    "physical_type": col.get("physical_type") or "string",
                    "semantic_type": col.get("semantic_type"),
                    "logical_type": col.get("logical_type"),
                    "pk_candidate": bool(col.get("pk_candidate")),
                    "fk_candidate": bool(col.get("fk_candidate")),
                }
                if meta["pk_candidate"]:
                    self.pk_columns[table].add(name)
                columns.append(meta)
                self.column_lookup[(table.lower(), name.lower())] = meta
            columns.sort(key=lambda c: c.get("position", 0))
            if columns:
                self.table_columns[table] = columns
        for pk in self.raw_data.get("pk", []) or []:
            table = self._remember_table(str(pk.get("table") or ""))
            column = str(pk.get("column") or "")
            if table and column:
                self.pk_columns[table].add(column)
        for composite in self.raw_data.get("composite_pk", []) or []:
            table = self._remember_table(str(composite.get("table") or ""))
            for column in composite.get("columns") or []:
                self.pk_columns[table].add(str(column))

    def _load_canonical(self) -> None:
        if not self.canonical_dir.exists():
            return
        for path in sorted(self.canonical_dir.glob("*.canonical.json")):
            try:
                canonical = _read_json(path)
            except Exception:
                continue
            table = str(canonical.get("table_name") or canonical.get("table_id") or path.name.replace(".canonical.json", ""))
            table = self._remember_table(table)
            if table in self.table_columns:
                continue
            columns = []
            for col in canonical.get("columns") or []:
                name = str(col.get("normalized_name") or col.get("name") or col.get("original_name") or "")
                if not name:
                    continue
                meta = {
                    "name": name,
                    "original_name": col.get("original_name") or name,
                    "position": col.get("position", len(columns)),
                    "physical_type": col.get("physical_type") or "string",
                    "semantic_type": col.get("semantic_type"),
                    "logical_type": None,
                    "pk_candidate": False,
                    "fk_candidate": False,
                }
                columns.append(meta)
                self.column_lookup[(table.lower(), name.lower())] = meta
            columns.sort(key=lambda c: c.get("position", 0))
            if columns:
                self.table_columns[table] = columns

    def _load_lcil(self) -> None:
        if not self.lcil_path.exists():
            return
        try:
            data = _read_json(self.lcil_path)
        except Exception:
            return
        insights = data.get("insights") or []
        if isinstance(insights, list):
            self.lcil_insights = [item for item in insights if isinstance(item, dict)]
            for item in self.lcil_insights:
                table = item.get("table_name")
                if table:
                    self._remember_table(str(table))

    def _add_relationship_tables_and_columns(self) -> None:
        for rel in self.raw_relationships:
            fk_table = self._remember_table(rel["fk_table"])
            pk_table = self._remember_table(rel["pk_table"])
            rel["fk_table"] = fk_table
            rel["pk_table"] = pk_table
            self._remember_column(fk_table, rel["fk_column"])
            self._remember_column(pk_table, rel["pk_column"])
            if rel["relationship_class"] == TRUE_FK:
                self.pk_columns[pk_table].add(rel["pk_column"])

    def _remember_table(self, table: str) -> str:
        key = table.lower()
        existing = self.table_case.get(key)
        if existing:
            self.tables.add(existing)
            return existing
        self.table_case[key] = table
        self.tables.add(table)
        return table

    def _remember_column(self, table: str, column: str) -> None:
        table = self._remember_table(table)
        key = (table.lower(), column.lower())
        if key in self.column_lookup:
            return
        meta = {
            "name": column,
            "original_name": column,
            "position": len(self.table_columns.get(table, [])),
            "physical_type": "string",
            "semantic_type": None,
            "logical_type": None,
            "pk_candidate": False,
            "fk_candidate": False,
        }
        self.table_columns.setdefault(table, []).append(meta)
        self.column_lookup[key] = meta

    # ------------------------------------------------------------------
    # Public generation API
    # ------------------------------------------------------------------

    def ensure_output_dirs(self) -> None:
        for directory in [
            self.erd_dir,
            self.drawio_dir,
            self.charts_dir,
            self.graph_dir,
            self.scripts_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def generate_dbml(self) -> dict[str, Any]:
        """Generate dbdiagram DBML with validated cross-table relationship refs."""

        self.load()
        self.ensure_output_dirs()
        render_classes = ERD_CLASSES | {BRIDGE_TABLE}
        true_fks = self._relationships_by_class(render_classes)
        path = self.erd_dir / "schema.dbml"
        path.write_text(self._build_dbml(true_fks), encoding="utf-8")

        outputs = {"dbml": str(path.resolve())}
        module_outputs = self._write_dbml_modules(true_fks)
        outputs.update(module_outputs)
        return {
            "success": True,
            "mode": "dbml",
            "outputs": outputs,
            "true_fk_relationships": len(true_fks),
            "tables": len(self.tables),
        }

    def generate_mermaid(self) -> dict[str, Any]:
        """Generate Mermaid ERD from validated FK-like relationship classes."""

        self.load()
        self.ensure_output_dirs()
        path = self.erd_dir / "schema.mmd"
        mermaid_code = self._build_mermaid_code()
        path.write_text(mermaid_code, encoding="utf-8")
        module_outputs = self._write_mermaid_modules()
        outputs = {"mermaid": str(path.resolve()), **module_outputs}
        return {
            "success": True,
            "mode": "mermaid",
            "outputs": outputs,
            "true_fk_relationships": len(self._relationships_by_class(ERD_CLASSES | {BRIDGE_TABLE})),
            "tables": len(self.tables),
        }

    def generate_drawio(self) -> dict[str, Any]:
        """Generate diagrams.net draw.io XML files."""

        self.load()
        self.ensure_output_dirs()
        semantic_path = self.drawio_dir / "semantic_erd.drawio"
        ontology_path = self.drawio_dir / "ontology.drawio"
        semantic_path.write_text(self._build_semantic_drawio(), encoding="utf-8")
        ontology_path.write_text(self._build_ontology_drawio(), encoding="utf-8")
        return {
            "success": True,
            "mode": "drawio",
            "outputs": {
                "semantic_erd": str(semantic_path.resolve()),
                "ontology": str(ontology_path.resolve()),
            },
            "relationships_rendered": len(self._relationships_for_render(DRAWIO_CLASSES, self.config.max_drawio_edges)),
        }

    def generate_html(self) -> dict[str, Any]:
        """Generate standalone Mermaid ERD HTML preview."""

        self.load()
        self.ensure_output_dirs()
        mermaid_path = self.erd_dir / "schema.mmd"
        mermaid_code = self._build_mermaid_code()
        mermaid_path.write_text(mermaid_code, encoding="utf-8")

        html_path = self.erd_dir / "erd.html"
        html_path.write_text(self._build_erd_html(mermaid_code), encoding="utf-8")
        return {
            "success": True,
            "mode": "html",
            "outputs": {
                "html": str(html_path.resolve()),
                "mermaid": str(mermaid_path.resolve()),
            },
            "metrics": self.graph_metrics(),
        }

    def generate_charts(self) -> dict[str, Any]:
        """Generate PNG relationship charts."""

        self.load()
        self.ensure_output_dirs()
        paths = {
            "relationship_summary": self.charts_dir / "relationship_summary.png",
            "confidence_histogram": self.charts_dir / "confidence_histogram.png",
            "relationship_heatmap": self.charts_dir / "relationship_heatmap.png",
        }
        self._write_relationship_summary_chart(paths["relationship_summary"])
        self._write_confidence_histogram(paths["confidence_histogram"])
        self._write_relationship_heatmap(paths["relationship_heatmap"])
        return {
            "success": True,
            "mode": "charts",
            "outputs": {key: str(path.resolve()) for key, path in paths.items()},
            "metrics": self.graph_metrics(),
        }

    def generate_graph(self) -> dict[str, Any]:
        """Generate graph JSON and standalone graph HTML."""

        self.load()
        self.ensure_output_dirs()
        graph = self.graph_json()
        graph_path = self.graph_dir / "graph.json"
        graph_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

        html_path = self.graph_dir / "graph.html"
        html_path.write_text(self._build_graph_html(graph), encoding="utf-8")
        return {
            "success": True,
            "mode": "graph",
            "outputs": {
                "graph_json": str(graph_path.resolve()),
                "graph_html": str(html_path.resolve()),
            },
            "metrics": graph["metrics"],
        }

    def generate_full_export(self) -> dict[str, Any]:
        """Generate every ERVE artifact."""

        self.load()
        self.ensure_output_dirs()
        outputs: dict[str, str] = {}
        for result in [
            self.generate_dbml(),
            self.generate_mermaid(),
            self.generate_drawio(),
            self.generate_html(),
            self.generate_charts(),
            self.generate_graph(),
            self.ensure_scripts(),
        ]:
            outputs.update(result.get("outputs", {}))
        return {
            "success": True,
            "mode": "full",
            "outputs": outputs,
            "metrics": self.graph_metrics(),
        }

    def ensure_scripts(self) -> dict[str, Any]:
        """Generate helper scripts under output/scripts."""

        self.ensure_output_dirs()
        scripts = {
            "generate_dbml.py": "dbml",
            "generate_drawio.py": "drawio",
            "generate_mermaid.py": "mermaid",
            "generate_html.py": "html",
            "generate_charts.py": "charts",
            "generate_graph.py": "graph",
            "generate_all.py": "full",
        }
        outputs = {}
        for file_name, mode in scripts.items():
            path = self.scripts_dir / file_name
            path.write_text(self._script_content(mode), encoding="utf-8")
            outputs[file_name[:-3]] = str(path.resolve())
        return {"success": True, "mode": "scripts", "outputs": outputs}

    # ------------------------------------------------------------------
    # Graph model and metrics
    # ------------------------------------------------------------------

    def graph_json(self) -> dict[str, Any]:
        self.load()
        metrics = self.graph_metrics()
        degree = self._table_degree()
        in_degree, out_degree = self._directed_degree()
        nodes = []
        for table in sorted(self.tables, key=lambda t: t.lower()):
            columns = self.table_columns.get(table, [])
            nodes.append(
                {
                    "id": table,
                    "label": table,
                    "type": "table",
                    "group": self._module_for_table(table),
                    "degree": degree.get(table, 0),
                    "in_degree": in_degree.get(table, 0),
                    "out_degree": out_degree.get(table, 0),
                    "column_count": len(columns),
                    "pk_columns": sorted(self.pk_columns.get(table, [])),
                }
            )

        edges = []
        for idx, rel in enumerate(self.relationships):
            edges.append(
                {
                    "id": f"edge_{idx + 1}",
                    "source": rel["fk_table"],
                    "target": rel["pk_table"],
                    "type": rel["relationship_class"],
                    "confidence": rel["confidence_score"],
                    "fk_column": rel["fk_column"],
                    "pk_column": rel["pk_column"],
                    "semantic_similarity": rel.get("semantic_similarity", 0.0),
                    "containment_ratio": rel.get("containment_ratio", 0.0),
                    "label": f"{rel['fk_column']} -> {rel['pk_column']}",
                }
            )

        return {
            "schema_version": "1.0",
            "artifact_type": "erve_graph",
            "generated_at": _now(),
            "source": str(self.relationships_path),
            "metadata": {
                "raw_relationships": len(self.raw_relationships),
                "exported_relationships": len(self.relationships),
                "min_confidence": self.config.min_confidence,
                "top_k": self.config.top_k,
                "relationship_class_counts": dict(Counter(rel["relationship_class"] for rel in self.relationships)),
            },
            "nodes": nodes,
            "edges": edges,
            "groups": self._graph_groups(),
            "ontology": self._ontology_summary(),
            "metrics": metrics,
        }

    def graph_metrics(self) -> dict[str, Any]:
        self.load()
        degree = self._table_degree()
        in_degree, out_degree = self._directed_degree()
        confidences = [rel["confidence_score"] for rel in self.relationships]
        components = self._connected_components()
        class_counts = Counter(rel["relationship_class"] for rel in self.relationships)
        module_counts = Counter(self._module_for_table(table) for table in self.tables)
        orphan_tables = sorted([table for table in self.tables if degree.get(table, 0) == 0], key=str.lower)
        top_connected = [
            {
                "table": table,
                "degree": count,
                "in_degree": in_degree.get(table, 0),
                "out_degree": out_degree.get(table, 0),
                "module": self._module_for_table(table),
            }
            for table, count in degree.most_common(20)
        ]
        node_count = len(self.tables)
        edge_count = len(self.relationships)
        max_edges = node_count * (node_count - 1) if node_count > 1 else 1
        return {
            "table_count": node_count,
            "relationship_count": edge_count,
            "raw_relationship_count": len(self.raw_relationships),
            "relationship_class_counts": dict(class_counts),
            "confidence": {
                "min": min(confidences) if confidences else 0.0,
                "max": max(confidences) if confidences else 0.0,
                "avg": statistics.mean(confidences) if confidences else 0.0,
                "median": statistics.median(confidences) if confidences else 0.0,
            },
            "connected_components": len(components),
            "largest_component_size": max((len(component) for component in components), default=0),
            "density": round(edge_count / max_edges, 6),
            "orphan_tables": orphan_tables,
            "orphan_table_count": len(orphan_tables),
            "isolated_nodes": orphan_tables,
            "module_counts": dict(module_counts),
            "top_connected_tables": top_connected,
            "degree_distribution": dict(Counter(degree.values())),
        }

    # ------------------------------------------------------------------
    # DBML
    # ------------------------------------------------------------------

    def _build_dbml(self, true_fks: list[dict[str, Any]]) -> str:
        lines = [
            "// Generated by ER Visualization Engine (ERVE)",
            f"// Source: {self.relationships_path}",
            f"// Generated: {_now()}",
            "",
            "Project ERVE_Schema {",
            '  database_type: "Generic"',
            f'  Note: "Generated from relationship.json with min confidence {self.config.min_confidence}"',
            "}",
            "",
        ]

        for module, tables in self._tables_by_module().items():
            lines.append(f"// Module: {module}")
            for table in tables:
                lines.extend(self._dbml_table_lines(table))
                lines.append("")

        for rel in true_fks:
            lines.append(
                "Ref: "
                f"{_dbml_ident(rel['fk_table'])}.{_dbml_ident(rel['fk_column'])} > "
                f"{_dbml_ident(rel['pk_table'])}.{_dbml_ident(rel['pk_column'])}"
            )
        lines.append("")
        return "\n".join(lines)

    def _dbml_table_lines(self, table: str) -> list[str]:
        lines = [f"Table {_dbml_ident(table)} {{"]
        columns = self.table_columns.get(table, [])
        if not columns:
            columns = [{"name": "id", "physical_type": "integer", "position": 0}]
        pk_set = {col.lower() for col in self.pk_columns.get(table, set())}
        for col in columns:
            name = str(col["name"])
            db_type = _dbml_type(col.get("physical_type"))
            tags = []
            if name.lower() in pk_set:
                tags.append("pk")
            tag_text = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"  {_dbml_ident(name)} {db_type}{tag_text}")
        lines.append("}")
        return lines

    def _write_dbml_modules(self, true_fks: list[dict[str, Any]]) -> dict[str, str]:
        if len(self.tables) <= self.config.split_modules_over_tables:
            return {}
        outputs = {}
        by_module = self._tables_by_module()
        for module, tables in by_module.items():
            if len(tables) > self.config.max_tables_per_module:
                table_chunks = [
                    tables[i : i + self.config.max_tables_per_module]
                    for i in range(0, len(tables), self.config.max_tables_per_module)
                ]
            else:
                table_chunks = [tables]
            for idx, chunk in enumerate(table_chunks, start=1):
                chunk_set = set(chunk)
                rels = [
                    rel
                    for rel in true_fks
                    if rel["fk_table"] in chunk_set and rel["pk_table"] in chunk_set
                ]
                suffix = module if len(table_chunks) == 1 else f"{module}_{idx}"
                path = self.erd_dir / f"schema_{_file_safe(suffix)}.dbml"
                partial = self._build_dbml_for_tables(chunk, rels, suffix)
                path.write_text(partial, encoding="utf-8")
                outputs[f"dbml_{suffix}"] = str(path.resolve())
        return outputs

    def _build_dbml_for_tables(self, tables: list[str], true_fks: list[dict[str, Any]], label: str) -> str:
        lines = [f"// ERVE module export: {label}", ""]
        for table in tables:
            lines.extend(self._dbml_table_lines(table))
            lines.append("")
        for rel in true_fks:
            lines.append(
                "Ref: "
                f"{_dbml_ident(rel['fk_table'])}.{_dbml_ident(rel['fk_column'])} > "
                f"{_dbml_ident(rel['pk_table'])}.{_dbml_ident(rel['pk_column'])}"
            )
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Mermaid
    # ------------------------------------------------------------------

    def _build_mermaid_code(self, tables: set[str] | None = None, rels: list[dict[str, Any]] | None = None) -> str:
        true_fks = rels if rels is not None else self._relationships_by_class(ERD_CLASSES | {BRIDGE_TABLE})
        true_fks = self._limit_edges_for_erd(true_fks, self.config.max_mermaid_edges)
        if tables is None:
            tables = set(self.tables)
            if len(tables) > self.config.split_modules_over_tables:
                involved = {rel["fk_table"] for rel in true_fks} | {rel["pk_table"] for rel in true_fks}
                tables = involved
        id_map = self._mermaid_table_ids(tables)

        lines = [
            "erDiagram",
            f"    %% Generated by ERVE from {self.relationships_path}",
            f"    %% min_confidence={self.config.min_confidence}",
        ]
        for module, module_tables in self._tables_by_module(tables).items():
            lines.append(f"    %% Module: {module}")
            for table in module_tables:
                lines.extend(self._mermaid_table_lines(table, id_map[table]))

        seen_edges = set()
        for rel in true_fks:
            if rel["fk_table"] not in id_map or rel["pk_table"] not in id_map:
                continue
            edge_key = (
                rel["fk_table"].lower(),
                rel["fk_column"].lower(),
                rel["pk_table"].lower(),
                rel["pk_column"].lower(),
            )
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            label = _mermaid_label(rel["fk_column"])
            lines.append(f"    {id_map[rel['pk_table']]} ||--o{{ {id_map[rel['fk_table']]} : \"{label}\"")
        if len(lines) <= 3:
            lines.append("    EMPTY {")
            lines.append("        string no_true_fk_relationships")
            lines.append("    }")
        return "\n".join(lines) + "\n"

    def _mermaid_table_lines(self, table: str, table_id: str) -> list[str]:
        lines = [f"    {table_id} {{"]
        columns = self.table_columns.get(table, [])
        if not columns:
            columns = [{"name": "id", "physical_type": "string"}]
        pk_set = {col.lower() for col in self.pk_columns.get(table, set())}
        fk_cols = {
            rel["fk_column"].lower()
            for rel in self._relationships_by_class({TRUE_FK})
            if rel["fk_table"].lower() == table.lower()
        }
        for col in columns[:80]:
            name = _mermaid_column(col["name"])
            dtype = _mermaid_type(col.get("physical_type"))
            tags = []
            if col["name"].lower() in pk_set:
                tags.append("PK")
            if col["name"].lower() in fk_cols:
                tags.append("FK")
            tag_text = " " + " ".join(tags) if tags else ""
            lines.append(f"        {dtype} {name}{tag_text}")
        if len(columns) > 80:
            lines.append("        string more_columns")
        lines.append("    }")
        return lines

    def _write_mermaid_modules(self) -> dict[str, str]:
        if len(self.tables) <= self.config.split_modules_over_tables:
            return {}
        outputs = {}
        true_fks = self._relationships_by_class({TRUE_FK})
        for module, tables in self._tables_by_module().items():
            table_set = set(tables)
            rels = [
                rel
                for rel in true_fks
                if rel["fk_table"] in table_set and rel["pk_table"] in table_set
            ]
            path = self.erd_dir / f"schema_{_file_safe(module)}.mmd"
            path.write_text(self._build_mermaid_code(table_set, rels), encoding="utf-8")
            outputs[f"mermaid_{module}"] = str(path.resolve())
        return outputs

    # ------------------------------------------------------------------
    # Draw.io
    # ------------------------------------------------------------------

    def _build_semantic_drawio(self) -> str:
        relationships = self._relationships_for_render(DRAWIO_CLASSES, self.config.max_drawio_edges)
        selected_tables = self._selected_tables_for_edges(relationships, self.config.max_drawio_nodes)
        by_module = self._tables_by_module(selected_tables)

        cells = [_mx_cell("0"), _mx_cell("1", parent="0")]
        table_ids: dict[str, str] = {}
        x_base = 40
        y_base = 40
        module_w = 360
        module_gap = 44
        table_w = 260
        table_h = 96
        row_gap = 24

        module_index = 0
        for module, tables in by_module.items():
            col = module_index % 3
            row = module_index // 3
            x = x_base + col * (module_w + module_gap)
            y = y_base + row * 560
            group_h = max(170, min(520, 72 + len(tables[:8]) * (table_h + row_gap)))
            group_id = f"group_{_drawio_id(module)}"
            cells.append(
                _mx_vertex(
                    group_id,
                    f"<b>{escape(module.title())}</b><br>module cluster",
                    x,
                    y,
                    module_w,
                    group_h,
                    "swimlane;whiteSpace=wrap;html=1;rounded=1;arcSize=8;fillColor=#eef2ff;strokeColor=#c7d2fe;fontColor=#111827;",
                )
            )
            for idx, table in enumerate(tables[:8]):
                node_id = f"table_{_drawio_id(table)}"
                table_ids[table] = node_id
                tx = x + 48
                ty = y + 52 + idx * (table_h + row_gap)
                label = self._drawio_table_label(table)
                cells.append(
                    _mx_vertex(
                        node_id,
                        label,
                        tx,
                        ty,
                        table_w,
                        table_h,
                        "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#ffffff;strokeColor=#6366f1;fontColor=#111827;shadow=0;",
                    )
                )
            module_index += 1

        edge_count = 0
        for rel in relationships:
            source = table_ids.get(rel["fk_table"])
            target = table_ids.get(rel["pk_table"])
            if not source or not target:
                continue
            edge_count += 1
            color = CLASS_COLORS.get(rel["relationship_class"], CLASS_COLORS["UNKNOWN"])
            label = (
                f"{escape(rel['relationship_class'])}<br>"
                f"{escape(rel['fk_column'])} -> {escape(rel['pk_column'])}<br>"
                f"{rel['confidence_score']:.2f}"
            )
            cells.append(
                _mx_edge(
                    f"edge_{edge_count}",
                    label,
                    source,
                    target,
                    f"edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;strokeColor={color};endArrow=block;endFill=1;fontColor=#374151;",
                )
            )

        return _drawio_file("Semantic ERD", cells)

    def _build_ontology_drawio(self) -> str:
        cells = [_mx_cell("0"), _mx_cell("1", parent="0")]
        if not self.lcil_insights:
            return self._build_fallback_ontology_drawio(cells)

        domain_nodes: dict[str, str] = {}
        entity_nodes: dict[str, str] = {}
        column_nodes: dict[str, str] = {}
        edges: list[tuple[str, str, str, str]] = []

        domain_counts = Counter(str(item.get("semantic_domain") or "Unknown") for item in self.lcil_insights)
        top_domains = [domain for domain, _ in domain_counts.most_common(20)]
        for idx, domain in enumerate(top_domains):
            node_id = f"domain_{_drawio_id(domain)}"
            domain_nodes[domain] = node_id
            cells.append(
                _mx_vertex(
                    node_id,
                    f"<b>{escape(domain)}</b><br>{domain_counts[domain]} column(s)",
                    40,
                    60 + idx * 82,
                    220,
                    58,
                    "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#f5f3ff;strokeColor=#8b5cf6;fontColor=#111827;",
                )
            )

        entity_order: list[str] = []
        for item in self.lcil_insights:
            domain = str(item.get("semantic_domain") or "Unknown")
            if domain not in domain_nodes:
                continue
            entity = str(item.get("suggested_entity") or domain)
            if entity not in entity_nodes:
                entity_order.append(entity)
                node_id = f"entity_{_drawio_id(entity)}"
                entity_nodes[entity] = node_id
                idx = len(entity_order) - 1
                cells.append(
                    _mx_vertex(
                        node_id,
                        f"<b>{escape(entity)}</b><br>ontology entity",
                        340,
                        60 + idx * 82,
                        220,
                        58,
                        "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#ecfdf5;strokeColor=#10b981;fontColor=#111827;",
                    )
                )
                edges.append((f"domain_entity_{idx}", domain_nodes[domain], node_id, "classified_as"))

            column_key = f"{item.get('table_name')}.{item.get('column_name')}"
            if column_key not in column_nodes and len(column_nodes) < 180:
                node_id = f"column_{_drawio_id(column_key)}"
                column_nodes[column_key] = node_id
                idx = len(column_nodes) - 1
                cells.append(
                    _mx_vertex(
                        node_id,
                        f"{escape(column_key)}<br>{float(item.get('confidence') or 0):.2f}",
                        640,
                        60 + idx * 64,
                        260,
                        46,
                        "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#ffffff;strokeColor=#3b82f6;fontColor=#111827;",
                    )
                )
                edges.append((f"entity_column_{idx}", entity_nodes[entity], node_id, "contains"))

        for idx, (edge_id, source, target, label) in enumerate(edges[:260], start=1):
            cells.append(
                _mx_edge(
                    f"{edge_id}_{idx}",
                    escape(label),
                    source,
                    target,
                    "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#64748b;endArrow=block;endFill=1;",
                )
            )
        return _drawio_file("Ontology", cells)

    def _build_fallback_ontology_drawio(self, cells: list[str]) -> str:
        by_module = self._tables_by_module()
        for idx, (module, tables) in enumerate(by_module.items()):
            cells.append(
                _mx_vertex(
                    f"domain_{_drawio_id(module)}",
                    f"<b>{escape(module.title())}</b><br>{len(tables)} table(s)",
                    80 + (idx % 4) * 280,
                    80 + (idx // 4) * 140,
                    220,
                    72,
                    "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor=#eef2ff;strokeColor=#6366f1;fontColor=#111827;",
                )
            )
        return _drawio_file("Ontology", cells)

    def _drawio_table_label(self, table: str) -> str:
        columns = self.table_columns.get(table, [])
        pk_set = {col.lower() for col in self.pk_columns.get(table, set())}
        shown = []
        for col in columns[:5]:
            marker = " PK" if col["name"].lower() in pk_set else ""
            shown.append(f"{escape(col['name'])}{marker}")
        more = f"<br><font color=\"#6b7280\">+{len(columns) - 5} more</font>" if len(columns) > 5 else ""
        return f"<b>{escape(table)}</b><br><font color=\"#6b7280\">{self._module_for_table(table)}</font><br>" + "<br>".join(shown) + more

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def _build_erd_html(self, mermaid_code: str) -> str:
        metrics = self.graph_metrics()
        class_counts = metrics["relationship_class_counts"]
        top_tables = metrics["top_connected_tables"][:10]
        modules = metrics["module_counts"]
        confidence = metrics["confidence"]
        top_rows = "\n".join(
            f"<tr><td>{escape(item['table'])}</td><td>{escape(item['module'])}</td><td>{item['degree']}</td><td>{item['in_degree']}</td><td>{item['out_degree']}</td></tr>"
            for item in top_tables
        )
        class_cards = "\n".join(
            f"<div class=\"metric\"><span>{escape(cls.replace('_', ' ').title())}</span><strong>{count:,}</strong></div>"
            for cls, count in sorted(class_counts.items())
        )
        module_cards = "\n".join(
            f"<span class=\"tag\">{escape(module)} <b>{count}</b></span>"
            for module, count in sorted(modules.items())
        )
        source_display = escape(str(self.relationships_path))
        mermaid_escaped = escape(mermaid_code)
        generated = _now()
        return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ERVE Interactive ERD</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <style>
    :root {{
      --bg:#f7f8fc; --surface:#ffffff; --surface2:#f0f1f7; --border:#e2e5f0;
      --text:#111827; --muted:#6b7280; --accent:#6366f1; --purple:#7c3aed;
      --success:#10b981; --warning:#f59e0b; --info:#3b82f6; --radius:8px;
      --shadow:0 8px 30px rgba(0,0,0,.08);
      font-family: Inter, Segoe UI, Arial, sans-serif;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); }}
    header {{ padding:24px 32px; background:var(--surface); border-bottom:1px solid var(--border); position:sticky; top:0; z-index:2; }}
    h1 {{ margin:0; font-size:24px; letter-spacing:0; }}
    .subtitle {{ color:var(--muted); margin-top:6px; font-size:13px; }}
    main {{ padding:24px 32px 40px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-bottom:18px; }}
    .metric {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:14px 16px; box-shadow:var(--shadow); }}
    .metric span {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
    .metric strong {{ display:block; margin-top:4px; font-size:24px; }}
    .panel {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); box-shadow:var(--shadow); margin-top:16px; overflow:hidden; }}
    .panel h2 {{ margin:0; padding:14px 18px; border-bottom:1px solid var(--border); font-size:15px; }}
    .panel-body {{ padding:18px; overflow:auto; }}
    .diagram {{ min-height:620px; background:#fff; }}
    .mermaid {{ min-width:720px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ padding:9px 10px; border-bottom:1px solid var(--border); text-align:left; }}
    th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; background:var(--surface2); }}
    .tags {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .tag {{ display:inline-flex; gap:6px; align-items:center; border:1px solid var(--border); border-radius:999px; padding:6px 10px; background:var(--surface2); color:var(--muted); }}
    .toolbar {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }}
    button {{ border:1px solid var(--border); background:var(--surface); border-radius:6px; padding:8px 12px; cursor:pointer; color:var(--text); }}
    button:hover {{ border-color:var(--accent); color:var(--accent); }}
    code {{ font-family:Consolas, 'JetBrains Mono', monospace; font-size:12px; }}
  </style>
</head>
<body>
  <header>
    <h1>ER Visualization Engine</h1>
    <div class="subtitle">Source: <code>{source_display}</code> | Generated: {generated}</div>
  </header>
  <main>
    <section class="grid">
      <div class="metric"><span>Tables</span><strong>{metrics['table_count']:,}</strong></div>
      <div class="metric"><span>Relationships</span><strong>{metrics['relationship_count']:,}</strong></div>
      <div class="metric"><span>TRUE FK</span><strong>{class_counts.get(TRUE_FK, 0):,}</strong></div>
      <div class="metric"><span>Avg Confidence</span><strong>{confidence['avg']:.2f}</strong></div>
      <div class="metric"><span>Components</span><strong>{metrics['connected_components']:,}</strong></div>
      <div class="metric"><span>Orphan Tables</span><strong>{metrics['orphan_table_count']:,}</strong></div>
    </section>
    <section class="grid">{class_cards}</section>
    <section class="panel">
      <h2>Mermaid ER Diagram</h2>
      <div class="panel-body">
        <div class="toolbar">
          <button onclick="zoomDiagram(0.15)">Zoom In</button>
          <button onclick="zoomDiagram(-0.15)">Zoom Out</button>
          <button onclick="resetZoom()">Reset</button>
        </div>
        <div class="diagram" id="diagram-wrap"><pre class="mermaid" id="diagram">{mermaid_escaped}</pre></div>
      </div>
    </section>
    <section class="panel">
      <h2>Top Connected Tables</h2>
      <div class="panel-body">
        <table><thead><tr><th>Table</th><th>Module</th><th>Degree</th><th>Incoming</th><th>Outgoing</th></tr></thead><tbody>{top_rows}</tbody></table>
      </div>
    </section>
    <section class="panel">
      <h2>Clusters</h2>
      <div class="panel-body"><div class="tags">{module_cards}</div></div>
    </section>
  </main>
  <script>
    mermaid.initialize({{ startOnLoad:true, theme:"neutral", er:{{ useMaxWidth:false }} }});
    let zoom = 1;
    function applyZoom() {{
      const svg = document.querySelector("#diagram-wrap svg");
      if (svg) {{
        svg.style.transformOrigin = "top left";
        svg.style.transform = `scale(${{zoom}})`;
      }}
    }}
    function zoomDiagram(delta) {{ zoom = Math.max(0.35, Math.min(3, zoom + delta)); applyZoom(); }}
    function resetZoom() {{ zoom = 1; applyZoom(); }}
    setTimeout(applyZoom, 600);
  </script>
</body>
</html>
"""

    # ------------------------------------------------------------------
    # Charts
    # ------------------------------------------------------------------

    def _write_relationship_summary_chart(self, path: Path) -> None:
        plt = _pyplot()
        metrics = self.graph_metrics()
        class_counts = Counter(metrics["relationship_class_counts"])
        degree = self._table_degree()
        modules = Counter(metrics["module_counts"])

        fig, axes = plt.subplots(2, 2, figsize=(16, 11))
        fig.suptitle("Relationship Summary", fontsize=16, fontweight="bold")

        ax = axes[0, 0]
        labels = list(class_counts.keys()) or ["None"]
        values = [class_counts[label] for label in labels] or [0]
        colors = [CLASS_COLORS.get(label, CLASS_COLORS["UNKNOWN"]) for label in labels]
        ax.bar(labels, values, color=colors)
        ax.set_title("Relationship Class Counts")
        ax.tick_params(axis="x", rotation=25)
        ax.set_ylabel("Count")

        ax = axes[0, 1]
        top = degree.most_common(12)
        if top:
            names, counts = zip(*top)
            ax.barh(list(names)[::-1], list(counts)[::-1], color="#6366f1")
        ax.set_title("Top Connected Tables")
        ax.set_xlabel("Degree")

        ax = axes[1, 0]
        dist = Counter(degree.values())
        xs = sorted(dist)
        ys = [dist[x] for x in xs]
        ax.bar(xs, ys, color="#3b82f6")
        ax.set_title("Degree Distribution")
        ax.set_xlabel("Degree")
        ax.set_ylabel("Tables")

        ax = axes[1, 1]
        mod_top = modules.most_common(12)
        if mod_top:
            names, counts = zip(*mod_top)
            ax.barh(list(names)[::-1], list(counts)[::-1], color="#8b5cf6")
        ax.set_title(f"Module Clusters (orphans: {metrics['orphan_table_count']})")
        ax.set_xlabel("Tables")

        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(path, dpi=160, bbox_inches="tight")
        plt.close(fig)

    def _write_confidence_histogram(self, path: Path) -> None:
        plt = _pyplot()
        by_class: dict[str, list[float]] = defaultdict(list)
        for rel in self.relationships:
            by_class[rel["relationship_class"]].append(rel["confidence_score"])

        fig, ax = plt.subplots(figsize=(13, 7))
        if by_class:
            bins = [i / 20 for i in range(0, 21)]
            for rel_class, values in sorted(by_class.items()):
                ax.hist(
                    values,
                    bins=bins,
                    alpha=0.58,
                    label=rel_class,
                    color=CLASS_COLORS.get(rel_class, CLASS_COLORS["UNKNOWN"]),
                )
        else:
            ax.text(0.5, 0.5, "No relationships after confidence pruning", ha="center", va="center")
        ax.axvline(self.config.min_confidence, color="#111827", linestyle="--", linewidth=1.4, label="Min confidence")
        ax.set_title("Confidence Distribution")
        ax.set_xlabel("Confidence Score")
        ax.set_ylabel("Relationships")
        ax.set_xlim(0, 1)
        ax.legend(loc="best")
        fig.tight_layout()
        fig.savefig(path, dpi=160, bbox_inches="tight")
        plt.close(fig)

    def _write_relationship_heatmap(self, path: Path) -> None:
        plt = _pyplot()
        degree = self._table_degree()
        tables = [table for table, _ in degree.most_common(self.config.heatmap_top_n)]
        if not tables:
            tables = sorted(self.tables, key=str.lower)[: self.config.heatmap_top_n]
        index = {table: idx for idx, table in enumerate(tables)}
        matrix = [[0 for _ in tables] for _ in tables]
        for rel in self.relationships:
            if rel["fk_table"] in index and rel["pk_table"] in index:
                matrix[index[rel["fk_table"]]][index[rel["pk_table"]]] += 1

        fig, ax = plt.subplots(figsize=(max(10, len(tables) * 0.45), max(8, len(tables) * 0.42)))
        if tables:
            im = ax.imshow(matrix, cmap="Blues")
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            ax.set_xticks(range(len(tables)))
            ax.set_yticks(range(len(tables)))
            ax.set_xticklabels(tables, rotation=90, fontsize=8)
            ax.set_yticklabels(tables, fontsize=8)
            ax.set_xlabel("Referenced table")
            ax.set_ylabel("Referencing table")
        else:
            ax.text(0.5, 0.5, "No relationships after confidence pruning", ha="center", va="center")
        ax.set_title("Relationship Heatmap")
        fig.tight_layout()
        fig.savefig(path, dpi=160, bbox_inches="tight")
        plt.close(fig)

    # ------------------------------------------------------------------
    # Graph HTML
    # ------------------------------------------------------------------

    def _build_graph_html(self, graph: dict[str, Any]) -> str:
        render_graph = self._render_graph_subset(graph)
        graph_json = json.dumps(render_graph).replace("</", "<\\/")
        metrics = graph["metrics"]
        classes = sorted(graph["metadata"]["relationship_class_counts"].keys())
        options = "\n".join(f'<option value="{escape(cls)}">{escape(cls)}</option>' for cls in classes)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ERVE Graph Preview</title>
  <style>
    :root {{ --bg:#f7f8fc; --surface:#fff; --border:#e2e5f0; --text:#111827; --muted:#6b7280; --accent:#6366f1; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:Inter, Segoe UI, Arial, sans-serif; }}
    header {{ padding:18px 24px; background:var(--surface); border-bottom:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; gap:16px; }}
    h1 {{ margin:0; font-size:20px; }}
    .meta {{ color:var(--muted); font-size:13px; }}
    .controls {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
    select, input {{ border:1px solid var(--border); border-radius:6px; padding:7px 9px; background:var(--surface); color:var(--text); }}
    main {{ display:grid; grid-template-columns:1fr 300px; height:calc(100vh - 74px); }}
    svg {{ width:100%; height:100%; background:#fff; }}
    aside {{ border-left:1px solid var(--border); background:var(--surface); padding:18px; overflow:auto; }}
    .metric {{ border:1px solid var(--border); border-radius:8px; padding:12px; margin-bottom:10px; }}
    .metric span {{ display:block; color:var(--muted); font-size:12px; }}
    .metric strong {{ display:block; font-size:22px; margin-top:4px; }}
    .node-label {{ font-size:11px; fill:#111827; pointer-events:none; }}
    .edge {{ stroke-opacity:.42; }}
    @media (max-width: 900px) {{ main {{ grid-template-columns:1fr; }} aside {{ display:none; }} }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Graph Preview</h1>
      <div class="meta">Rendered subset for browser performance. Full graph is in graph.json.</div>
    </div>
    <div class="controls">
      <label>Class <select id="class-filter"><option value="">All</option>{options}</select></label>
      <label>Confidence <input id="confidence-filter" type="range" min="0" max="1" step="0.05" value="{self.config.min_confidence}"></label>
    </div>
  </header>
  <main>
    <svg id="graph"></svg>
    <aside>
      <div class="metric"><span>Tables</span><strong>{metrics['table_count']:,}</strong></div>
      <div class="metric"><span>Relationships</span><strong>{metrics['relationship_count']:,}</strong></div>
      <div class="metric"><span>Rendered Edges</span><strong>{len(render_graph['edges']):,}</strong></div>
      <div class="metric"><span>Avg Confidence</span><strong>{metrics['confidence']['avg']:.2f}</strong></div>
      <div class="metric"><span>Components</span><strong>{metrics['connected_components']:,}</strong></div>
    </aside>
  </main>
  <script>
    const GRAPH = {graph_json};
    const COLORS = {json.dumps(CLASS_COLORS)};
    const svg = document.getElementById("graph");
    const classFilter = document.getElementById("class-filter");
    const confidenceFilter = document.getElementById("confidence-filter");
    let nodes = [];
    let edges = [];

    function resetData() {{
      const cls = classFilter.value;
      const minConf = Number(confidenceFilter.value);
      edges = GRAPH.edges.filter(e => (!cls || e.type === cls) && e.confidence >= minConf);
      const ids = new Set();
      edges.forEach(e => {{ ids.add(e.source); ids.add(e.target); }});
      nodes = GRAPH.nodes.filter(n => ids.has(n.id));
      const w = svg.clientWidth || 900;
      const h = svg.clientHeight || 700;
      nodes.forEach((n, i) => {{
        n.x = n.x || w * (0.25 + 0.5 * Math.random());
        n.y = n.y || h * (0.25 + 0.5 * Math.random());
        n.vx = 0; n.vy = 0;
      }});
      draw();
    }}

    function tick() {{
      const w = svg.clientWidth || 900;
      const h = svg.clientHeight || 700;
      const byId = new Map(nodes.map(n => [n.id, n]));
      for (let i = 0; i < nodes.length; i++) {{
        for (let j = i + 1; j < nodes.length; j++) {{
          const a = nodes[i], b = nodes[j];
          let dx = a.x - b.x, dy = a.y - b.y;
          let d2 = Math.max(dx * dx + dy * dy, 80);
          let f = 650 / d2;
          a.vx += dx * f; a.vy += dy * f;
          b.vx -= dx * f; b.vy -= dy * f;
        }}
      }}
      edges.forEach(e => {{
        const a = byId.get(e.source), b = byId.get(e.target);
        if (!a || !b) return;
        let dx = b.x - a.x, dy = b.y - a.y;
        let d = Math.sqrt(dx * dx + dy * dy) || 1;
        let f = (d - 150) * 0.01;
        a.vx += dx / d * f; a.vy += dy / d * f;
        b.vx -= dx / d * f; b.vy -= dy / d * f;
      }});
      nodes.forEach(n => {{
        n.vx += (w / 2 - n.x) * 0.002;
        n.vy += (h / 2 - n.y) * 0.002;
        n.vx *= 0.82; n.vy *= 0.82;
        n.x = Math.max(30, Math.min(w - 30, n.x + n.vx));
        n.y = Math.max(30, Math.min(h - 30, n.y + n.vy));
      }});
      draw();
      requestAnimationFrame(tick);
    }}

    function draw() {{
      const byId = new Map(nodes.map(n => [n.id, n]));
      svg.innerHTML = "";
      edges.forEach(e => {{
        const a = byId.get(e.source), b = byId.get(e.target);
        if (!a || !b) return;
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
        line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
        line.setAttribute("stroke", COLORS[e.type] || COLORS.UNKNOWN);
        line.setAttribute("stroke-width", Math.max(1, e.confidence * 3));
        line.setAttribute("class", "edge");
        svg.appendChild(line);
      }});
      nodes.forEach(n => {{
        const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
        const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        c.setAttribute("cx", n.x); c.setAttribute("cy", n.y); c.setAttribute("r", Math.max(7, Math.min(20, 7 + n.degree)));
        c.setAttribute("fill", "#ffffff"); c.setAttribute("stroke", "#6366f1"); c.setAttribute("stroke-width", "2");
        const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
        t.setAttribute("x", n.x + 12); t.setAttribute("y", n.y + 4); t.setAttribute("class", "node-label");
        t.textContent = n.label;
        g.appendChild(c); g.appendChild(t); svg.appendChild(g);
      }});
    }}
    classFilter.addEventListener("change", resetData);
    confidenceFilter.addEventListener("input", resetData);
    window.addEventListener("resize", resetData);
    resetData();
    requestAnimationFrame(tick);
  </script>
</body>
</html>
"""

    def _render_graph_subset(self, graph: dict[str, Any]) -> dict[str, Any]:
        edges = sorted(
            graph["edges"],
            key=lambda e: (_class_rank(e["type"]), -float(e.get("confidence", 0.0))),
        )[: self.config.max_render_edges]
        node_ids = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
        nodes = [node for node in graph["nodes"] if node["id"] in node_ids]
        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Script generation
    # ------------------------------------------------------------------

    def _script_content(self, mode: str) -> str:
        relationships = repr(str(self.relationships_path))
        output_base = repr(str(self.output_base))
        return f'''"""Generated ERVE helper script for {mode} export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from profiler.erve import ERVEConfig, ERVEEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ERVE {mode} export.")
    parser.add_argument("--relationships-path", default={relationships})
    parser.add_argument("--output-base", default={output_base})
    parser.add_argument("--min-confidence", type=float, default={self.config.min_confidence!r})
    parser.add_argument("--top-k", type=int, default={self.config.top_k!r})
    args = parser.parse_args()

    engine = ERVEEngine(config=ERVEConfig(
        relationships_path=args.relationships_path,
        output_base=args.output_base,
        min_confidence=args.min_confidence,
        top_k=args.top_k,
    ))
    result = getattr(engine, "generate_{mode}_export", None)
    if result is None:
        if "{mode}" == "full":
            payload = engine.generate_full_export()
        else:
            payload = getattr(engine, "generate_{mode}")()
    else:
        payload = result()
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

    # ------------------------------------------------------------------
    # Utility selectors
    # ------------------------------------------------------------------

    def _relationships_by_class(self, classes: set[str]) -> list[dict[str, Any]]:
        return [rel for rel in self.relationships if rel["relationship_class"] in classes]

    def _relationships_for_render(self, classes: set[str], limit: int) -> list[dict[str, Any]]:
        rels = [rel for rel in self.relationships if rel["relationship_class"] in classes]
        rels.sort(key=lambda r: (_class_rank(r["relationship_class"]), -r["confidence_score"]))
        return rels[:limit]

    def _selected_tables_for_edges(self, rels: list[dict[str, Any]], max_nodes: int) -> set[str]:
        selected = {rel["fk_table"] for rel in rels} | {rel["pk_table"] for rel in rels}
        if len(selected) <= max_nodes:
            return selected
        degree = self._table_degree(rels)
        return {table for table, _ in degree.most_common(max_nodes)}

    def _limit_edges_for_erd(self, rels: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if len(rels) <= limit:
            return rels
        degree = self._table_degree(rels)
        return sorted(
            rels,
            key=lambda r: (
                -(degree.get(r["fk_table"], 0) + degree.get(r["pk_table"], 0)),
                -r["confidence_score"],
            ),
        )[:limit]

    def _table_degree(self, rels: list[dict[str, Any]] | None = None) -> Counter[str]:
        rels = rels if rels is not None else self.relationships
        degree: Counter[str] = Counter()
        for table in self.tables:
            degree.setdefault(table, 0)
        for rel in rels:
            degree[rel["fk_table"]] += 1
            degree[rel["pk_table"]] += 1
        return degree

    def _directed_degree(self) -> tuple[Counter[str], Counter[str]]:
        in_degree: Counter[str] = Counter()
        out_degree: Counter[str] = Counter()
        for table in self.tables:
            in_degree.setdefault(table, 0)
            out_degree.setdefault(table, 0)
        for rel in self.relationships:
            out_degree[rel["fk_table"]] += 1
            in_degree[rel["pk_table"]] += 1
        return in_degree, out_degree

    def _connected_components(self) -> list[set[str]]:
        adjacency: dict[str, set[str]] = {table: set() for table in self.tables}
        for rel in self.relationships:
            adjacency.setdefault(rel["fk_table"], set()).add(rel["pk_table"])
            adjacency.setdefault(rel["pk_table"], set()).add(rel["fk_table"])
        visited: set[str] = set()
        components: list[set[str]] = []
        for table in sorted(adjacency):
            if table in visited:
                continue
            component: set[str] = set()
            queue: deque[str] = deque([table])
            visited.add(table)
            while queue:
                current = queue.popleft()
                component.add(current)
                for neighbor in adjacency.get(current, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            components.append(component)
        return components

    def _module_for_table(self, table: str) -> str:
        table = table.strip()
        if "_" in table:
            prefix = table.split("_", 1)[0]
            return _clean_module(prefix)
        if "." in table:
            prefix = table.split(".", 1)[0]
            return _clean_module(prefix)
        return "core"

    def _tables_by_module(self, subset: set[str] | None = None) -> dict[str, list[str]]:
        tables = subset if subset is not None else self.tables
        groups: dict[str, list[str]] = defaultdict(list)
        for table in tables:
            groups[self._module_for_table(table)].append(table)
        return {
            module: sorted(items, key=lambda t: (-self._table_degree().get(t, 0), t.lower()))
            for module, items in sorted(groups.items())
        }

    def _mermaid_table_ids(self, tables: set[str]) -> dict[str, str]:
        used: Counter[str] = Counter()
        mapping = {}
        for table in sorted(tables, key=str.lower):
            base = _mermaid_id(table)
            used[base] += 1
            mapping[table] = base if used[base] == 1 else f"{base}_{used[base]}"
        return mapping

    def _graph_groups(self) -> list[dict[str, Any]]:
        groups = []
        for module, tables in self._tables_by_module().items():
            groups.append({"id": module, "type": "module", "tables": tables, "table_count": len(tables)})
        domain_counts = Counter(str(item.get("semantic_domain") or "Unknown") for item in self.lcil_insights)
        for domain, count in domain_counts.items():
            groups.append({"id": domain, "type": "ontology_domain", "table_count": count})
        return groups

    def _ontology_summary(self) -> dict[str, Any]:
        domain_counts = Counter(str(item.get("semantic_domain") or "Unknown") for item in self.lcil_insights)
        entity_counts = Counter(str(item.get("suggested_entity") or "Unknown") for item in self.lcil_insights)
        tags = Counter(tag for item in self.lcil_insights for tag in item.get("ontology_tags") or [])
        return {
            "domain_counts": dict(domain_counts),
            "entity_counts": dict(entity_counts),
            "ontology_tag_counts": dict(tags),
            "insight_count": len(self.lcil_insights),
        }


# ----------------------------------------------------------------------
# Standalone helpers
# ----------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_float(value: Any) -> float:
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception:
        return 0.0


def _class_rank(rel_class: str) -> int:
    return {
        TRUE_FK: 0,
        POSSIBLE_REFERENCE: 1,
        SEMANTICALLY_RELATED: 2,
        SHARED_ENTITY_DOMAIN: 3,
    }.get(rel_class, 9)


def _clean_module(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower()
    return cleaned or "core"


def _file_safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "module"


def _dbml_ident(value: str) -> str:
    value = str(value)
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
        return value
    return '"' + value.replace('"', '\\"') + '"'


def _dbml_type(value: Any) -> str:
    key = str(value or "").lower()
    if "int" in key:
        return "int"
    if "big" in key:
        return "bigint"
    if "decimal" in key or "numeric" in key:
        return "decimal"
    if "float" in key or "double" in key or "real" in key:
        return "float"
    if "bool" in key:
        return "boolean"
    if "timestamp" in key or "datetime" in key:
        return "timestamp"
    if key == "date":
        return "date"
    return "varchar"


def _mermaid_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value)).upper()
    if not cleaned:
        cleaned = "UNKNOWN_TABLE"
    if cleaned[0].isdigit():
        cleaned = "T_" + cleaned
    return cleaned


def _mermaid_column(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value))
    if not cleaned:
        cleaned = "unknown_column"
    if cleaned[0].isdigit():
        cleaned = "c_" + cleaned
    return cleaned


def _mermaid_label(value: str) -> str:
    return str(value).replace('"', "'").replace("\n", " ")[:60]


def _mermaid_type(value: Any) -> str:
    key = str(value or "").lower()
    if "int" in key:
        return "int"
    if "decimal" in key or "numeric" in key or "float" in key or "double" in key:
        return "float"
    if "bool" in key:
        return "boolean"
    if "date" in key or "time" in key:
        return "datetime"
    return "string"


def _drawio_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_")
    return cleaned or "node"


def _mx_cell(cell_id: str, value: str = "", parent: str | None = None) -> str:
    attrs = [f'id="{escape(cell_id, quote=True)}"']
    if value:
        attrs.append(f'value="{escape(value, quote=True)}"')
    if parent:
        attrs.append(f'parent="{escape(parent, quote=True)}"')
    return "<mxCell " + " ".join(attrs) + "/>"


def _mx_vertex(cell_id: str, value: str, x: int, y: int, width: int, height: int, style: str) -> str:
    return (
        f'<mxCell id="{escape(cell_id, quote=True)}" value="{escape(value, quote=True)}" '
        f'style="{escape(style, quote=True)}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{width}" height="{height}" as="geometry"/>'
        "</mxCell>"
    )


def _mx_edge(cell_id: str, value: str, source: str, target: str, style: str) -> str:
    return (
        f'<mxCell id="{escape(cell_id, quote=True)}" value="{escape(value, quote=True)}" '
        f'style="{escape(style, quote=True)}" edge="1" parent="1" '
        f'source="{escape(source, quote=True)}" target="{escape(target, quote=True)}">'
        '<mxGeometry relative="1" as="geometry"/>'
        "</mxCell>"
    )


def _drawio_file(name: str, cells: list[str]) -> str:
    cell_xml = "\n".join(cells)
    diagram_id = _drawio_id(name).lower()
    return f"""<mxfile host="app.diagrams.net" modified="{_now()}" agent="ERVE" version="22.1.0" type="device">
  <diagram name="{escape(name, quote=True)}" id="{diagram_id}">
    <mxGraphModel dx="1280" dy="720" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1600" pageHeight="1200" math="0" shadow="0">
      <root>
{textwrap.indent(cell_xml, "        ")}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""


def _pyplot():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt
