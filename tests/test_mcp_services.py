from __future__ import annotations

import json
from pathlib import Path

from file_profiler import services


def test_list_supported_files_single_file():
    files = services.list_supported_files("data/warehouse_colors.csv")

    assert len(files) == 1
    assert files[0]["detected_format"] == "csv"
    assert files[0]["name"] == "warehouse_colors.csv"


def test_profile_file_writes_artifacts(tmp_path):
    result = services.profile_file(
        "data/warehouse_colors.csv",
        sample_size=20,
        output_base=str(tmp_path),
    )

    assert result["success"] is True
    assert result["table_name"] == "warehouse_colors"
    assert result["column_count"] > 0
    assert Path(result["canonical_path"]).exists()
    assert Path(result["profile_path"]).exists()


def test_generate_erd_writes_html(tmp_path):
    relationships_path = tmp_path / "relationships.json"
    relationships_path.write_text(
        json.dumps(
            {
                "metadata": {"total_relationships": 1, "true_fk_count": 1},
                "relationships": [
                    {
                        "fk_table": "orders",
                        "fk_column": "customer_id",
                        "pk_table": "customers",
                        "pk_column": "customer_id",
                        "relationship_class": "TRUE_FK",
                        "confidence_score": 0.98,
                        "semantic_similarity": 0.9,
                        "containment_ratio": 1.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = services.generate_erd(str(relationships_path), str(tmp_path / "viz"))

    erd_path = Path(result["erd_path"])
    assert result["success"] is True
    assert result["true_fk_relationships"] == 1
    assert erd_path.exists()
    assert "orders }o--|| customers" in erd_path.read_text(encoding="utf-8")


def test_quality_summary_reads_existing_profile():
    summary = services.get_quality_summary(profile_path="output/profiles/warehouse_colors.profile.json")

    assert summary["table_count"] == 1
    assert summary["columns_profiled"] > 0
    assert summary["tables"][0]["table_name"] == "warehouse_colors"
