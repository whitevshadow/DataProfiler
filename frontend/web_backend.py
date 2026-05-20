from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# Make fkrte importable
_FKRTE_DIR = Path(__file__).resolve().parent
if str(_FKRTE_DIR) not in sys.path:
    sys.path.insert(0, str(_FKRTE_DIR))

try:
    from fkrte.tree_builder import (
        build_all as _fkrte_build_all,
        load_true_fk_edges as _fkrte_edges,
        build_graph as _fkrte_graph,
        load_profiles as _fkrte_profiles,
        load_lcil as _fkrte_lcil,
        expand_entity as _fkrte_expand,
        search_tree as _fkrte_search,
        invalidate_cache as _fkrte_invalidate,
        get_cached as _fkrte_cached,
        TREE_OUT_DIR as _FKRTE_TREE_DIR,
    )
    _FKRTE_OK = True
except Exception as _fkrte_err:
    _FKRTE_OK = False
    print(f"[FKRTE] tree_builder unavailable: {_fkrte_err}")

from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket

from connector.connection_manager import ConnectorError, get_connection_manager
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from profiler.agent.chatbot import create_chat_graph, load_mcp_tools
from profiler.agent.llm_factory import get_llm_with_fallback
from profiler.agent.system_prompt import CHATBOT_SYSTEM_PROMPT
from profiler.diagram import (
    build_diagram_state,
    get_table_detail,
    get_column_insight,
    get_relationship_detail,
    export_dbml_schema,
)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DIST_DIR = BASE_DIR / "dist"
UPLOAD_TMP_DIR = PROJECT_ROOT / "data" / "uploads"
UPLOAD_PERSISTENT_DIR = PROJECT_ROOT / "data" / "mounted"
SESSIONS_FILE = PROJECT_ROOT / "output" / "frontend_sessions.json"


class SessionStore:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._sessions: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.file_path.exists():
            return
        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._sessions = raw
        except Exception:
            self._sessions = {}

    def _save(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(self._sessions, indent=2), encoding="utf-8")

    def touch(self, session_id: str, label: str | None = None) -> None:
        now = time.time()
        item = self._sessions.get(session_id, {})
        item.setdefault("session_id", session_id)
        item["label"] = label or item.get("label") or "Session"
        item.setdefault("created_at", now)
        item["updated_at"] = now
        item.setdefault("message_count", 0)
        item.setdefault("messages", [])
        self._sessions[session_id] = item
        self._save()

    def append_message(self, session_id: str, role: str, content: str, tool: str | None = None) -> None:
        self.touch(session_id)
        entry = {"role": role, "content": content, "ts": time.time()}
        if tool:
            entry["tool"] = tool
        self._sessions[session_id]["messages"].append(entry)
        self._sessions[session_id]["message_count"] = len(self._sessions[session_id]["messages"])
        self._sessions[session_id]["updated_at"] = time.time()
        self._save()

    def list(self) -> list[dict[str, Any]]:
        items = list(self._sessions.values())
        items.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return [
            {
                "session_id": i["session_id"],
                "label": i.get("label", "Session"),
                "updated_at": _iso(i.get("updated_at", 0)),
                "message_count": i.get("message_count", 0),
            }
            for i in items
        ]

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        return self._sessions.get(session_id, {}).get("messages", [])


SESSIONS = SessionStore(SESSIONS_FILE)


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _normalize_content(content: Any) -> str:
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "thinking":
                    continue
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return " ".join(p for p in parts if p).strip()
    return str(content)


def _upload_target_dir(target: str) -> Path:
    if target == "persistent":
        return UPLOAD_PERSISTENT_DIR
    return UPLOAD_TMP_DIR


async def index(_: Request) -> FileResponse:
    index_path = (DIST_DIR if DIST_DIR.exists() else BASE_DIR) / "index.html"
    return FileResponse(index_path)


async def api_sessions(request: Request) -> JSONResponse:
    if request.method == "GET":
        return JSONResponse(SESSIONS.list())

    body = await request.json()
    session_id = body.get("session_id")
    if not session_id:
        return JSONResponse({"error": "session_id is required"}, status_code=400)
    label = body.get("label")
    SESSIONS.touch(session_id, label=label)
    return JSONResponse({"ok": True})


async def api_upload(request: Request) -> JSONResponse:
    form = await request.form()
    target = request.query_params.get("target", "temporary")
    batch_id = request.query_params.get("batch_id") or uuid.uuid4().hex[:12]

    dst_root = _upload_target_dir(target) / batch_id
    dst_root.mkdir(parents=True, exist_ok=True)

    uploaded: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for item in form.getlist("files"):
        file_name = Path(getattr(item, "filename", "uploaded.bin")).name
        if not file_name:
            continue
        dst = dst_root / file_name
        try:
            data = await item.read()
            dst.write_bytes(data)
            rel = dst.relative_to(PROJECT_ROOT).as_posix()
            uploaded.append(
                {
                    "file_name": file_name,
                    "size": len(data),
                    "server_path": rel,
                    "upload_dir": dst_root.relative_to(PROJECT_ROOT).as_posix(),
                }
            )
        except Exception as exc:
            errors.append({"file_name": file_name, "error": str(exc)})

    return JSONResponse(
        {
            "files": uploaded,
            "errors": errors,
            "upload_dir": dst_root.relative_to(PROJECT_ROOT).as_posix(),
        }
    )


async def list_connections(_: Request) -> JSONResponse:
    manager = get_connection_manager()
    rows = [c.__dict__ for c in manager.list_connections()]
    return JSONResponse(rows)


async def create_connection(request: Request) -> JSONResponse:
    manager = get_connection_manager()
    body = await request.json()
    try:
        info = manager.register(
            connection_id=body.get("connection_id", "").strip(),
            scheme=body.get("scheme", "").strip(),
            credentials=body.get("credentials", {}) or {},
            display_name=body.get("display_name", "").strip(),
        )
        return JSONResponse(
            {
                "connection_id": info.connection_id,
                "scheme": info.scheme,
                "display_name": info.display_name,
            }
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def test_connection(request: Request) -> JSONResponse:
    manager = get_connection_manager()
    connection_id = request.path_params["connection_id"]
    try:
        result = manager.test(connection_id)
        return JSONResponse(result.__dict__)
    except Exception as exc:
        return JSONResponse({"success": False, "message": str(exc), "latency_ms": 0.0}, status_code=400)


async def delete_connection(request: Request) -> JSONResponse:
    manager = get_connection_manager()
    connection_id = request.path_params["connection_id"]
    ok = manager.remove(connection_id)
    return JSONResponse({"ok": ok})


# ============================================================
# FKRTE API endpoints
# ============================================================

_fkrte_state_cache: dict[str, Any] = {}

def _fkrte_state() -> dict[str, Any]:
    global _fkrte_state_cache
    if not _FKRTE_OK:
        return {}
    if not _fkrte_state_cache:
        data = _fkrte_cached()
        edges = _fkrte_edges()
        p2c, c2p = _fkrte_graph(edges)
        _fkrte_state_cache = {
            "data": data,
            "p2c": p2c,
            "c2p": c2p,
            "profiles": _fkrte_profiles(),
            "lcil": _fkrte_lcil(),
        }
    return _fkrte_state_cache


async def fkrte_tree(request: Request) -> JSONResponse:
    if not _FKRTE_OK:
        return JSONResponse({"error": "FKRTE not available"}, status_code=503)
    force = request.query_params.get("force", "false").lower() == "true"
    if force:
        _fkrte_invalidate()
        global _fkrte_state_cache
        _fkrte_state_cache = {}
    data = _fkrte_state()["data"]
    return JSONResponse({
        "tree": data["tree"],
        "stats": {
            "total_tables": len(data["entities"]),
            "total_true_fk_edges": len(data["edges"]),
            "root_nodes": len(data["tree"]),
        }
    })


async def fkrte_entity(request: Request) -> JSONResponse:
    if not _FKRTE_OK:
        return JSONResponse({"error": "FKRTE not available"}, status_code=503)
    entity_id = request.path_params["entity_id"].lower()
    entities = _fkrte_state()["data"]["entities"]
    entity = entities.get(entity_id)
    if entity is None:
        for k, v in entities.items():
            if k.lower() == entity_id:
                entity = v
                break
    if entity is None:
        return JSONResponse({"error": f"Entity '{entity_id}' not found"}, status_code=404)
    return JSONResponse(entity)


async def fkrte_expand(request: Request) -> JSONResponse:
    if not _FKRTE_OK:
        return JSONResponse({"error": "FKRTE not available"}, status_code=503)
    entity_id = request.path_params["entity_id"].lower()
    visited_raw = request.query_params.get("visited", "")
    visited = [v.strip() for v in visited_raw.split(",") if v.strip()]
    p2c = _fkrte_state()["p2c"]
    children = _fkrte_expand(entity_id, p2c, visited)
    return JSONResponse({"entity_id": entity_id, "children": children})


async def fkrte_relationship(request: Request) -> JSONResponse:
    if not _FKRTE_OK:
        return JSONResponse({"error": "FKRTE not available"}, status_code=503)
    edge_id = request.path_params["edge_id"]
    edges = _fkrte_state()["data"]["edges"]
    for e in edges:
        if e["id"] == edge_id:
            return JSONResponse(e)
    for e in edges:
        if edge_id in e["id"]:
            return JSONResponse(e)
    return JSONResponse({"error": f"Edge '{edge_id}' not found"}, status_code=404)


async def fkrte_relationships(request: Request) -> JSONResponse:
    if not _FKRTE_OK:
        return JSONResponse({"error": "FKRTE not available"}, status_code=503)
    entity_id = request.query_params.get("entity_id", "").lower()
    min_conf = float(request.query_params.get("min_confidence", "0"))
    edges = _fkrte_state()["data"]["edges"]
    result = [
        e for e in edges
        if e["confidence"] >= min_conf
        and (not entity_id or entity_id in [e["fk_table"], e["pk_table"]])
    ]
    return JSONResponse({"relationships": result, "count": len(result)})


async def fkrte_table(request: Request) -> JSONResponse:
    if not _FKRTE_OK:
        return JSONResponse({"error": "FKRTE not available"}, status_code=503)
    table_id = request.path_params["table_id"].lower()
    metrics = _fkrte_state()["data"]["metrics"]
    for m in metrics:
        if m["id"].lower() == table_id:
            return JSONResponse(m)
    return JSONResponse({"error": f"Table '{table_id}' not found"}, status_code=404)


async def fkrte_search(request: Request) -> JSONResponse:
    if not _FKRTE_OK:
        return JSONResponse({"error": "FKRTE not available"}, status_code=503)
    q = request.query_params.get("q", "")
    min_quality = float(request.query_params.get("min_quality", "0"))
    state = _fkrte_state()
    results = _fkrte_search(q, state["data"]["entities"], state["profiles"])
    if min_quality > 0:
        results = [r for r in results if r.get("quality_score", 0) >= min_quality]
    return JSONResponse({"query": q, "results": results, "count": len(results)})


async def fkrte_entities(request: Request) -> JSONResponse:
    if not _FKRTE_OK:
        return JSONResponse({"error": "FKRTE not available"}, status_code=503)
    min_quality = float(request.query_params.get("min_quality", "0"))
    limit = int(request.query_params.get("limit", "200"))
    offset = int(request.query_params.get("offset", "0"))
    entities = _fkrte_state()["data"]["entities"]
    result = [
        {
            "id": e["id"], "label": e["label"],
            "quality_score": e["quality_score"],
            "row_count": e["row_count"],
            "column_count": e["column_count"],
            "pk": e["pk"], "fk_count": e["fk_count"],
            "is_orphan": e["is_orphan"],
            "has_children": bool(e.get("related_children")),
        }
        for e in entities.values()
        if e.get("quality_score", 0) >= min_quality
    ]
    result.sort(key=lambda x: x["label"])
    return JSONResponse({"entities": result[offset:offset + limit], "total": len(result)})


async def fkrte_stats(_: Request) -> JSONResponse:
    if not _FKRTE_OK:
        return JSONResponse({"error": "FKRTE not available"}, status_code=503)
    data = _fkrte_state()["data"]
    entities = data["entities"]
    return JSONResponse({
        "total_tables": len(entities),
        "true_fk_count": len(data["edges"]),
        "orphan_tables": sum(1 for e in entities.values() if e.get("is_orphan")),
        "tables_with_lcil": sum(1 for e in entities.values() if e.get("lcil_domains")),
        "root_nodes": len(data["tree"]),
    })


async def fkrte_rebuild(request: Request) -> JSONResponse:
    if not _FKRTE_OK:
        return JSONResponse({"error": "FKRTE not available"}, status_code=503)
    _fkrte_invalidate()
    global _fkrte_state_cache
    _fkrte_state_cache = {}
    result = _fkrte_build_all(force=True)
    _fkrte_state()  # re-warm
    return JSONResponse({"ok": True, "stats": result.get("stats", {})})


async def fkrte_index(_: Request) -> JSONResponse:
    """FKRTE health check."""
    return JSONResponse({"status": "FKRTE online", "available": _FKRTE_OK})


async def api_diagram_state(request: Request) -> JSONResponse:
    params = request.query_params
    min_confidence = float(params.get("min_confidence", 0.5))
    top_k_raw = params.get("top_k")
    top_k = int(top_k_raw) if top_k_raw else None
    classes_raw = params.get("relationship_classes")
    classes = [c.strip() for c in classes_raw.split(",") if c.strip()] if classes_raw else None
    payload = build_diagram_state(
        output_base=PROJECT_ROOT / "output",
        min_confidence=min_confidence,
        top_k=top_k,
        relationship_classes=classes,
    )
    return JSONResponse(payload)


async def api_diagram_table(request: Request) -> JSONResponse:
    table_id = request.path_params["table_id"]
    payload = get_table_detail(table_id, output_base=PROJECT_ROOT / "output")
    return JSONResponse(payload)


async def api_diagram_column(request: Request) -> JSONResponse:
    column_id = request.path_params["column_id"]
    payload = get_column_insight(column_id, output_base=PROJECT_ROOT / "output")
    return JSONResponse(payload)


async def api_diagram_relationship(request: Request) -> JSONResponse:
    edge_id = request.path_params["edge_id"]
    payload = get_relationship_detail(edge_id, output_base=PROJECT_ROOT / "output")
    return JSONResponse(payload)


async def api_diagram_dbml(_: Request) -> PlainTextResponse:
    result = export_dbml_schema(output_base=PROJECT_ROOT / "output")
    dbml_path = Path(result["path"]).resolve()
    if dbml_path.exists():
        return PlainTextResponse(dbml_path.read_text(encoding="utf-8"))
    return PlainTextResponse("", status_code=404)


# ── DBML Viewer API ──────────────────────────────────────────────
async def api_dbml(_: Request) -> PlainTextResponse:
    """Alias for /api/diagram/dbml - returns schema.dbml text"""
    result = export_dbml_schema(output_base=PROJECT_ROOT / "output")
    dbml_path = Path(result["path"]).resolve()
    if dbml_path.exists():
        return PlainTextResponse(dbml_path.read_text(encoding="utf-8"))
    return PlainTextResponse("", status_code=404)


async def api_dbml_render(request: Request) -> JSONResponse:
    """Parse and cache DBML as JSON graph for viewer"""
    render_path = PROJECT_ROOT / "output" / "ui" / "dbml_render.json"
    
    if request.method == "POST":
        # Save provided graph data
        try:
            body = await request.json()
            render_path.parent.mkdir(parents=True, exist_ok=True)
            render_path.write_text(json.dumps(body, indent=2), encoding="utf-8")
            return JSONResponse({"status": "saved", "path": str(render_path)})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    
    # GET: return cached render if exists
    if render_path.exists():
        try:
            data = json.loads(render_path.read_text(encoding="utf-8"))
            return JSONResponse(data)
        except Exception as e:
            return JSONResponse({"error": f"Failed to load render: {e}"}, status_code=500)
    
    return JSONResponse({"nodes": [], "edges": [], "metadata": {}}, status_code=404)


async def api_dbml_state(request: Request) -> JSONResponse:
    """Persist/load DBML workspace UI state."""
    state_path = PROJECT_ROOT / "output" / "ui" / "dbml_state.json"

    if request.method == "POST":
        try:
            payload = await request.json()
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return JSONResponse({"status": "saved", "path": str(state_path)})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return JSONResponse(data)
        except Exception as exc:
            return JSONResponse({"error": f"Failed to load state: {exc}"}, status_code=500)

    return JSONResponse(
        {
            "viewer_open": False,
            "active_entity": None,
            "zoom": 1,
            "layout": "auto",
            "fullscreen": False,
            "selected_column": None,
            "minimap": True,
        },
        status_code=200,
    )


async def api_entity_detail(request: Request) -> JSONResponse:
    """Merge profile, quality, PK, and LCIL data for an entity"""
    entity_id = request.path_params["entity_id"]
    output_base = PROJECT_ROOT / "output"
    
    result = {}
    
    # Load profile
    profile_path = output_base / "profiles" / f"{entity_id}.json"
    if profile_path.exists():
        try:
            result["profile"] = json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    # Load quality
    quality_path = output_base / "quality" / f"{entity_id}.json"
    if quality_path.exists():
        try:
            result["quality"] = json.loads(quality_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    # Load PK analysis
    pk_path = output_base / "pk_analysis" / f"{entity_id}.json"
    if pk_path.exists():
        try:
            result["pk"] = json.loads(pk_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    # Load LCIL
    lcil_path = output_base / "lcil" / f"{entity_id}.json"
    if lcil_path.exists():
        try:
            result["lcil"] = json.loads(lcil_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    if result:
        return JSONResponse(result)
    
    return JSONResponse({"error": "Entity not found"}, status_code=404)


async def api_relationship_detail_dbml(request: Request) -> JSONResponse:
    """Get relationship metadata for DBML viewer"""
    rel_id = request.path_params["rel_id"]
    output_base = PROJECT_ROOT / "output"
    
    # Load relationships.json
    rel_path = output_base / "relationships" / "relationships.json"
    if rel_path.exists():
        try:
            data = json.loads(rel_path.read_text(encoding="utf-8"))
            # Find matching relationship
            for rel in data.get("relationships", []):
                rel_key = f"{rel['left_table']}.{rel['left_column']}-{rel['right_table']}.{rel['right_column']}"
                if rel_key == rel_id or rel.get("edge_id") == rel_id:
                    return JSONResponse(rel)
        except Exception as e:
            return JSONResponse({"error": f"Failed to load relationships: {e}"}, status_code=500)
    
    return JSONResponse({"error": "Relationship not found"}, status_code=404)


class ChatEndpoint(WebSocketEndpoint):
    encoding = "json"

    async def on_connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.graph = None
        self.config = None
        self.session_id = None
        self.tool_count = 0

    async def on_receive(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        msg_type = data.get("type")

        if msg_type == "config":
            await self._handle_config(websocket, data)
            return

        if msg_type == "message":
            await self._handle_user_message(websocket, data)
            return

    async def _handle_config(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        self.session_id = data.get("session_id") or f"web-{uuid.uuid4().hex[:10]}"
        mcp_url = data.get("mcp_url") or "http://localhost:8080/sse"
        provider = data.get("provider")

        SESSIONS.touch(self.session_id)

        try:
            tools = await load_mcp_tools(mcp_url)
            llm = get_llm_with_fallback(provider=provider)
            self.graph = create_chat_graph(tools, llm)
            self.config = {"configurable": {"thread_id": self.session_id}}
            self.tool_count = len(tools)

            history = SESSIONS.get_messages(self.session_id)
            await websocket.send_json(
                {
                    "type": "connected",
                    "tools": self.tool_count,
                    "has_history": len(history) > 0,
                }
            )
            if history:
                await websocket.send_json({"type": "history", "messages": history})
        except Exception as exc:
            await websocket.send_json({"type": "error", "content": f"Connection failed: {exc}"})

    async def _handle_user_message(self, websocket: WebSocket, data: dict[str, Any]) -> None:
        if self.graph is None or self.config is None:
            await websocket.send_json({"type": "error", "content": "Backend is not configured yet."})
            return

        content = str(data.get("content") or "").strip()
        if not content:
            return

        SESSIONS.append_message(self.session_id, "user", content)
        await websocket.send_json({"type": "thinking", "percent": 10})

        final_text = ""
        tool_index = 0
        tool_name_map = {}  # Track tool names by index
        component_sent = False
        try:
            inputs = {
                "messages": [HumanMessage(content=content)],
                "mode": "autonomous",
            }
            async for event in self.graph.astream(inputs, config=self.config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    if node_name == "agent":
                        msg = node_output["messages"][-1]
                        if isinstance(msg, AIMessage):
                            if msg.tool_calls:
                                for tc in msg.tool_calls:
                                    tool_index += 1
                                    tool_name = tc.get("name", "tool")
                                    tool_name_map[tool_index] = tool_name
                                    await websocket.send_json(
                                        {
                                            "type": "tool_start",
                                            "tool": tool_name,
                                            "tool_index": tool_index,
                                            "percent": min(80, 15 + tool_index * 10),
                                        }
                                    )
                            else:
                                normalized = _normalize_content(msg.content)
                                if normalized:
                                    final_text = normalized
                    elif node_name == "tools":
                        for tool_msg in node_output.get("messages", []):
                            if isinstance(tool_msg, ToolMessage):
                                # Get tool name from our tracking map
                                current_tool_name = tool_name_map.get(max(1, tool_index), "tool")

                                # Try to parse JSON and extract summary field
                                raw_content = _normalize_content(tool_msg.content)
                                summary = raw_content
                                parsed_payload: dict[str, Any] | None = None
                                try:
                                    import json
                                    parsed = json.loads(tool_msg.content)
                                    if isinstance(parsed, dict):
                                        parsed_payload = parsed
                                    if isinstance(parsed, dict) and "summary" in parsed:
                                        summary = parsed["summary"]
                                except (json.JSONDecodeError, TypeError):
                                    pass  # Use raw content as summary

                                # If this tool produced a DBML visual payload, stream component event.
                                if isinstance(parsed_payload, dict) and parsed_payload.get("render_type") == "dbml_visual":
                                    component_payload = parsed_payload.get("component")
                                    if not isinstance(component_payload, dict):
                                        component_payload = {
                                            "type": "component",
                                            "component": "dbml_viewer",
                                            "props": {
                                                "dbml": parsed_payload.get("dbml_text", ""),
                                                "viewer_html": parsed_payload.get("viewer_html", ""),
                                                "react_component": parsed_payload.get("react_component", ""),
                                                "graph_nodes": parsed_payload.get("graph_nodes", []),
                                                "graph_edges": parsed_payload.get("graph_edges", []),
                                            },
                                        }
                                    await websocket.send_json(component_payload)
                                    component_sent = True

                                if len(summary) > 180:
                                    summary = summary[:180] + "..."

                                SESSIONS.append_message(self.session_id, "tool", summary, tool=current_tool_name)
                                await websocket.send_json(
                                    {
                                        "type": "tool_result",
                                        "tool": current_tool_name,
                                        "tool_index": max(1, tool_index),
                                        "success": True,
                                        "summary": summary or "Done",
                                        "percent": min(90, 20 + tool_index * 12),
                                    }
                                )

            if component_sent:
                # Do not emit a summary/explanation text when a render component is available.
                await websocket.send_json({"type": "turn_complete"})
                return

            if not final_text:
                final_text = "Done."

            SESSIONS.append_message(self.session_id, "assistant", final_text)
            await websocket.send_json({"type": "assistant", "content": final_text})
        except Exception as exc:
            error_msg = str(exc)
            print(f"Error in _handle_user_message: {error_msg}")
            
            # Check if it's an LLM API error
            if "InternalServerError" in error_msg or "500" in error_msg:
                error_msg = "⚠️ The LLM API is currently unavailable (500 error). Please try again in a moment, or switch to OpenAI by configuring OPENAI_API_KEY in your .env file."
            elif "litellm" in error_msg.lower():
                error_msg = f"⚠️ LLM Error: {error_msg}. Check your API keys in .env file."
            
            # Only send error if websocket is still open
            try:
                if websocket.client_state.value == 1:  # CONNECTED state
                    await websocket.send_json({"type": "error", "content": error_msg})
            except Exception as send_exc:
                print(f"Could not send error to client (websocket closed): {send_exc}")


routes = [
    Route("/", endpoint=index, methods=["GET"]),
    Route("/index.html", endpoint=index, methods=["GET"]),
    # ── FKRTE API ──────────────────────────────────────────────
    Route("/api/fkrte/tree",                        endpoint=fkrte_tree,         methods=["GET"]),
    Route("/api/fkrte/entity/{entity_id}",          endpoint=fkrte_entity,       methods=["GET"]),
    Route("/api/fkrte/expand/{entity_id}",          endpoint=fkrte_expand,       methods=["GET"]),
    Route("/api/fkrte/relationship/{edge_id:path}", endpoint=fkrte_relationship, methods=["GET"]),
    Route("/api/fkrte/relationships",               endpoint=fkrte_relationships,methods=["GET"]),
    Route("/api/fkrte/table/{table_id}",            endpoint=fkrte_table,        methods=["GET"]),
    Route("/api/fkrte/search",                      endpoint=fkrte_search,       methods=["GET"]),
    Route("/api/fkrte/entities",                    endpoint=fkrte_entities,     methods=["GET"]),
    Route("/api/fkrte/stats",                       endpoint=fkrte_stats,        methods=["GET"]),
    Route("/api/fkrte/rebuild",                     endpoint=fkrte_rebuild,      methods=["POST"]),
    Route("/api/fkrte",                             endpoint=fkrte_index,        methods=["GET"]),
    # ── Diagram API ────────────────────────────────────────────
    Route("/api/diagram/state", endpoint=api_diagram_state, methods=["GET"]),
    Route("/api/diagram/table/{table_id}", endpoint=api_diagram_table, methods=["GET"]),
    Route("/api/diagram/column/{column_id}", endpoint=api_diagram_column, methods=["GET"]),
    Route("/api/diagram/relationship/{edge_id}", endpoint=api_diagram_relationship, methods=["GET"]),
    Route("/api/diagram/dbml", endpoint=api_diagram_dbml, methods=["GET"]),
    # ── DBML Viewer API ────────────────────────────────────────
    Route("/api/dbml", endpoint=api_dbml, methods=["GET"]),
    Route("/api/dbml/render", endpoint=api_dbml_render, methods=["GET", "POST"]),
    Route("/api/dbml/state", endpoint=api_dbml_state, methods=["GET", "POST"]),
    Route("/api/entity/{entity_id}", endpoint=api_entity_detail, methods=["GET"]),
    Route("/api/relationship/{rel_id:path}", endpoint=api_relationship_detail_dbml, methods=["GET"]),
    # ── Session & Upload API ───────────────────────────────────
    Route("/api/sessions", endpoint=api_sessions, methods=["GET", "POST"]),
    Route("/api/upload", endpoint=api_upload, methods=["POST"]),
    Route("/api/connections", endpoint=list_connections, methods=["GET"]),
    Route("/api/connections", endpoint=create_connection, methods=["POST"]),
    Route("/api/connections/{connection_id}/test", endpoint=test_connection, methods=["POST"]),
    Route("/api/connections/{connection_id}", endpoint=delete_connection, methods=["DELETE"]),
    WebSocketRoute("/ws/chat", ChatEndpoint),
    Mount("/static", app=StaticFiles(directory=str(DIST_DIR if DIST_DIR.exists() else BASE_DIR)), name="static"),
    Mount("/", app=StaticFiles(directory=str(DIST_DIR if DIST_DIR.exists() else BASE_DIR), html=True), name="frontend-static"),
]

app = Starlette(debug=True, routes=routes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_backend:app", host="127.0.0.1", port=5500, reload=False)
