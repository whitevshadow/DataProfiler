from __future__ import annotations

import json
from pathlib import Path

from profiler.erve import ERVEConfig, ERVEEngine
from profiler import services


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _profile(table: str, columns: list[tuple[str, str]], pk_columns: list[str]) -> dict:
    return {
        "table_name": table,
        "table_profile": {
            "column_count": len(columns),
            "pk_candidates": pk_columns,
            "fk_candidates": [],
        },
        "columns": [
            {
                "column_name": name,
                "original_name": name,
                "position": index,
                "physical_type": physical_type,
                "pk_candidate": name in pk_columns,
                "fk_candidate": False,
            }
            for index, (name, physical_type) in enumerate(columns)
        ],
    }


def _sample_output(tmp_path: Path) -> tuple[Path, Path]:
    output = tmp_path / "output"
    relationships_path = output / "relationships" / "relationships.json"
    _write_json(
        relationships_path,
        {
            "metadata": {"total_relationships": 4, "true_fk_count": 1},
            "relationships": [
                {
                    "fk_table": "orders",
                    "fk_column": "customer_id",
                    "pk_table": "customers",
                    "pk_column": "customer_id",
                    "relationship_class": "TRUE_FK",
                    "confidence_score": 0.96,
                    "semantic_similarity": 0.91,
                    "containment_ratio": 1.0,
                },
                {
                    "fk_table": "orders",
                    "fk_column": "status",
                    "pk_table": "invoices",
                    "pk_column": "status",
                    "relationship_class": "SEMANTICALLY_RELATED",
                    "confidence_score": 0.82,
                    "semantic_similarity": 0.88,
                    "containment_ratio": 0.2,
                },
                {
                    "fk_table": "orders",
                    "fk_column": "delivery_method_id",
                    "pk_table": "delivery_methods",
                    "pk_column": "delivery_method_id",
                    "relationship_class": "SHARED_ENTITY_DOMAIN",
                    "confidence_score": 0.74,
                    "semantic_similarity": 0.81,
                    "containment_ratio": 0.5,
                },
                {
                    "fk_table": "orders",
                    "fk_column": "payment_method_id",
                    "pk_table": "payment_methods",
                    "pk_column": "payment_method_id",
                    "relationship_class": "POSSIBLE_REFERENCE",
                    "confidence_score": 0.31,
                    "semantic_similarity": 0.71,
                    "containment_ratio": 0.3,
                },
            ],
        },
    )
    profiles = output / "profiles"
    _write_json(
        profiles / "orders.profile.json",
        _profile(
            "orders",
            [
                ("order_id", "integer"),
                ("customer_id", "integer"),
                ("status", "string"),
                ("delivery_method_id", "integer"),
                ("payment_method_id", "integer"),
            ],
            ["order_id"],
        ),
    )
    _write_json(
        profiles / "customers.profile.json",
        _profile("customers", [("customer_id", "integer"), ("customer_name", "string")], ["customer_id"]),
    )
    _write_json(
        profiles / "invoices.profile.json",
        _profile("invoices", [("invoice_id", "integer"), ("status", "string")], ["invoice_id"]),
    )
    _write_json(
        output / "low_cardinality" / "low_cardinality_insights.json",
        {
            "insights": [
                {
                    "table_name": "orders",
                    "column_name": "status",
                    "semantic_domain": "WorkflowState",
                    "suggested_entity": "OrderStatus",
                    "confidence": 0.91,
                    "ontology_tags": ["workflow"],
                }
            ]
        },
    )
    return output, relationships_path


def test_erve_full_export_generates_expected_artifacts(tmp_path: Path) -> None:
    output, relationships_path = _sample_output(tmp_path)
    engine = ERVEEngine(
        config=ERVEConfig(
            relationships_path=relationships_path,
            output_base=output,
            min_confidence=0.5,
        )
    )

    result = engine.generate_full_export()

    assert result["success"] is True
    assert (output / "erd" / "schema.dbml").exists()
    assert (output / "erd" / "schema.mmd").exists()
    assert (output / "erd" / "erd.html").exists()
    assert (output / "drawio" / "semantic_erd.drawio").exists()
    assert (output / "drawio" / "ontology.drawio").exists()
    assert (output / "charts" / "relationship_summary.png").stat().st_size > 0
    assert (output / "charts" / "confidence_histogram.png").stat().st_size > 0
    assert (output / "charts" / "relationship_heatmap.png").stat().st_size > 0
    assert (output / "graph" / "graph.json").exists()
    assert (output / "graph" / "graph.html").exists()
    assert (output / "scripts" / "generate_dbml.py").exists()

    dbml = (output / "erd" / "schema.dbml").read_text(encoding="utf-8")
    assert "Ref: orders.customer_id > customers.customer_id" in dbml
    assert "orders.status > invoices.status" not in dbml

    mermaid = (output / "erd" / "schema.mmd").read_text(encoding="utf-8")
    assert "CUSTOMERS ||--o{ ORDERS" in mermaid
    assert "INVOICES ||--o{ ORDERS" not in mermaid

    graph = json.loads((output / "graph" / "graph.json").read_text(encoding="utf-8"))
    edge_types = {edge["type"] for edge in graph["edges"]}
    assert edge_types == {"TRUE_FK", "SEMANTICALLY_RELATED", "SHARED_ENTITY_DOMAIN"}
    assert graph["metrics"]["orphan_table_count"] >= 0


def test_service_generate_er_visualizations_mode_dbml(tmp_path: Path) -> None:
    output, relationships_path = _sample_output(tmp_path)

    result = services.generate_er_visualizations(
        relationships_path=str(relationships_path),
        output_base=str(output),
        mode="dbml",
    )

    assert result["success"] is True
    assert result["mode"] == "dbml"
    assert Path(result["outputs"]["dbml"]).exists()
