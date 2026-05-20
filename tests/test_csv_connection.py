from __future__ import annotations

from pathlib import Path

from connector.connection_manager import ConnectionManager
from connector.registry import registry


def test_csv_connection_can_be_registered_and_tested(tmp_path: Path) -> None:
    csv_path = tmp_path / "customers.csv"
    csv_path.write_text("customer_id,name\n1,Ada\n", encoding="utf-8")

    manager = ConnectionManager()
    manager.register(
        connection_id="local-csv",
        scheme="csv",
        credentials={"path": str(csv_path), "encoding": "utf-8"},
        display_name="Local CSV",
    )

    result = manager.test("local-csv")

    assert result.success is True
    assert manager.get("local-csv").is_healthy is True


def test_registry_resolves_csv_to_file_connector() -> None:
    connector = registry.get("csv")

    assert connector.__class__.__name__ == "FileConnector"
