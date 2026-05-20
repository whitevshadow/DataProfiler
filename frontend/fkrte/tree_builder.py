"""
FKRTE Tree Builder
==================
Builds a navigable FK relationship tree from the profiler output files.
Uses ONLY TRUE_FK relationships. Parent = pk_table, Child = fk_table.
Implements BFS expansion with cycle detection and depth limiting.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent
PROJECT_ROOT = BASE.parent.parent.parent       # f:\agentic_profiler
OUTPUT_ROOT  = PROJECT_ROOT / "output"

REL_FILE     = OUTPUT_ROOT / "relationships"   / "relationships.json"
PROFILES_DIR = OUTPUT_ROOT / "profiles"
LC_FILE      = OUTPUT_ROOT / "low_cardinality" / "low_cardinality_insights.json"
TREE_OUT_DIR = OUTPUT_ROOT / "tree"

MAX_DEPTH    = 8
TOP_K        = 20           # max children per node in initial expansion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _norm(name: str) -> str:
    """Lowercase, strip schema prefix, strip underscores for display."""
    return name.strip()


def _display(name: str) -> str:
    """Human-friendly display name (PascalCase from snake_case/schema.name)."""
    # Remove schema prefix  (sales_orders → orders)
    part = name.split("_", 1)[-1] if "_" in name else name
    return part.title().replace("_", "")


def _table_key(name: str) -> str:
    return name.lower().replace(" ", "_")


# ---------------------------------------------------------------------------
# 1. Load relationships  (TRUE_FK only)
# ---------------------------------------------------------------------------
def load_true_fk_edges(rel_file: Path = REL_FILE) -> list[dict]:
    with open(rel_file, encoding="utf-8") as f:
        data = json.load(f)
    edges = []
    for r in data.get("relationships", []):
        if r.get("relationship_class") == "TRUE_FK":
            edges.append({
                "fk_table":   r["fk_table"],
                "fk_column":  r["fk_column"],
                "pk_table":   r["pk_table"],
                "pk_column":  r["pk_column"],
                "confidence": r.get("confidence_score", 0.0),
                "containment": r.get("containment_ratio", 0.0),
                "semantic_similarity": r.get("semantic_similarity", 0.0),
                "reasoning":  r.get("reasoning", []),
                "relationship_class": "TRUE_FK",
            })
    return edges


# ---------------------------------------------------------------------------
# 2. Build adjacency maps
# ---------------------------------------------------------------------------
def build_graph(edges: list[dict]) -> tuple[dict, dict]:
    """
    parent_to_children[pk_table] = [{ fk_table, fk_column, pk_column, confidence, … }]
    child_to_parents[fk_table]   = [pk_table, …]
    """
    parent_to_children: dict[str, list[dict]] = defaultdict(list)
    child_to_parents:   dict[str, list[str]]  = defaultdict(list)
    seen: set[tuple] = set()

    for e in edges:
        pk = _table_key(e["pk_table"])
        fk = _table_key(e["fk_table"])
        # Skip self-loops for DIFFERENT columns only if both tables are same
        key = (pk, fk, e["pk_column"], e["fk_column"])
        if key in seen:
            continue
        seen.add(key)
        parent_to_children[pk].append({
            "child":          fk,
            "child_display":  e["fk_table"],
            "fk_column":      e["fk_column"],
            "pk_column":      e["pk_column"],
            "confidence":     e["confidence"],
            "containment":    e["containment"],
            "semantic_similarity": e["semantic_similarity"],
            "reasoning":      e["reasoning"],
        })
        if pk not in child_to_parents[fk]:
            child_to_parents[fk].append(pk)

    return dict(parent_to_children), dict(child_to_parents)


# ---------------------------------------------------------------------------
# 3. Load profile metrics
# ---------------------------------------------------------------------------
def load_profiles(profiles_dir: Path = PROFILES_DIR) -> dict[str, dict]:
    profiles: dict[str, dict] = {}
    for p in profiles_dir.glob("*.profile.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            table = _table_key(data.get("table_name", p.stem.replace(".profile", "")))
            tp = data.get("table_profile", {})
            cols = data.get("columns", [])
            
            # Find best PK candidate
            pk_col = None
            best_pk_conf = 0.0
            for c in cols:
                if c.get("pk_candidate") and c.get("pk_confidence", 0) > best_pk_conf:
                    best_pk_conf = c["pk_confidence"]
                    pk_col = c.get("original_name") or c.get("column_name")

            # Count FK candidates
            fk_count = sum(1 for c in cols if c.get("fk_candidate"))
            
            # Column details
            col_details = []
            for c in cols:
                stats = c.get("statistics", {})
                top_vals = [str(v[0]) for v in (stats.get("top_values") or [])[:5]]
                col_details.append({
                    "name":         c.get("original_name") or c.get("column_name"),
                    "key":          c.get("column_name"),
                    "type":         c.get("physical_type", "unknown").upper(),
                    "logical_type": c.get("logical_type", ""),
                    "semantic_type": c.get("semantic_type") or "",
                    "cardinality":  (c.get("cardinality_class") or "").upper(),
                    "null_ratio":   stats.get("null_ratio", 0.0),
                    "quality":      c.get("quality_score", 1.0),
                    "top_values":   top_vals,
                    "is_pk":        bool(c.get("pk_candidate") and c.get("pk_confidence", 0) > 0.8),
                    "is_fk":        bool(c.get("fk_candidate")),
                    "relational_role": c.get("relational_role", ""),
                    "quality_flags": c.get("quality_flags", []),
                })

            profiles[table] = {
                "table_name":      data.get("table_name"),
                "row_count":       tp.get("row_count_estimate"),
                "column_count":    tp.get("column_count", len(cols)),
                "quality_score":   tp.get("quality_score", 0.0),
                "completeness":    tp.get("completeness_score", 0.0),
                "pk":              pk_col,
                "pk_confidence":   best_pk_conf,
                "fk_count":        fk_count,
                "pk_candidates":   tp.get("pk_candidates", []),
                "fk_candidates":   tp.get("fk_candidates", []),
                "columns":         col_details,
                "quality_flags":   tp.get("total_quality_flags", 0),
            }
        except Exception:
            pass
    return profiles


# ---------------------------------------------------------------------------
# 4. Load LCIL insights
# ---------------------------------------------------------------------------
def load_lcil(lc_file: Path = LC_FILE) -> dict[str, list[str]]:
    """Return table_key -> [domain labels]"""
    result: dict[str, list[str]] = {}
    if not lc_file.exists():
        return result
    try:
        data = json.loads(lc_file.read_text(encoding="utf-8"))
        # Expected shape: list of dicts with table/column info
        for item in data if isinstance(data, list) else data.get("insights", []):
            table = _table_key(item.get("table", ""))
            domain = item.get("domain") or item.get("label") or item.get("semantic_label") or ""
            if table and domain:
                result.setdefault(table, [])
                if domain not in result[table]:
                    result[table].append(domain)
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# 5. Build the full tree structure (for initial render)
# ---------------------------------------------------------------------------
def build_relationship_tree(
    parent_to_children: dict[str, list[dict]],
    profiles: dict[str, dict],
    depth_limit: int = MAX_DEPTH,
) -> list[dict]:
    """
    Returns root-level entities (tables with no parents or with parents).
    Each entity has a children list populated lazily to depth_limit.
    """
    all_tables = set(parent_to_children.keys())
    # Also include tables that appear only as children
    for children_list in parent_to_children.values():
        for c in children_list:
            all_tables.add(c["child"])
    # Also include profiled tables
    all_tables.update(profiles.keys())

    # Determine root tables (not a child of any other table via TRUE_FK)
    child_set: set[str] = set()
    for children_list in parent_to_children.values():
        for c in children_list:
            if c["child"] != list(parent_to_children.keys())[0]:  # avoid self
                child_set.add(c["child"])

    # Recompute properly
    child_set = set()
    for p, children_list in parent_to_children.items():
        for c in children_list:
            if c["child"] != p:  # skip self-references
                child_set.add(c["child"])

    root_tables = sorted(all_tables - child_set)
    # If every table is a child (circular), just use all tables as roots
    if not root_tables:
        root_tables = sorted(all_tables)

    def _build_node(table: str, visited: set[str], depth: int) -> dict:
        node = {
            "id":       table,
            "label":    profiles.get(table, {}).get("table_name") or table,
            "children": [],
            "has_children": bool(parent_to_children.get(table)),
        }
        if depth >= depth_limit or table in visited:
            node["truncated"] = True
            return node
        visited = visited | {table}
        for edge in parent_to_children.get(table, []):
            child_key = edge["child"]
            child_node = _build_node(child_key, visited, depth + 1)
            child_node["edge"] = {
                "fk_column":  edge["fk_column"],
                "pk_column":  edge["pk_column"],
                "confidence": edge["confidence"],
                "containment": edge["containment"],
                "semantic_similarity": edge["semantic_similarity"],
                "reasoning":  edge["reasoning"],
                "relationship_class": "TRUE_FK",
            }
            node["children"].append(child_node)
        return node

    tree = []
    for t in root_tables:
        tree.append(_build_node(t, set(), 0))
    return tree


# ---------------------------------------------------------------------------
# 6. Build entity properties map
# ---------------------------------------------------------------------------
def build_entity_properties(
    profiles: dict[str, dict],
    parent_to_children: dict[str, list[dict]],
    child_to_parents: dict[str, list[str]],
    lcil: dict[str, list[str]],
) -> dict[str, dict]:
    props = {}
    all_tables = set(profiles.keys()) | set(parent_to_children.keys())
    for children_list in parent_to_children.values():
        for c in children_list:
            all_tables.add(c["child"])

    for table in all_tables:
        p = profiles.get(table, {})
        related_children = [c["child"] for c in parent_to_children.get(table, [])]
        related_parents  = child_to_parents.get(table, [])
        props[table] = {
            "id":                table,
            "label":             p.get("table_name") or table,
            "row_count":         p.get("row_count"),
            "column_count":      p.get("column_count", 0),
            "quality_score":     p.get("quality_score", 0.0),
            "completeness":      p.get("completeness", 1.0),
            "pk":                p.get("pk"),
            "pk_confidence":     p.get("pk_confidence", 0.0),
            "fk_count":          p.get("fk_count", 0),
            "pk_candidates":     p.get("pk_candidates", []),
            "fk_candidates":     p.get("fk_candidates", []),
            "columns":           p.get("columns", []),
            "quality_flags":     p.get("quality_flags", 0),
            "related_children":  related_children,
            "related_parents":   related_parents,
            "lcil_domains":      lcil.get(table, []),
            "is_orphan":         not related_children and not related_parents,
        }
    return props


# ---------------------------------------------------------------------------
# 7. Build relationship edges list
# ---------------------------------------------------------------------------
def build_relationship_edges(edges: list[dict]) -> list[dict]:
    result = []
    for i, e in enumerate(edges):
        pk = _table_key(e["pk_table"])
        fk = _table_key(e["fk_table"])
        edge_id = f"{fk}__{e['fk_column']}__{pk}__{e['pk_column']}"
        result.append({
            "id":               edge_id,
            "fk_table":         fk,
            "fk_table_label":   e["fk_table"],
            "fk_column":        e["fk_column"],
            "pk_table":         pk,
            "pk_table_label":   e["pk_table"],
            "pk_column":        e["pk_column"],
            "relationship_class": "TRUE_FK",
            "confidence":       e["confidence"],
            "containment":      e["containment"],
            "semantic_similarity": e["semantic_similarity"],
            "reasoning":        e["reasoning"],
        })
    return result


# ---------------------------------------------------------------------------
# 8. Build table metrics
# ---------------------------------------------------------------------------
def build_table_metrics(profiles: dict[str, dict]) -> list[dict]:
    metrics = []
    for table, p in profiles.items():
        metrics.append({
            "id":            table,
            "label":         p.get("table_name") or table,
            "row_count":     p.get("row_count"),
            "column_count":  p.get("column_count", 0),
            "quality_score": p.get("quality_score", 0.0),
            "completeness":  p.get("completeness", 1.0),
            "pk":            p.get("pk"),
            "fk_count":      p.get("fk_count", 0),
            "quality_flags": p.get("quality_flags", 0),
        })
    return sorted(metrics, key=lambda x: x["label"])


# ---------------------------------------------------------------------------
# 9. Expand a single entity (BFS one level)
# ---------------------------------------------------------------------------
def expand_entity(
    entity_id: str,
    parent_to_children: dict[str, list[dict]],
    visited: list[str] | None = None,
) -> list[dict]:
    """Return direct children of entity_id with edge metadata."""
    visited_set = set(visited or [])
    children = []
    for edge in parent_to_children.get(entity_id, []):
        child = edge["child"]
        children.append({
            "id":            child,
            "label":         edge["child_display"],
            "has_children":  bool(parent_to_children.get(child)),
            "is_visited":    child in visited_set,
            "edge": {
                "fk_column":   edge["fk_column"],
                "pk_column":   edge["pk_column"],
                "confidence":  edge["confidence"],
                "containment": edge["containment"],
                "semantic_similarity": edge["semantic_similarity"],
                "reasoning":   edge["reasoning"],
                "relationship_class": "TRUE_FK",
            }
        })
    return children


# ---------------------------------------------------------------------------
# 10. Search
# ---------------------------------------------------------------------------
def search_tree(
    query: str,
    entity_props: dict[str, dict],
    profiles: dict[str, dict],
    min_score: float = 0.0,
) -> list[dict]:
    q = query.lower().strip()
    results = []
    for table, props in entity_props.items():
        score = 0.0
        reasons = []

        # Table name match
        label = props.get("label", table).lower()
        if q in label:
            score += 2.0
            reasons.append("table_name")
        if label.startswith(q):
            score += 1.0
            reasons.append("name_prefix")

        # PK match
        pk = (props.get("pk") or "").lower()
        if q in pk:
            score += 1.5
            reasons.append("pk")

        # Column match
        for col in props.get("columns", []):
            col_name = col.get("name", "").lower()
            sem = col.get("semantic_type", "").lower()
            if q in col_name or q in sem:
                score += 1.0
                reasons.append(f"column:{col['name']}")
                break

        # LCIL domains
        for domain in props.get("lcil_domains", []):
            if q in domain.lower():
                score += 0.5
                reasons.append(f"lcil:{domain}")

        # Quality filter
        qs = props.get("quality_score", 0.0)

        if score >= min_score and score > 0:
            results.append({
                "id":            table,
                "label":         props.get("label", table),
                "score":         score,
                "reasons":       reasons,
                "quality_score": qs,
                "row_count":     props.get("row_count"),
                "pk":            props.get("pk"),
            })

    results.sort(key=lambda x: -x["score"])
    return results[:50]


# ---------------------------------------------------------------------------
# 11. Main build → write JSON outputs
# ---------------------------------------------------------------------------
def build_all(force: bool = False) -> dict[str, Any]:
    TREE_OUT_DIR.mkdir(parents=True, exist_ok=True)

    tree_file   = TREE_OUT_DIR / "relationship_tree.json"
    entity_file = TREE_OUT_DIR / "entity_properties.json"
    edges_file  = TREE_OUT_DIR / "relationship_edges.json"
    metrics_file = TREE_OUT_DIR / "table_metrics.json"

    if not force and all(f.exists() for f in [tree_file, entity_file, edges_file, metrics_file]):
        # Return cached
        return {
            "tree":     json.loads(tree_file.read_text()),
            "entities": json.loads(entity_file.read_text()),
            "edges":    json.loads(edges_file.read_text()),
            "metrics":  json.loads(metrics_file.read_text()),
        }

    edges   = load_true_fk_edges()
    parent_to_children, child_to_parents = build_graph(edges)
    profiles = load_profiles()
    lcil     = load_lcil()

    tree     = build_relationship_tree(parent_to_children, profiles)
    entities = build_entity_properties(profiles, parent_to_children, child_to_parents, lcil)
    rel_edges = build_relationship_edges(edges)
    metrics  = build_table_metrics(profiles)

    tree_file.write_text(json.dumps(tree, indent=2), encoding="utf-8")
    entity_file.write_text(json.dumps(entities, indent=2), encoding="utf-8")
    edges_file.write_text(json.dumps(rel_edges, indent=2), encoding="utf-8")
    metrics_file.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    return {
        "tree":     tree,
        "entities": entities,
        "edges":    rel_edges,
        "metrics":  metrics,
        "stats": {
            "total_tables":        len(entities),
            "total_true_fk_edges": len(rel_edges),
            "root_nodes":          len(tree),
        }
    }


# ---------------------------------------------------------------------------
# Convenience accessors (used by FastAPI routes)
# ---------------------------------------------------------------------------
_CACHE: dict[str, Any] = {}

def get_cached() -> dict[str, Any]:
    global _CACHE
    if not _CACHE:
        _CACHE = build_all()
    return _CACHE

def invalidate_cache() -> None:
    global _CACHE
    _CACHE = {}


if __name__ == "__main__":
    result = build_all(force=True)
    print(f"✅ Built FKRTE tree:")
    print(f"   Tables:    {result['stats']['total_tables']}")
    print(f"   TRUE_FK:   {result['stats']['total_true_fk_edges']}")
    print(f"   Roots:     {result['stats']['root_nodes']}")
    print(f"   Output:    {TREE_OUT_DIR}")
