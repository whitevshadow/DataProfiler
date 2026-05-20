from __future__ import annotations

import json
from pathlib import Path

from profiler import services


def test_dbml_web_renderer_text_interactive_success() -> None:
    dbml = """
Table users {
  id int [pk]
  name varchar
}

Table posts {
  id int [pk]
  user_id int
}

Ref: posts.user_id > users.id
""".strip()

    result = services.dbml_web_renderer(
        source_type="text",
        dbml_text=dbml,
        viewer_mode="interactive",
        layout="horizontal",
    )

    assert result["status"] == "success"
    assert result["stats"]["tables"] == 2
    assert result["stats"]["relationships"] == 1
    assert "<html>" in result["viewer_html"]
    assert "ReactFlow" in result["react_component"]


def test_dbml_web_renderer_invalid_dbml_returns_error() -> None:
    result = services.dbml_web_renderer(
        source_type="text",
        dbml_text="this is not dbml",
    )

    assert result["status"] == "error"
    assert "Invalid DBML syntax" in result["message"]


def test_dbml_web_renderer_file_and_unresolved_fk(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.dbml"
    schema_path.write_text(
        """
Table orders {
  id int [pk]
  customer_id int
}

Ref: orders.customer_id > customers.id
""".strip(),
        encoding="utf-8",
    )

    result = services.dbml_web_renderer(
        source_type="file",
        file_path=str(schema_path),
        viewer_mode="readonly",
    )

    assert result["status"] == "success"
    assert result["stats"]["unresolved_relationships"] == 1
    assert any(rel["status"] == "unresolved" for rel in result["relationships"])


def test_dbml_web_renderer_relationship_json_conversion(tmp_path: Path) -> None:
    rel_path = tmp_path / "relationship.json"
    rel_path.write_text(
        json.dumps(
            {
                "relationships": [
                    {
                        "fk_table": "posts",
                        "fk_column": "user_id",
                        "pk_table": "users",
                        "pk_column": "id",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = services.dbml_web_renderer(
        source_type="file",
        file_path=str(rel_path),
        viewer_mode="embed",
    )

    assert result["status"] == "success"
    assert result["stats"]["tables"] == 2
    assert "<iframe" in result["viewer_html"]


def test_dbml_web_renderer_detects_circular_refs() -> None:
    dbml = """
Table a {
  id int [pk]
  b_id int
}

Table b {
  id int [pk]
  a_id int
}

Ref: a.b_id > b.id
Ref: b.a_id > a.id
""".strip()

    result = services.dbml_web_renderer(source_type="text", dbml_text=dbml)

    assert result["status"] == "success"
    assert any("Circular references detected" in w for w in result.get("warnings", []))
    assert any(rel.get("circular") for rel in result["relationships"])


def test_display_dbml_returns_visual_component_payload(tmp_path: Path) -> None:
        out_base = tmp_path / "output"
        schema_path = out_base / "erd" / "schema.dbml"
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(
                """
Table users {
    id int [pk]
    name varchar
}

Table posts {
    id int [pk]
    user_id int
}

Ref: posts.user_id > users.id
""".strip(),
                encoding="utf-8",
        )

        result = services.display_dbml(output_base=str(out_base))

        assert result["status"] == "success"
        assert result["render_type"] == "dbml_visual"
        assert "Table users" in result["dbml_text"]
        assert isinstance(result["viewer_html"], str) and result["viewer_html"]
        assert isinstance(result["react_component"], str) and "ReactFlow" in result["react_component"]
        assert isinstance(result["graph_nodes"], list) and len(result["graph_nodes"]) == 2
        assert isinstance(result["graph_edges"], list) and len(result["graph_edges"]) == 1
        assert result["component"]["type"] == "component"
        assert result["component"]["component"] == "dbml_viewer"
