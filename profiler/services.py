"""Service functions exposed through the profiler MCP server."""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

# Session and UI state tracking
from session.session_state import SessionStateManager
from ui.ui_state_builder import UIStateBuilder

log = logging.getLogger(__name__)

# Initialize global state managers
_session_manager = SessionStateManager()
_ui_builder = UIStateBuilder()

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
    if path in (None, ""):
        raw = Path(default)
    else:
        normalized = _normalize_virtual_path(str(path))
        raw = Path(normalized)
    if raw.is_absolute():
        return raw
    return (Path.cwd() / raw).resolve()


def _normalize_virtual_path(value: str) -> str:
    """Map common agent-emitted virtual paths to local workspace-relative paths."""
    text = value.strip()
    unix = text.replace("\\", "/")
    lowered = unix.lower()

    # Root path "/" should map to workspace data directory, not drive root
    if unix == "/":
        return "data"

    # Some agent/tooling layers emit Linux sandbox paths on Windows hosts.
    if "home/user/data" in lowered:
        return "data"

    # Frontend upload target conventions may use container-style /data/* paths.
    if lowered == "/data":
        return "data"
    if lowered.startswith("/data/"):
        return unix.lstrip("/")

    return text


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

    # Calculate metrics
    total_tables = len(results)
    total_rows = sum(r.get("row_count_estimate", 0) for r in results)
    total_columns = sum(r.get("column_count", 0) for r in results)
    
    # Update session state
    session = _session_manager.get_current()
    session.mark_profile_complete(
        profile_path=str((resolve_path(output_base) / "profiles").resolve()),
        tables=total_tables,
        rows=total_rows,
        columns=total_columns
    )
    session.output_base = str(resolve_path(output_base))
    session.dataset_path = str(target)
    _session_manager.save()
    
    # Emit UI state event
    _ui_builder.emit_profile_complete(
        tables=total_tables,
        rows=total_rows,
        columns=total_columns,
        status=f"Profiled {total_tables} tables"
    )

    output_root = resolve_path(output_base)
    pk_context_path = _write_pk_context(output_root)
    profiler_context_path = None
    try:
        from profiler.profiler_agent_context import build_profiler_context
        build_profiler_context(str(output_root))
        profiler_context_path = str((output_root / "profiler_context.json").resolve())
    except Exception as exc:  # pragma: no cover
        log.warning("Failed to build profiler_context.json: %s", exc)

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
        "tables_profiled": total_tables,
        "total_rows": total_rows,
        "total_columns": total_columns,
        "pk_context_file": pk_context_path,
        "profiler_context_file": profiler_context_path,
    }


def detect_relationships(
    output_base: str = "output",
) -> dict[str, Any]:
    """Build validated downstream relationships from profiler output."""
    from relationships.production_relationship_builder import build_relationship_graph

    output_root = resolve_path(output_base)
    relationship_summary = build_relationship_graph(output_root)
    relationships_path = output_root / "relationships" / "relationships.json"

    accepted_classes = {
        "FOREIGN_KEY",
        "TRANSACTION_REFERENCE",
        "DIMENSION_REFERENCE",
        "ENUM_REFERENCE",
        "SELF_REFERENCE",
        "AUDIT_REFERENCE",
    }
    fk_count = sum(
        1
        for rel in relationship_summary.get("relationships", [])
        if rel.get("relationship_class") in accepted_classes
    )
    total_rels = len(relationship_summary.get("relationships", []))
    
    # Update session state
    session = _session_manager.get_current()
    session.mark_relationship_complete(
        relationship_path=str(relationships_path.resolve()),
        fk_count=fk_count
    )
    _session_manager.save()
    
    # Emit UI state event
    _ui_builder.emit_relationship_complete(
        fk_count=fk_count,
        status=f"Detected {fk_count} validated relationships"
    )

    summary = (
        f"Built {fk_count} validated relationship edges, "
        f"{len(relationship_summary.get('pk', []))} primary keys, "
        f"{len(relationship_summary.get('composite_pk', []))} composite keys, "
        f"and {len(relationship_summary.get('invalid_matches', []))} invalid matches"
    )
    
    return {
        "success": relationships_path.exists(),
        "summary": summary,
        "relationships": relationship_summary,
        "relationships_path": str(relationships_path.resolve()),
        "true_fk_count": fk_count,
        "total_relationships": total_rels,
    }


def enrich_descriptions(
    output_base: str = "output",
    max_workers: int = 5,
) -> dict[str, Any]:
    """Generate LLM semantic descriptions for columns (enrichment only, NO relationship detection).
    
    This function ONLY adds semantic meaning to existing profiles.
    It does NOT create relationships - that is the job of detect_relationships().
    """
    from profiling_agent import ProfilingAgent

    output_root = resolve_path(output_base)
    agent = ProfilingAgent(
        data_dir="data",
        output_base=str(output_root),
        sample_size=100,
        max_workers=max_workers,
    )
    
    # Stage 3 ONLY - descriptions
    description_summary = agent._stage3_llm_descriptions()
    descriptions_path = output_root / "descriptions" / "descriptions.json"
    
    # Build human-readable summary
    tables_count = description_summary.get("tables_processed", 0)
    descriptions_count = description_summary.get("descriptions_generated", 0)
    
    # Update session state
    session = _session_manager.get_current()
    session.mark_enrichment_complete(enrichment_path=str(descriptions_path.resolve()))
    _session_manager.save()
    
    # Emit UI state event
    _ui_builder.emit_enrichment_complete(
        descriptions=descriptions_count,
        status=f"Generated {descriptions_count} semantic descriptions"
    )
    
    summary = f"Enriched {tables_count} tables with {descriptions_count} semantic descriptions"
    
    return {
        "success": descriptions_path.exists(),
        "summary": summary,
        "descriptions": description_summary,
        "descriptions_path": str(descriptions_path.resolve()),
        "tables_processed": tables_count,
        "descriptions_generated": descriptions_count,
    }


def enrich_relationships(
    output_base: str = "output",
    max_workers: int = 5,
) -> dict[str, Any]:
    """DEPRECATED: Use enrich_descriptions() and detect_relationships() separately.
    
    This function is kept for backward compatibility but will call both stages separately.
    """
    # Run descriptions first
    desc_result = enrich_descriptions(output_base, max_workers)
    
    # Then run relationship detection
    rel_result = detect_relationships(output_base)
    
    # Combine results
    summary = f"{desc_result['summary']}. {rel_result['summary']}"
    
    return {
        "success": desc_result["success"] and rel_result["success"],
        "summary": summary,
        "descriptions": desc_result.get("descriptions", {}),
        "relationships": rel_result.get("relationships", {}),
        "descriptions_path": desc_result.get("descriptions_path"),
        "relationships_path": rel_result.get("relationships_path"),
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
        # Automatically run relationship detection
        log.info("Relationships file not found. Running detect_relationships...")
        try:
            detect_result = detect_relationships(output_base="output")
            if not detect_result.get("success"):
                raise RuntimeError(f"Failed to generate relationships: {detect_result}")
        except FileNotFoundError as e:
            # If descriptions don't exist, run full enrichment
            log.info("Descriptions not found. Running full enrich_relationships...")
            enrich_result = enrich_relationships(output_base="output", max_workers=5)
            if not enrich_result.get("success"):
                raise RuntimeError(f"Failed to generate relationships: {enrich_result}")

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
    
    # Build human-readable summary
    summary_parts = [f"Found {len(relationships)} relationships"]
    if class_counts:
        class_breakdown = ", ".join(f"{count} {cls}" for cls, count in sorted(class_counts.items(), key=lambda x: -x[1]))
        summary_parts.append(f"({class_breakdown})")
    if related_tables:
        summary_parts.append(f"across {len(related_tables)} tables")
    
    return {
        "success": True,
        "summary": " ".join(summary_parts),
        "relationships_path": str(relationships_path.resolve()),
        "total_relationships": len(relationships),
        "class_counts": dict(class_counts),
        "related_tables": related_tables,
        "relationships": relationships[:100],
        "truncated": len(relationships) > 100,
        "note": f"Showing first 100 of {len(relationships)} relationships. Check relationships_path for full list."
    }


def generate_erd(
    relationships_path: str = "output/relationships/relationships.json",
    output_dir: str = "output/visualizations",
) -> dict[str, Any]:
    """Generate an interactive Mermaid ERD HTML file using ERVE."""
    del output_dir  # ERVE writes to output/erd to keep artifact locations stable.
    from profiler.erve import ERVEConfig, ERVEEngine

    rel_path = resolve_path(relationships_path)
    output_base = rel_path.parent.parent if rel_path.parent.name == "relationships" else resolve_path("output")
    engine = ERVEEngine(
        config=ERVEConfig(
            relationships_path=rel_path,
            output_base=output_base,
            min_confidence=0.5,
        )
    )
    mermaid_result = engine.generate_mermaid()
    html_result = engine.generate_html()
    metrics = html_result.get("metrics", {})
    return {
        "success": True,
        "relationships_path": str(rel_path.resolve()),
        "erd_path": html_result["outputs"]["html"],
        "mermaid_path": mermaid_result["outputs"]["mermaid"],
        "tables": metrics.get("table_count", 0),
        "true_fk_relationships": metrics.get("relationship_class_counts", {}).get("TRUE_FK", 0),
        "outputs": {**mermaid_result["outputs"], **html_result["outputs"]},
    }


def display_dbml(
    dbml_path: str | None = None,
    output_base: str = "output",
) -> dict[str, Any]:
    """Display existing DBML schema as an embeddable visual component payload.

    Loads existing schema.dbml without regeneration and returns viewer payload
    fields suitable for direct frontend rendering (iframe/ReactFlow/fallback).
    """
    from backend.dbml import (
        load_dbml,
        save_dbml_render,
        build_entity_cache,
        build_hover_cache,
        save_viewer_state,
    )
    
    out_base = resolve_path(output_base)
    
    # Load existing DBML
    load_result = load_dbml(dbml_path=dbml_path, output_base=out_base)

    if not load_result.get("success"):
        return {
            "status": "error",
            "message": load_result.get("error", "Failed to load DBML"),
            "hint": load_result.get("hint", ""),
        }

    dbml_content = load_result["content"]
    dbml_source_path = load_result["path"]

    # Parse DBML and build viewer payload
    try:
        web_render = dbml_web_renderer(
            source_type="text",
            dbml_text=dbml_content,
            viewer_mode="interactive",
            layout="auto",
            options={
                "zoom": True,
                "minimap": True,
                "search": True,
                "collapse_columns": True,
                "highlight_fk": True,
                "dark_mode": False,
            },
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to parse DBML: {exc}",
            "dbml_source_path": dbml_source_path,
        }

    if web_render.get("status") != "success":
        return {
            "status": "error",
            "message": web_render.get("message", "Invalid DBML syntax"),
            "warnings": web_render.get("warnings", []),
            "dbml_source_path": dbml_source_path,
        }

    graph_view = web_render.get("interactive_er_view", {})
    graph_nodes = graph_view.get("nodes", [])
    graph_edges = graph_view.get("edges", [])
    relationships = web_render.get("relationships", [])

    graph = {
        "nodes": [
            {
                "id": n.get("id"),
                "name": n.get("data", {}).get("title"),
                "type": "table",
                "columns": n.get("data", {}).get("columns", []),
            }
            for n in graph_nodes
        ],
        "edges": [
            {
                "id": f"{r.get('source')}.{r.get('source_column')}-{r.get('target')}.{r.get('target_column')}",
                "source": r.get("source"),
                "sourceColumn": r.get("source_column"),
                "target": r.get("target"),
                "targetColumn": r.get("target_column"),
                "type": "TRUE_FK",
                "cardinality": r.get("type", "1-N"),
                "status": r.get("status", "resolved"),
            }
            for r in relationships
        ],
        "metadata": {
            "tables": len(graph_nodes),
            "relationships": len(graph_edges),
        },
    }
    
    # Build caches
    try:
        entity_cache = build_entity_cache(graph, output_base=out_base)
        hover_cache = build_hover_cache(graph, entity_cache)

        # Save render graph
        render_path = save_dbml_render(graph, output_base=out_base)

        # Save all viewer state
        state_paths = save_viewer_state(graph, entity_cache, hover_cache, output_base=out_base)

    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to build viewer state: {exc}",
            "dbml_source_path": dbml_source_path,
        }

    # Update session state
    state = _session_manager.get_current()
    state.dbml_path = dbml_source_path
    _session_manager.save(state)

    viewer_html = web_render.get("viewer_html", "")
    react_component = web_render.get("react_component", "")

    return {
        "status": "success",
        "render_type": "dbml_visual",
        "dbml_text": dbml_content,
        "viewer_html": viewer_html,
        "react_component": react_component,
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "component": {
            "type": "component",
            "component": "dbml_viewer",
            "props": {
                "dbml": dbml_content,
                "viewer_html": viewer_html,
                "react_component": react_component,
                "graph_nodes": graph_nodes,
                "graph_edges": graph_edges,
            },
        },
        "dbml_source_path": dbml_source_path,
        "render_path": render_path,
        "entity_cache_path": state_paths["entity_cache"],
        "hover_cache_path": state_paths["hover_cache"],
        "relationship_tree_path": state_paths["relationship_tree"],
        "warnings": web_render.get("warnings", []),
        "stats": web_render.get("stats", {}),
    }


def dbml_web_renderer(
    source_type: str = "text",
    dbml_text: str | None = None,
    file_path: str | None = None,
    viewer_mode: str = "interactive",
    layout: str = "auto",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render DBML schema into embeddable and interactive web ER outputs.

    The tool accepts DBML text, file, or URL sources and returns parsed schema,
    table metadata, relationships, and ready-to-embed HTML/component payloads.
    """
    default_options = {
        "zoom": True,
        "minimap": True,
        "search": True,
        "collapse_columns": True,
        "highlight_fk": True,
        "dark_mode": False,
    }
    requested_options = options or {}
    merged_options = {**default_options, **requested_options}

    source_kind = (source_type or "text").strip().lower()
    mode = (viewer_mode or "interactive").strip().lower()
    layout_mode = (layout or "auto").strip().lower()

    allowed_sources = {"text", "file", "url"}
    allowed_modes = {"embed", "interactive", "readonly", "editor"}
    allowed_layouts = {"auto", "horizontal", "vertical", "clustered"}

    if source_kind not in allowed_sources:
        return {
            "status": "error",
            "message": "Invalid source_type. Expected one of: text, file, url",
        }
    if mode not in allowed_modes:
        return {
            "status": "error",
            "message": "Invalid viewer_mode. Expected one of: embed, interactive, readonly, editor",
        }
    if layout_mode not in allowed_layouts:
        return {
            "status": "error",
            "message": "Invalid layout. Expected one of: auto, horizontal, vertical, clustered",
        }

    try:
        loaded_dbml, source_meta = _load_dbml_source(
            source_type=source_kind,
            dbml_text=dbml_text,
            file_path=file_path,
        )
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    parse_result = _parse_dbml_schema(loaded_dbml)
    if not parse_result["ok"]:
        return {
            "status": "error",
            "message": parse_result.get("error", "Invalid DBML syntax"),
            "warnings": parse_result.get("warnings", []),
        }

    parsed = parse_result["parsed"]
    tables = parsed["tables"]
    relationships = parsed["refs"]
    warnings = parse_result["warnings"]

    graph_view = _build_graph_view(tables, relationships, layout_mode, merged_options)
    html_payload = _build_viewer_html(
        mode=mode,
        dbml_text=loaded_dbml,
        graph_view=graph_view,
        options=merged_options,
        warnings=warnings,
    )

    total_columns = sum(len(t.get("columns", [])) for t in tables)
    unresolved_count = sum(1 for rel in relationships if rel.get("status") == "unresolved")

    return {
        "status": "success",
        "source": source_meta,
        "schema": parsed,
        "tables": tables,
        "relationships": relationships,
        "viewer_html": html_payload["viewer_html"],
        "react_component": html_payload["react_component"],
        "embed_code": html_payload["embed_code"],
        "interactive_er_view": graph_view,
        "warnings": warnings,
        "stats": {
            "tables": len(tables),
            "columns": total_columns,
            "relationships": len(relationships),
            "unresolved_relationships": unresolved_count,
        },
    }


def _load_dbml_source(
    source_type: str,
    dbml_text: str | None,
    file_path: str | None,
) -> tuple[str, dict[str, Any]]:
    if source_type == "text":
        if not dbml_text or not dbml_text.strip():
            raise ValueError("dbml_text is required when source_type='text'")
        return dbml_text.strip(), {"source_type": "text"}

    if source_type == "url":
        url = (file_path or dbml_text or "").strip()
        if not url:
            raise ValueError("file_path or dbml_text must contain a URL when source_type='url'")
        try:
            with urlopen(url, timeout=15) as response:  # nosec B310 - user supplied URL is intentional tool behavior
                body = response.read().decode("utf-8", errors="replace")
        except URLError as exc:
            raise ValueError(f"Failed to load URL: {exc}") from exc
        dbml = _coerce_content_to_dbml(body, hint_path=url)
        return dbml, {"source_type": "url", "url": url}

    if not file_path:
        raise ValueError("file_path is required when source_type='file'")

    local_path = resolve_path(file_path)
    if not local_path.exists() or not local_path.is_file():
        raise ValueError(f"File not found: {local_path}")

    text = local_path.read_text(encoding="utf-8", errors="replace")
    dbml = _coerce_content_to_dbml(text, hint_path=str(local_path))
    return dbml, {
        "source_type": "file",
        "file_path": str(local_path.resolve()),
        "file_name": local_path.name,
    }


def _coerce_content_to_dbml(content: str, hint_path: str | None = None) -> str:
    cleaned = (content or "").strip()
    if not cleaned:
        raise ValueError("Input content is empty")

    hint = (hint_path or "").lower()
    if "table " in cleaned.lower() and "{" in cleaned:
        return cleaned

    if hint.endswith(".dbml"):
        return cleaned

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        raise ValueError("Invalid DBML syntax")

    if not isinstance(payload, dict):
        raise ValueError("Invalid DBML syntax")

    if "relationships" in payload:
        return _relationship_json_to_dbml(payload)
    if "columns" in payload or "table_name" in payload:
        return _canonical_or_profile_to_dbml(payload, hint)

    raise ValueError("Unsupported input format. Expected DBML, relationship.json, canonical.json, or profile.json")


def _relationship_json_to_dbml(payload: dict[str, Any]) -> str:
    rels = payload.get("relationships", [])
    table_columns: dict[str, dict[str, str]] = {}
    table_pk: dict[str, set[str]] = {}

    for rel in rels:
        fk_table = str(rel.get("fk_table", "")).strip()
        fk_column = str(rel.get("fk_column", "")).strip()
        pk_table = str(rel.get("pk_table", "")).strip()
        pk_column = str(rel.get("pk_column", "")).strip()
        if not fk_table or not fk_column or not pk_table or not pk_column:
            continue

        table_columns.setdefault(fk_table, {})[fk_column] = "int"
        table_columns.setdefault(pk_table, {})[pk_column] = "int"
        table_pk.setdefault(pk_table, set()).add(pk_column)

    if not table_columns:
        raise ValueError("relationship.json does not contain usable relationships")

    lines: list[str] = []
    for table_name in sorted(table_columns.keys()):
        lines.append(f"Table {table_name} {{")
        for col_name in sorted(table_columns[table_name].keys()):
            attrs: list[str] = []
            if col_name in table_pk.get(table_name, set()):
                attrs.append("pk")
            suffix = f" [{', '.join(attrs)}]" if attrs else ""
            lines.append(f"  {col_name} int{suffix}")
        lines.append("}")
        lines.append("")

    for rel in rels:
        fk_table = str(rel.get("fk_table", "")).strip()
        fk_column = str(rel.get("fk_column", "")).strip()
        pk_table = str(rel.get("pk_table", "")).strip()
        pk_column = str(rel.get("pk_column", "")).strip()
        if fk_table and fk_column and pk_table and pk_column:
            lines.append(f"Ref: {fk_table}.{fk_column} > {pk_table}.{pk_column}")

    return "\n".join(lines).strip() + "\n"


def _canonical_or_profile_to_dbml(payload: dict[str, Any], hint: str) -> str:
    table_name = str(
        payload.get("table_name")
        or payload.get("name")
        or payload.get("table")
        or "table_1"
    )

    raw_columns = payload.get("columns")
    if isinstance(raw_columns, list) and raw_columns:
        lines = [f"Table {table_name} {{"]
        for idx, col in enumerate(raw_columns):
            col_name = str(col.get("name") or col.get("column_name") or f"column_{idx + 1}")
            col_type = str(col.get("type") or col.get("data_type") or "varchar")
            attrs: list[str] = []
            if bool(col.get("pk") or col.get("is_primary_key")):
                attrs.append("pk")
            if col.get("unique"):
                attrs.append("unique")
            suffix = f" [{', '.join(attrs)}]" if attrs else ""
            lines.append(f"  {col_name} {col_type}{suffix}")
        lines.append("}")
        return "\n".join(lines)

    # profile.json often nests stats while lacking normalized column entries.
    if "table_profile" in payload and ".profile.json" in hint:
        column_count = int(payload.get("table_profile", {}).get("column_count", 0) or 0)
        lines = [f"Table {table_name} {{"]
        for idx in range(max(column_count, 1)):
            lines.append(f"  column_{idx + 1} varchar")
        lines.append("}")
        return "\n".join(lines)

    raise ValueError("canonical/profile JSON did not include recognizable columns")


def _parse_dbml_schema(dbml_text: str) -> dict[str, Any]:
    warnings: list[str] = []
    tables: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []

    table_matches = list(
        re.finditer(
            r"Table\s+([A-Za-z_][\w]*)\s*\{([\s\S]*?)\}",
            dbml_text,
            re.IGNORECASE,
        )
    )
    if not table_matches:
        return {"ok": False, "error": "Invalid DBML syntax"}

    table_name_count: dict[str, int] = {}
    table_columns_map: dict[str, set[str]] = {}

    for match in table_matches:
        table_name = match.group(1)
        body = match.group(2)
        table_name_count[table_name] = table_name_count.get(table_name, 0) + 1

        columns: list[dict[str, Any]] = []
        pk: list[str] = []
        fk: list[str] = []

        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("//"):
                continue
            if line.lower().startswith(("indexes", "note:")):
                continue

            col_match = re.match(
                r"([A-Za-z_][\w]*)\s+([^\s\[]+)(?:\s*\[([^\]]+)\])?",
                line,
            )
            if not col_match:
                warnings.append(f"Skipped malformed column definition in table {table_name}: {line}")
                continue

            col_name = col_match.group(1)
            col_type = col_match.group(2)
            attr_text = (col_match.group(3) or "").lower()
            is_pk = "pk" in attr_text or "primary key" in attr_text
            is_fk = "ref:" in attr_text or "fk" in attr_text
            columns.append(
                {
                    "name": col_name,
                    "type": col_type,
                    "pk": is_pk,
                    "fk": is_fk,
                    "nullable": "not null" not in attr_text,
                }
            )
            if is_pk:
                pk.append(col_name)
            if is_fk:
                fk.append(col_name)

        if not columns:
            return {"ok": False, "error": f"Invalid DBML syntax: table {table_name} has no valid columns"}

        if not pk:
            warnings.append(f"Missing primary key for table {table_name}")

        tables.append(
            {
                "name": table_name,
                "columns": columns,
                "pk": pk,
                "fk": fk,
            }
        )
        table_columns_map[table_name] = {c["name"] for c in columns}

    duplicates = [name for name, count in table_name_count.items() if count > 1]
    if duplicates:
        return {"ok": False, "error": f"Duplicate table names found: {', '.join(sorted(duplicates))}"}

    ref_pattern = re.compile(
        r"Ref(?:\s+[A-Za-z_][\w]*)?\s*:\s*([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\s*([<>\-]+)\s*([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)",
        re.IGNORECASE,
    )

    for match in ref_pattern.finditer(dbml_text):
        source_table = match.group(1)
        source_column = match.group(2)
        operator = match.group(3)
        target_table = match.group(4)
        target_column = match.group(5)

        rel_type = _operator_to_ref_type(operator)
        relation = _operator_to_relation(operator)
        status = "resolved"
        relation_warnings: list[str] = []

        if source_table not in table_columns_map:
            status = "unresolved"
            relation_warnings.append(f"Missing source table {source_table}")
        elif source_column not in table_columns_map[source_table]:
            status = "unresolved"
            relation_warnings.append(f"Missing source column {source_table}.{source_column}")

        if target_table not in table_columns_map:
            status = "unresolved"
            relation_warnings.append(f"Missing target table {target_table}")
        elif target_column not in table_columns_map[target_table]:
            status = "unresolved"
            relation_warnings.append(f"Missing target column {target_table}.{target_column}")

        if relation_warnings:
            warnings.extend(relation_warnings)

        refs.append(
            {
                "source": source_table,
                "source_column": source_column,
                "target": target_table,
                "target_column": target_column,
                "type": rel_type,
                "relation": relation,
                "status": status,
            }
        )

    cycle_edges = [(r["source"], r["target"]) for r in refs if r["status"] == "resolved"]
    circular_nodes = _detect_circular_tables(cycle_edges)
    if circular_nodes:
        cycle_list = ", ".join(sorted(circular_nodes))
        warnings.append(f"Circular references detected among tables: {cycle_list}")
        for rel in refs:
            if rel["source"] in circular_nodes and rel["target"] in circular_nodes:
                rel["circular"] = True

    return {"ok": True, "parsed": {"tables": tables, "refs": refs}, "warnings": warnings}


def _operator_to_ref_type(operator: str) -> str:
    if ">" in operator and "<" in operator:
        return "N-N"
    if ">" in operator:
        return "1-N"
    if "<" in operator:
        return "N-1"
    return "1-1"


def _operator_to_relation(operator: str) -> str:
    if ">" in operator and "<" in operator:
        return "many-to-many"
    if ">" in operator:
        return "many-to-one"
    if "<" in operator:
        return "one-to-many"
    return "one-to-one"


def _detect_circular_tables(edges: list[tuple[str, str]]) -> set[str]:
    graph: dict[str, list[str]] = {}
    for src, dst in edges:
        graph.setdefault(src, []).append(dst)
        graph.setdefault(dst, [])

    circular: set[str] = set()
    visited: set[str] = set()
    stack: set[str] = set()

    def dfs(node: str, path: list[str]) -> None:
        visited.add(node)
        stack.add(node)
        path.append(node)
        for nxt in graph.get(node, []):
            if nxt not in visited:
                dfs(nxt, path)
            elif nxt in stack:
                circular.update(path[path.index(nxt):])
        stack.discard(node)
        path.pop()

    for node in graph.keys():
        if node not in visited:
            dfs(node, [])

    return circular


def _build_graph_view(
    tables: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    layout: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    table_count = len(tables)
    rel_count = len(relationships)

    effective_layout = layout
    if layout == "auto":
        effective_layout = "clustered" if table_count > 500 else "horizontal"

    module_groups: dict[str, list[dict[str, Any]]] = {}
    if effective_layout == "clustered":
        for table in tables:
            module = table["name"].split("_", 1)[0]
            module_groups.setdefault(module, []).append(table)
    else:
        module_groups["default"] = tables

    nodes: list[dict[str, Any]] = []
    group_index = 0
    for module, module_tables in module_groups.items():
        for i, table in enumerate(module_tables):
            if effective_layout == "vertical":
                x = group_index * 420
                y = i * 200
            elif effective_layout == "horizontal":
                x = i * 360
                y = group_index * 240
            else:
                cols = max(1, int(math.sqrt(max(1, len(module_tables)))))
                x = group_index * 800 + (i % cols) * 320
                y = (i // cols) * 220

            nodes.append(
                {
                    "id": table["name"],
                    "position": {"x": x, "y": y},
                    "data": {
                        "title": table["name"],
                        "module": module,
                        "columns": table["columns"],
                        "pk": table["pk"],
                    },
                }
            )
        group_index += 1

    edges = [
        {
            "id": f"{r['source']}.{r['source_column']}->{r['target']}.{r['target_column']}",
            "source": r["source"],
            "target": r["target"],
            "label": f"{r['source_column']} -> {r['target_column']}",
            "relation": r["relation"],
            "type": "smoothstep",
            "status": r.get("status", "resolved"),
            "highlight": bool(options.get("highlight_fk", True)),
            "circular": bool(r.get("circular", False)),
        }
        for r in relationships
    ]

    optimizations = {
        "virtual_render": table_count > 100,
        "cluster_by_module": table_count > 500,
        "lazy_edge_loading": rel_count > 2000,
    }

    return {
        "nodes": nodes,
        "edges": edges,
        "layout": effective_layout,
        "options": options,
        "optimizations": optimizations,
    }


def _build_viewer_html(
    mode: str,
    dbml_text: str,
    graph_view: dict[str, Any],
    options: dict[str, Any],
    warnings: list[str],
) -> dict[str, str]:
    escaped_dbml = escape(dbml_text)
    graph_json = json.dumps(graph_view, ensure_ascii=False)
    search_enabled = "true" if options.get("search", True) else "false"
    minimap_enabled = "true" if options.get("minimap", True) else "false"
    dark_class = "dark" if options.get("dark_mode", False) else "light"
    minimap_component = "<MiniMap />" if options.get("minimap", True) else ""

    embed_code = (
        '<iframe src="https://dbdiagram.io" width="100%" height="900px" '
        'style="border:0;" title="DBML ER Diagram"></iframe>'
    )

    react_component = (
        "import React from 'react';\n"
        "import ReactFlow, { MiniMap, Controls, Background } from 'reactflow';\n"
        "import 'reactflow/dist/style.css';\n\n"
        "export default function DbmlWebRenderer() {\n"
        f"  const initialNodes = {json.dumps(graph_view['nodes'], indent=2)};\n"
        f"  const initialEdges = {json.dumps(graph_view['edges'], indent=2)};\n"
        "  return (\n"
        "    <div style={{ width: '100%', height: '900px' }}>\n"
        "      <ReactFlow nodes={initialNodes} edges={initialEdges} fitView>\n"
        "        <Controls />\n"
        "        <Background gap={16} />\n"
        f"        {minimap_component}\n"
        "      </ReactFlow>\n"
        "    </div>\n"
        "  );\n"
        "}\n"
    )

    toolbar_html = ""
    if mode in {"interactive", "editor", "readonly"}:
        toolbar_html = (
            '<div class="toolbar">'
            '<button onclick="zoomIn()">+</button>'
            '<button onclick="zoomOut()">-</button>'
            '<button onclick="fitView()">Fit</button>'
            '<button onclick="exportSvg()">Export SVG</button>'
            '<button onclick="exportPng()">Export PNG</button>'
            '</div>'
        )

    editor_html = ""
    if mode == "editor":
        editor_html = (
            '<div class="editor-pane">'
            '<h3>DBML Editor</h3>'
            f'<textarea id="dbmlEditor" oninput="syncEditor()">{escaped_dbml}</textarea>'
            '</div>'
        )

    readonly_banner = "<div class='mode-badge'>Read Only Mode</div>" if mode == "readonly" else ""
    warning_html = "".join(f"<li>{escape(w)}</li>" for w in warnings)

    viewer_html = f"""
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>DBML Web Renderer</title>
  <style>
    body {{ font-family: 'Segoe UI', sans-serif; margin: 0; padding: 0; background: {'#111827' if dark_class == 'dark' else '#f8fafc'}; color: {'#f8fafc' if dark_class == 'dark' else '#0f172a'}; }}
    .layout {{ display: grid; grid-template-columns: {'1fr 2fr' if mode == 'editor' else '1fr'}; gap: 12px; height: 100vh; padding: 12px; box-sizing: border-box; }}
    .viewer {{ border: 1px solid {'#334155' if dark_class == 'dark' else '#cbd5e1'}; border-radius: 10px; overflow: hidden; position: relative; background: {'#0b1220' if dark_class == 'dark' else '#ffffff'}; }}
    .toolbar {{ display: flex; gap: 8px; padding: 8px; border-bottom: 1px solid {'#334155' if dark_class == 'dark' else '#e2e8f0'}; }}
    .toolbar button {{ padding: 6px 10px; border-radius: 6px; border: 1px solid {'#64748b' if dark_class == 'dark' else '#94a3b8'}; background: {'#1e293b' if dark_class == 'dark' else '#f1f5f9'}; color: inherit; cursor: pointer; }}
    .canvas {{ height: calc(100% - 44px); overflow: auto; position: relative; }}
    .editor-pane textarea {{ width: 100%; height: calc(100vh - 72px); box-sizing: border-box; border-radius: 8px; border: 1px solid #94a3b8; padding: 8px; font-family: Consolas, monospace; }}
    .mode-badge {{ position: absolute; top: 8px; right: 8px; padding: 4px 8px; border-radius: 999px; background: #0ea5e9; color: white; font-size: 12px; }}
    .warnings {{ margin: 8px 0 0 0; padding: 8px 16px; font-size: 13px; }}
    .table-card {{ border: 1px solid {'#334155' if dark_class == 'dark' else '#cbd5e1'}; border-radius: 8px; padding: 6px 8px; margin: 6px; display: inline-block; min-width: 180px; vertical-align: top; background: {'#0f172a' if dark_class == 'dark' else '#ffffff'}; }}
    .table-title {{ font-weight: 600; margin-bottom: 4px; }}
    .col {{ font-size: 12px; opacity: 0.9; }}
  </style>
</head>
<body class=\"{dark_class}\">
  <div class=\"layout\">
    {editor_html}
    <div class=\"viewer\">
      {readonly_banner}
      {toolbar_html}
      <div class=\"canvas\" id=\"canvas\"></div>
      {"<div class='warnings'><strong>Warnings:</strong><ul>" + warning_html + "</ul></div>" if warning_html else ""}
    </div>
  </div>
  <script>
    const graph = {graph_json};
    let zoom = 1;

    function renderTables() {{
      const root = document.getElementById('canvas');
      if (!root) return;
      root.innerHTML = '';
      const query = {search_enabled} ? (document.getElementById('searchInput')?.value || '').toLowerCase() : '';
      for (const node of graph.nodes) {{
        const matches = !query || node.data.title.toLowerCase().includes(query) || node.data.columns.some(c => c.name.toLowerCase().includes(query));
        if (!matches) continue;
        const card = document.createElement('div');
        card.className = 'table-card';
        card.style.transform = `scale(${{zoom}})`;
        card.style.transformOrigin = 'top left';
        card.innerHTML = `<div class=\"table-title\">${{node.data.title}}</div>` +
          node.data.columns.map(c => `<div class=\"col\">${{c.pk ? '[PK] ' : ''}}${{c.name}} : ${{c.type}}</div>`).join('');
        root.appendChild(card);
      }}
    }}

    function zoomIn() {{ zoom = Math.min(zoom + 0.1, 2); renderTables(); }}
    function zoomOut() {{ zoom = Math.max(zoom - 0.1, 0.5); renderTables(); }}
    function fitView() {{ zoom = 1; renderTables(); }}
    function syncEditor() {{
      const editor = document.getElementById('dbmlEditor');
      if (!editor) return;
      // Live sync hook: host app can re-parse DBML here if desired.
    }}
    function exportSvg() {{
      const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='800'><text x='20' y='30'>DBML ER export placeholder</text></svg>`;
      downloadFile('diagram.svg', 'image/svg+xml', svg);
    }}
    function exportPng() {{
      const canvas = document.createElement('canvas');
      canvas.width = 1200;
      canvas.height = 800;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#111827';
      ctx.font = '24px sans-serif';
      ctx.fillText('DBML ER export placeholder', 20, 40);
      const link = document.createElement('a');
      link.download = 'diagram.png';
      link.href = canvas.toDataURL('image/png');
      link.click();
    }}
    function downloadFile(name, mime, body) {{
      const blob = new Blob([body], {{ type: mime }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.download = name;
      link.href = url;
      link.click();
      URL.revokeObjectURL(url);
    }}

    if ({search_enabled}) {{
      const toolbar = document.querySelector('.toolbar');
      if (toolbar) {{
        const search = document.createElement('input');
        search.id = 'searchInput';
        search.placeholder = 'Search tables/columns';
        search.oninput = renderTables;
        search.style.marginLeft = '8px';
        search.style.padding = '6px';
        toolbar.appendChild(search);
      }}
    }}

    if ({minimap_enabled}) {{
      // Minimap hook for host framework integration.
    }}

    renderTables();
  </script>
</body>
</html>
""".strip()

    if mode == "embed":
        viewer_html = embed_code

    return {
        "viewer_html": viewer_html,
        "react_component": react_component,
        "embed_code": embed_code,
    }


def generate_er_visualizations(
    relationships_path: str = "output/relationships/relationships.json",
    output_base: str = "output",
    mode: str = "full",
    min_confidence: float = 0.5,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Generate ERVE multi-format ER artifacts from relationship.json.
    
    Fully automatic ER visualization pipeline that generates:
    - DBML schema (dbdiagram.io format)
    - Draw.io XML (semantic ERD + ontology)
    - Mermaid ERD diagram
    - Standalone HTML preview
    - Relationship charts (PNG)
    - Graph JSON and HTML
    
    Args:
        relationships_path: Path to relationships.json file
        output_base: Base output directory (creates subdirs: erd/, drawio/, charts/, graph/)
        mode: Generation mode - "full" (default), "dbml", "drawio", "mermaid", "html", "charts", "graph"
        min_confidence: Minimum confidence threshold for relationships (default: 0.5)
        top_k: Max relationships to render. If None (default), auto-computed based on dataset:
            - < 50 tables: top_k = 50
            - 50-200 tables: top_k = 100
            - > 200 tables: top_k = 200
            - > 10000 relationships: top_k = 500
    
    Returns:
        dict with success status, outputs, and metrics
        
    Example:
        # User says: "Generate DB diagram"
        # Agent calls: generate_er_visualizations()  # All params have defaults
        
        # Explicit control:
        generate_er_visualizations(mode="dbml", top_k=50, min_confidence=0.7)
    """
    from profiler.erve import ERVEConfig, ERVEEngine

    rel_path = resolve_path(relationships_path)
    out_base = resolve_path(output_base)
    if not rel_path.exists():
        raise FileNotFoundError(f"Relationships file not found: {rel_path}")

    engine = ERVEEngine(
        config=ERVEConfig(
            relationships_path=rel_path,
            output_base=out_base,
            min_confidence=min_confidence,
            top_k=top_k,  # None is OK - will auto-compute
        )
    )
    mode_key = (mode or "full").lower().strip()
    generators = {
        "charts": engine.generate_charts,
        "relationship_chart": engine.generate_charts,
        "dbml": engine.generate_dbml,
        "drawio": engine.generate_drawio,
        "mermaid": engine.generate_mermaid,
        "html": engine.generate_html,
        "graph": engine.generate_graph,
        "scripts": engine.ensure_scripts,
        "full": engine.generate_full_export,
    }
    if mode_key not in generators:
        raise ValueError(f"Unsupported ERVE mode: {mode}")
    result = generators[mode_key]()
    return {
        **result,
        "relationships_path": str(rel_path.resolve()),
        "output_base": str(out_base.resolve()),
        "min_confidence": min_confidence,
        "top_k": top_k,
    }


def build_diagram_state(
    output_base: str = "output",
    min_confidence: float = 0.5,
    top_k: int | None = None,
    relationship_classes: list[str] | None = None,
) -> dict[str, Any]:
    """Build interactive diagram state from existing output artifacts."""
    from profiler.diagram import build_diagram_state as _build_state

    out_base = resolve_path(output_base)
    return _build_state(
        output_base=out_base,
        min_confidence=min_confidence,
        top_k=top_k,
        relationship_classes=relationship_classes,
    )


def get_table_detail(
    table_id: str,
    output_base: str = "output",
) -> dict[str, Any]:
    """Return expanded table details for the diagram explorer."""
    from profiler.diagram import get_table_detail as _get_table

    out_base = resolve_path(output_base)
    return _get_table(table_id, output_base=out_base)


def get_column_insight(
    column_id: str,
    output_base: str = "output",
) -> dict[str, Any]:
    """Return column-level insight payload for hover cards."""
    from profiler.diagram import get_column_insight as _get_column

    out_base = resolve_path(output_base)
    return _get_column(column_id, output_base=out_base)


def get_relationship_detail(
    edge_id: str,
    output_base: str = "output",
) -> dict[str, Any]:
    """Return relationship detail payload for edge selection."""
    from profiler.diagram import get_relationship_detail as _get_relationship

    out_base = resolve_path(output_base)
    return _get_relationship(edge_id, output_base=out_base)


def export_dbml(
    output_base: str = "output",
    min_confidence: float = 0.5,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Export DBML schema from existing TRUE_FK relationships."""
    from profiler.diagram import export_dbml_schema as _export_dbml

    out_base = resolve_path(output_base)
    return _export_dbml(
        output_base=out_base,
        min_confidence=min_confidence,
        top_k=top_k,
    )


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
        "columns_with_issues": table_profile.get("columns_with_issues", 0),
        "total_quality_flags": table_profile.get("total_quality_flags", 0),
        "composite_pk_candidates": table_profile.get("composite_pk_candidates", []),
    }


def _write_pk_context(output_base: Path) -> str:
    """Write consolidated pk_context.json from generated profile artifacts."""
    profiles_dir = output_base / "profiles"
    out_path = output_base / "pk_context.json"
    items: list[dict[str, Any]] = []

    try:
        from profiler.profiling.pk_detector import extract_table_root
    except Exception:
        extract_table_root = lambda table_name: str(table_name or "").lower()  # type: ignore

    for profile_file in sorted(profiles_dir.glob("*.profile.json")):
        profile = _read_json(profile_file)
        table_name = str(profile.get("table_name") or profile_file.stem.replace(".profile", ""))
        table_profile = profile.get("table_profile", {}) or {}
        pk_candidates = list(table_profile.get("pk_candidates") or [])
        composite_candidates = list(table_profile.get("composite_pk_candidates") or [])
        columns = profile.get("columns", []) or []
        by_name = {str(c.get("column_name")): c for c in columns}

        audit_refs = [
            str(c.get("column_name"))
            for c in columns
            if str(c.get("column_name", "")).lower().endswith(
                ("createdby", "modifiedby", "lasteditedby", "approvedby", "deletedby", "reviewedby")
            )
        ]

        if pk_candidates:
            pk_repr = pk_candidates[0]
            pk_type = "SINGLE"
            confidence = float(by_name.get(pk_repr, {}).get("pk_confidence", 0.75) or 0.75)
        elif composite_candidates:
            pk_repr = composite_candidates[0]
            pk_type = "COMPOSITE"
            confidence = 0.85
        else:
            pk_repr = None
            pk_type = "NONE"
            confidence = 0.0

        items.append(
            {
                "table": table_name,
                "table_root": extract_table_root(table_name),
                "pk": pk_repr,
                "pk_type": pk_type,
                "confidence": round(min(1.0, max(0.0, confidence)), 4),
                "pk_candidates": pk_candidates,
                "composite_candidates": composite_candidates,
                "audit_refs": audit_refs,
            }
        )

    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "tables": items}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(out_path.resolve())


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
