"""Service functions exposed through the profiler MCP server."""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".csv": "csv",
    ".json": "json",
    ".jsonl": "json",
    ".ndjson": "json",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".xlsx": "excel",
    ".xls": "excel",
    ".sqlite": "sqlite",
    ".sqlite3": "sqlite",
    ".db": "sqlite",
}


def resolve_path(path: str | Path | None, default: str | Path = ".") -> Path:
    """Resolve a user path relative to the current process working directory."""
    raw = Path(path) if path not in (None, "") else Path(default)
    if raw.is_absolute():
        return raw
    return (Path.cwd() / raw).resolve()


def relative_to_cwd(path: str | Path) -> str:
    """Return a compact path when possible, absolute otherwise."""
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)


def list_supported_files(path: str = ".") -> list[dict[str, Any]]:
    """Return supported data files under a file or directory path."""
    target = resolve_path(path)
    files = _iter_supported_files(target)
    results: list[dict[str, Any]] = []

    for file_path in files:
        fmt = _detect_format(file_path)
        stat = file_path.stat()
        item: dict[str, Any] = {
            "path": str(file_path),
            "display_path": relative_to_cwd(file_path),
            "name": file_path.name,
            "detected_format": fmt,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 4),
        }
        if fmt == "sqlite":
            item["table_count"] = _sqlite_table_count(file_path)
        results.append(item)

    return sorted(results, key=lambda item: item["path"].lower())


def profile_file(
    path: str,
    sample_size: int = 1000,
    output_base: str = "output",
) -> dict[str, Any]:
    """Profile one supported file and write canonical/profile artifacts."""
    from profiler.engines import registry
    from profiler.profiling.profiling_engine import profile_canonical_table

    file_path = resolve_path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not file_path.is_file():
        raise ValueError(f"Expected a file path: {file_path}")

    file_format = _detect_format(file_path)
    if file_format == "unknown":
        raise ValueError(f"Unsupported file extension: {file_path.suffix}")

    output_root = resolve_path(output_base)
    canonical_dir = output_root / "canonical"
    profiles_dir = output_root / "profiles"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    profiles_dir.mkdir(parents=True, exist_ok=True)

    table_name = file_path.stem
    table = registry.parse(
        file_path=file_path,
        file_format=file_format,
        encoding="utf-8",
        sample_size=sample_size,
    )
    canonical_path = canonical_dir / f"{table_name}.canonical.json"
    table.save_canonical_json(
        canonical_path,
        table_id=table_name,
        table_name=table_name,
    )

    profile = profile_canonical_table(canonical_path, profiles_dir)
    profile_path = profiles_dir / f"{profile.table_name}.profile.json"
    return _profile_result(
        profile_data=json.loads(profile.model_dump_json()),
        source_path=file_path,
        canonical_path=canonical_path,
        profile_path=profile_path,
    )


def profile_directory(
    path: str,
    sample_size: int = 1000,
    output_base: str = "output",
    max_workers: int = 4,
) -> dict[str, Any]:
    """Profile all supported files in a directory."""
    del max_workers  # Kept in the public tool contract for future parallel execution.
    target = resolve_path(path)
    files = _iter_supported_files(target)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for file_path in files:
        try:
            results.append(profile_file(str(file_path), sample_size, output_base))
        except Exception as exc:  # pragma: no cover - returned to agent/user
            log.exception("Failed to profile %s", file_path)
            errors.append({"path": str(file_path), "error": str(exc)})

    return {
        "success": not errors,
        "total_files": len(files),
        "profiles_generated": len(results),
        "errors": errors,
        "output_base": str(resolve_path(output_base)),
        "canonical_dir": str((resolve_path(output_base) / "canonical").resolve()),
        "profiles_dir": str((resolve_path(output_base) / "profiles").resolve()),
        "tables": [
            {
                "table_name": item["table_name"],
                "row_count_estimate": item["row_count_estimate"],
                "column_count": item["column_count"],
                "quality_score": item["quality_score"],
                "profile_path": item["profile_path"],
            }
            for item in results
        ],
    }


def enrich_relationships(
    output_base: str = "output",
    max_workers: int = 5,
) -> dict[str, Any]:
    """Run LLM description generation plus semantic relationship detection."""
    from profiling_agent import ProfilingAgent

    output_root = resolve_path(output_base)
    agent = ProfilingAgent(
        data_dir="data",
        output_base=str(output_root),
        sample_size=100,
        max_workers=max_workers,
    )
    description_summary = agent._stage4_llm_descriptions()
    relationship_summary = agent._stage5_relationship_detection()
    relationships_path = output_root / "relationships" / "relationships.json"
    return {
        "success": relationships_path.exists(),
        "descriptions": description_summary,
        "relationships": relationship_summary,
        "relationships_path": str(relationships_path.resolve()),
    }


def enrich_low_cardinality(
    output_base: str = "output",
    batch_size: int = 10,
    max_workers: int = 5,
    provider: str = "nvidia",
    model: str | None = None,
    min_confidence: float = 0.6,
) -> dict[str, Any]:
    """
    Enrich low-cardinality columns with semantic intelligence using LLM.
    
    Args:
        output_base: Base output directory
        batch_size: Number of columns per LLM batch
        max_workers: Max parallel workers
        provider: LLM provider (nvidia, openai, etc.)
        model: Optional specific model name
        min_confidence: Minimum confidence threshold
        
    Returns:
        Result dictionary with paths and statistics
    """
    from profiler.lcil import enrich_low_cardinality_intelligence
    
    return enrich_low_cardinality_intelligence(
        output_base=output_base,
        batch_size=batch_size,
        max_workers=max_workers,
        provider=provider,
        model=model,
        min_confidence=min_confidence,
    )


def get_quality_summary(
    table_name: str | None = None,
    profile_path: str | None = None,
) -> dict[str, Any]:
    """Summarize quality metrics from one profile or all profiles."""
    profiles = _load_profiles(table_name=table_name, profile_path=profile_path)
    summaries = [_quality_from_profile(profile) for profile in profiles]

    total_flags = sum(item["total_quality_flags"] for item in summaries)
    total_columns = sum(item["column_count"] for item in summaries)
    columns_with_issues = sum(item["columns_with_issues"] for item in summaries)

    return {
        "table_count": len(summaries),
        "columns_profiled": total_columns,
        "columns_with_issues": columns_with_issues,
        "total_quality_flags": total_flags,
        "avg_quality_score": round(
            sum(item["quality_score"] for item in summaries) / len(summaries),
            4,
        )
        if summaries
        else 0.0,
        "tables": summaries,
    }


def get_table_relationships(
    table_name: str | None = None,
    relationship_class: str | None = None,
) -> dict[str, Any]:
    """Return relationships filtered by table and/or relationship class."""
    relationships_path = resolve_path("output") / "relationships" / "relationships.json"
    if not relationships_path.exists():
        raise FileNotFoundError(f"Relationships file not found: {relationships_path}")

    data = _read_json(relationships_path)
    relationships = data.get("relationships", [])
    if table_name:
        table_key = table_name.lower()
        relationships = [
            rel
            for rel in relationships
            if rel.get("fk_table", "").lower() == table_key
            or rel.get("pk_table", "").lower() == table_key
        ]
    if relationship_class:
        class_key = relationship_class.upper()
        relationships = [
            rel
            for rel in relationships
            if str(rel.get("relationship_class", "")).upper() == class_key
        ]

    class_counts = Counter(rel.get("relationship_class", "UNKNOWN") for rel in relationships)
    related_tables = sorted(
        {
            rel.get("fk_table")
            for rel in relationships
            if rel.get("fk_table")
        }
        | {
            rel.get("pk_table")
            for rel in relationships
            if rel.get("pk_table")
        }
    )
    return {
        "relationships_path": str(relationships_path.resolve()),
        "total_relationships": len(relationships),
        "class_counts": dict(class_counts),
        "related_tables": related_tables,
        "relationships": relationships[:100],
        "truncated": len(relationships) > 100,
    }


def generate_erd(
    relationships_path: str = "output/relationships/relationships.json",
    output_dir: str = "output/visualizations",
) -> dict[str, Any]:
    """Generate an interactive Mermaid ERD HTML file."""
    rel_path = resolve_path(relationships_path)
    out_dir = resolve_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not rel_path.exists():
        raise FileNotFoundError(f"Relationships file not found: {rel_path}")

    data = _read_json(rel_path)
    relationships = data.get("relationships", [])
    true_fks = [rel for rel in relationships if rel.get("relationship_class") == "TRUE_FK"]
    tables = sorted(
        {
            rel.get("fk_table")
            for rel in true_fks
            if rel.get("fk_table")
        }
        | {
            rel.get("pk_table")
            for rel in true_fks
            if rel.get("pk_table")
        }
    )
    html_path = out_dir / "erd_diagram.html"
    html_path.write_text(
        _render_erd_html(true_fks=true_fks, tables=tables, source_path=rel_path),
        encoding="utf-8",
    )

    return {
        "success": True,
        "relationships_path": str(rel_path.resolve()),
        "erd_path": str(html_path.resolve()),
        "tables": len(tables),
        "true_fk_relationships": len(true_fks),
    }


def _iter_supported_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if _detect_format(target) != "unknown" else []
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {target}")
    if not target.is_dir():
        raise ValueError(f"Expected file or directory: {target}")
    return [
        path
        for path in target.rglob("*")
        if path.is_file() and _detect_format(path) != "unknown"
    ]


def _detect_format(path: Path) -> str:
    return SUPPORTED_EXTENSIONS.get(path.suffix.lower(), "unknown")


def _sqlite_table_count(path: Path) -> int:
    try:
        import sqlite3

        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
            ).fetchone()
        return int(row[0] if row else 0)
    except Exception:
        return 0


def _profile_result(
    profile_data: dict[str, Any],
    source_path: Path,
    canonical_path: Path,
    profile_path: Path,
) -> dict[str, Any]:
    table_profile = profile_data.get("table_profile", {})
    return {
        "success": True,
        "table_name": profile_data.get("table_name"),
        "source_path": str(source_path.resolve()),
        "canonical_path": str(canonical_path.resolve()),
        "profile_path": str(profile_path.resolve()),
        "row_count_estimate": table_profile.get("row_count_estimate"),
        "column_count": table_profile.get("column_count", 0),
        "quality_score": table_profile.get("quality_score", 0.0),
        "pk_candidates": table_profile.get("pk_candidates", []),
        "fk_candidates": table_profile.get("fk_candidates", []),
        "columns_with_issues": table_profile.get("columns_with_issues", 0),
        "total_quality_flags": table_profile.get("total_quality_flags", 0),
    }


def _load_profiles(
    table_name: str | None,
    profile_path: str | None,
) -> list[dict[str, Any]]:
    if profile_path:
        return [_read_json(resolve_path(profile_path))]

    profiles_dir = resolve_path("output") / "profiles"
    if not profiles_dir.exists():
        raise FileNotFoundError(f"Profiles directory not found: {profiles_dir}")

    profile_files = sorted(profiles_dir.glob("*.profile.json"))
    profiles = [_read_json(path) for path in profile_files]
    if table_name:
        table_key = table_name.lower()
        profiles = [
            profile
            for profile in profiles
            if profile.get("table_name", "").lower() == table_key
        ]
    return profiles


def _quality_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    table_profile = profile.get("table_profile", {})
    columns = profile.get("columns", [])
    top_issues = []
    for column in columns:
        flags = column.get("quality_flags") or []
        if flags:
            top_issues.append(
                {
                    "column_name": column.get("column_name"),
                    "quality_score": column.get("quality_score"),
                    "quality_flags": flags,
                }
            )

    return {
        "table_name": profile.get("table_name"),
        "row_count_estimate": table_profile.get("row_count_estimate"),
        "column_count": table_profile.get("column_count", len(columns)),
        "quality_score": table_profile.get("quality_score", 0.0),
        "completeness_score": table_profile.get("completeness_score", 0.0),
        "columns_with_issues": table_profile.get("columns_with_issues", 0),
        "total_quality_flags": table_profile.get("total_quality_flags", 0),
        "top_issues": top_issues[:10],
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _clean_mermaid_id(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned or "unknown_table"


def _render_erd_html(
    true_fks: list[dict[str, Any]],
    tables: list[str],
    source_path: Path,
) -> str:
    lines = ["erDiagram"]
    if true_fks:
        for rel in true_fks:
            fk_table = _clean_mermaid_id(str(rel.get("fk_table", "unknown")))
            pk_table = _clean_mermaid_id(str(rel.get("pk_table", "unknown")))
            fk_column = str(rel.get("fk_column", "fk"))
            pk_column = str(rel.get("pk_column", "pk"))
            label = f"{fk_column} -> {pk_column}".replace('"', "'")
            lines.append(f'    {fk_table} }}o--|| {pk_table} : "{label}"')
    else:
        lines.append('    EMPTY ||--|| EMPTY : "no TRUE_FK relationships"')
    mermaid_code = "\n".join(lines)
    table_count = len(tables)
    rel_count = len(true_fks)
    source_display = relative_to_cwd(source_path)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Entity Relationship Diagram</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Segoe UI, Arial, sans-serif;
      background: #f4f7fb;
      color: #1b2733;
    }}
    header {{
      padding: 24px 32px;
      background: #1f2937;
      color: #fff;
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; font-weight: 650; }}
    .meta {{ color: #d1d5db; font-size: 14px; }}
    main {{ padding: 24px; }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      max-width: 760px;
      margin-bottom: 18px;
    }}
    .stat {{
      border: 1px solid #d9e2ef;
      border-radius: 8px;
      background: #fff;
      padding: 14px 16px;
    }}
    .label {{ color: #5b6777; font-size: 13px; }}
    .value {{ margin-top: 4px; font-size: 24px; font-weight: 700; }}
    .diagram {{
      overflow: auto;
      min-height: 640px;
      border: 1px solid #d9e2ef;
      border-radius: 8px;
      background: #fff;
      padding: 24px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Entity Relationship Diagram</h1>
    <div class="meta">Source: {source_display}</div>
  </header>
  <main>
    <section class="stats">
      <div class="stat"><div class="label">Tables</div><div class="value">{table_count}</div></div>
      <div class="stat"><div class="label">TRUE_FK Relationships</div><div class="value">{rel_count}</div></div>
    </section>
    <section class="diagram">
      <pre class="mermaid">
{mermaid_code}
      </pre>
    </section>
  </main>
  <script>
    mermaid.initialize({{
      startOnLoad: true,
      theme: "default",
      er: {{ useMaxWidth: false }}
    }});
  </script>
</body>
</html>
"""
