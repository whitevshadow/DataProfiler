"""
FKRTE API Server
================
FastAPI backend serving the FK Relationship Tree Explorer.
Run with:  uvicorn fkrte.api:app --port 5600 --reload
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .tree_builder import (
    build_all,
    expand_entity,
    get_cached,
    invalidate_cache,
    search_tree,
    load_true_fk_edges,
    build_graph,
    load_profiles,
    load_lcil,
)

# ---------------------------------------------------------------------------
app = FastAPI(
    title="FKRTE — FK Relationship Tree Explorer API",
    description="Interactive FK relationship tree navigation for the Data Profiler",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Lazy graph state (loaded once, cached)
# ---------------------------------------------------------------------------
_graph_state: dict[str, Any] = {}

def _state() -> dict[str, Any]:
    global _graph_state
    if not _graph_state:
        data = get_cached()
        edges   = load_true_fk_edges()
        p2c, c2p = build_graph(edges)
        _graph_state = {
            "data":            data,
            "parent_to_children": p2c,
            "child_to_parents":   c2p,
            "profiles":        load_profiles(),
            "lcil":            load_lcil(),
        }
    return _graph_state


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/fkrte/tree")
def get_tree(force: bool = False):
    """
    Returns the full pre-built relationship tree (list of root nodes).
    Each node has: id, label, has_children, children[], edge{}.
    """
    if force:
        invalidate_cache()
        global _graph_state
        _graph_state = {}
    data = _state()["data"]
    return JSONResponse({
        "tree":    data["tree"],
        "stats": {
            "total_tables":        len(data["entities"]),
            "total_true_fk_edges": len(data["edges"]),
            "root_nodes":          len(data["tree"]),
        }
    })


@app.get("/api/fkrte/entity/{entity_id}")
def get_entity(entity_id: str):
    """Returns full entity properties: profile, columns, relationships, LCIL."""
    entities = _state()["data"]["entities"]
    entity = entities.get(entity_id.lower())
    if entity is None:
        # Try case-insensitive search
        for k, v in entities.items():
            if k.lower() == entity_id.lower():
                entity = v
                break
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return JSONResponse(entity)


@app.get("/api/fkrte/expand/{entity_id}")
def expand(
    entity_id: str,
    visited: str = Query(default="", description="Comma-separated already-visited entity IDs"),
):
    """
    Expand one level of children for entity_id.
    Returns list of child nodes with edge metadata.
    Respects visited set to prevent infinite loops.
    """
    visited_list = [v.strip() for v in visited.split(",") if v.strip()]
    state = _state()
    p2c   = state["parent_to_children"]
    children = expand_entity(entity_id.lower(), p2c, visited_list)
    return JSONResponse({"entity_id": entity_id, "children": children})


@app.get("/api/fkrte/relationship/{edge_id}")
def get_relationship(edge_id: str):
    """
    Returns full relationship details for an edge.
    edge_id format: {fk_table}__{fk_col}__{pk_table}__{pk_col}
    """
    edges = _state()["data"]["edges"]
    for e in edges:
        if e["id"] == edge_id:
            return JSONResponse(e)
    # Try partial match
    for e in edges:
        if edge_id in e["id"] or e["id"] in edge_id:
            return JSONResponse(e)
    raise HTTPException(status_code=404, detail=f"Relationship '{edge_id}' not found")


@app.get("/api/fkrte/relationships")
def list_relationships(
    entity_id: Optional[str] = Query(default=None),
    min_confidence: float = Query(default=0.0),
):
    """List all TRUE_FK relationships, optionally filtered by entity."""
    edges = _state()["data"]["edges"]
    result = [
        e for e in edges
        if e["confidence"] >= min_confidence
        and (entity_id is None or entity_id.lower() in [e["fk_table"], e["pk_table"]])
    ]
    return JSONResponse({"relationships": result, "count": len(result)})


@app.get("/api/fkrte/table/{table_id}")
def get_table_metrics(table_id: str):
    """Returns table metrics (rows, columns, quality, PK)."""
    metrics = _state()["data"]["metrics"]
    for m in metrics:
        if m["id"].lower() == table_id.lower():
            return JSONResponse(m)
    raise HTTPException(status_code=404, detail=f"Table '{table_id}' not found")


@app.get("/api/fkrte/search")
def search(
    q: str = Query(..., description="Search query"),
    min_quality: float = Query(default=0.0),
    min_confidence: float = Query(default=0.0),
    has_lcil: Optional[bool] = Query(default=None),
    is_orphan: Optional[bool] = Query(default=None),
    min_fk_count: int = Query(default=0),
):
    """
    Full-text search across table names, column names, PKs, semantic labels.
    Supports filters: quality, confidence, lcil presence, orphan, fk_count.
    """
    state    = _state()
    entities = state["data"]["entities"]
    profiles = state["profiles"]

    results = search_tree(q, entities, profiles)

    # Apply filters
    filtered = []
    for r in results:
        e = entities.get(r["id"], {})
        if e.get("quality_score", 0.0) < min_quality:
            continue
        if has_lcil is not None:
            if has_lcil and not e.get("lcil_domains"):
                continue
            if not has_lcil and e.get("lcil_domains"):
                continue
        if is_orphan is not None:
            if is_orphan != e.get("is_orphan", False):
                continue
        if e.get("fk_count", 0) < min_fk_count:
            continue
        filtered.append(r)

    return JSONResponse({"query": q, "results": filtered, "count": len(filtered)})


@app.get("/api/fkrte/entities")
def list_entities(
    min_quality: float = Query(default=0.0),
    min_fk_count: int = Query(default=0),
    has_lcil: Optional[bool] = Query(default=None),
    is_orphan: Optional[bool] = Query(default=None),
    limit: int = Query(default=200),
    offset: int = Query(default=0),
):
    """List all entities with optional filters."""
    entities = _state()["data"]["entities"]
    result = []
    for k, e in entities.items():
        if e.get("quality_score", 0.0) < min_quality:
            continue
        if e.get("fk_count", 0) < min_fk_count:
            continue
        if has_lcil is not None:
            if has_lcil and not e.get("lcil_domains"):
                continue
            if not has_lcil and e.get("lcil_domains"):
                continue
        if is_orphan is not None:
            if is_orphan != e.get("is_orphan", False):
                continue
        result.append({
            "id":            e["id"],
            "label":         e["label"],
            "quality_score": e["quality_score"],
            "row_count":     e["row_count"],
            "column_count":  e["column_count"],
            "pk":            e["pk"],
            "fk_count":      e["fk_count"],
            "is_orphan":     e["is_orphan"],
            "has_lcil":      bool(e.get("lcil_domains")),
            "has_children":  bool(e.get("related_children")),
        })
    result.sort(key=lambda x: x["label"])
    return JSONResponse({
        "entities": result[offset:offset+limit],
        "total":    len(result),
    })


@app.get("/api/fkrte/stats")
def get_stats():
    """Returns overall dataset statistics."""
    data = _state()["data"]
    entities = data["entities"]
    edges    = data["edges"]

    orphans   = sum(1 for e in entities.values() if e.get("is_orphan"))
    with_lcil = sum(1 for e in entities.values() if e.get("lcil_domains"))

    return JSONResponse({
        "total_tables":    len(entities),
        "true_fk_count":   len(edges),
        "orphan_tables":   orphans,
        "tables_with_lcil": with_lcil,
        "root_nodes":      len(data["tree"]),
    })


@app.post("/api/fkrte/rebuild")
def rebuild():
    """Force rebuild all tree JSON outputs from source files."""
    invalidate_cache()
    global _graph_state
    _graph_state = {}
    result = build_all(force=True)
    _state()  # re-warm
    return JSONResponse({
        "ok": True,
        "stats": result.get("stats", {}),
    })


# ---------------------------------------------------------------------------
# Mount static assets (FKRTE dist)
# ---------------------------------------------------------------------------
DIST = Path(__file__).parent / "dist"
if DIST.exists():
    app.mount("/fkrte", StaticFiles(directory=str(DIST), html=True), name="fkrte-static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fkrte.api:app", host="127.0.0.1", port=5600, reload=True)
