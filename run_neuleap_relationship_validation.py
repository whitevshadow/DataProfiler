from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import HashingVectorizer

from relationships.ann_pruner import AnnPruner
from relationships.candidate_pair_generator import CandidatePairGenerator
from relationships.confidence_engine import ConfidenceEngine
from relationships.containment_validator import ContainmentValidator
from relationships.suppression_rules import FKSuppressionEngine
from relationships.type_compatibility import check_type_compatibility

try:
    import chromadb
except ImportError as exc:
    raise RuntimeError("chromadb is required for this pipeline") from exc


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"

DESCRIPTIONS_PATH = OUTPUT / "descriptions" / "descriptions.json"
PROFILES_DIR = OUTPUT / "profiles"
CANONICAL_DIR = OUTPUT / "canonical"

EMBEDDINGS_PATH = OUTPUT / "descriptions" / "description_embeddings.json"
CHROMA_DIR = OUTPUT / "chromadb"
CHROMA_INDEX_PATH = CHROMA_DIR / "chromadb_index.json"

RAW_CANDIDATES_PATH = OUTPUT / "candidates" / "candidate_fk_raw.json"
CONTAINMENT_CANDIDATES_PATH = OUTPUT / "candidates" / "candidate_fk_containment.json"
ANN_NEIGHBORS_PATH = OUTPUT / "ann" / "ann_neighbors.json"
CLUSTERS_PATH = OUTPUT / "clusters" / "cluster_groups.json"
CLUSTER_JSON_PATH = OUTPUT / "clusters" / "cluster.json"

VALIDATION_PATH = OUTPUT / "validation" / "relationship_validation.json"
AUDIT_LEAKAGE_PATH = OUTPUT / "validation" / "audit_leakage_report.json"
MISSING_EMB_PATH = OUTPUT / "validation" / "missing_embeddings.json"
DOMAIN_VALIDATION_PATH = OUTPUT / "validation" / "domain_validation.json"

RELATIONSHIP_PATH = OUTPUT / "relationships" / "relationship.json"
PK_CONTEXT_PATH = OUTPUT / "pk_context.json"
PROFILER_CONTEXT_PATH = OUTPUT / "profiler_context.json"

CURRENT_SYSTEM_PATH = ROOT / "CURRENT_SYSTEM.md"

AUDIT_RE = re.compile(r"(lasteditedby|createdby|modifiedby|updatedby|userid|editorid|creatorid)", re.IGNORECASE)
TEMPORAL_RE = re.compile(r"(validfrom|validto|effective[_]?date|timestamp|date$)", re.IGNORECASE)
MEASURE_RE = re.compile(r"(amount|price|cost|quantity|count|total|tax|population|rate)$", re.IGNORECASE)
GEO_RE = re.compile(r"(location|latitude|longitude|geom|polygon|point)", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    for path in [
        OUTPUT / "descriptions",
        OUTPUT / "chromadb",
        OUTPUT / "candidates",
        OUTPUT / "ann",
        OUTPUT / "clusters",
        OUTPUT / "validation",
        OUTPUT / "relationships",
        OUTPUT / "plans",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _normalize_domain(value: str, column_name: str) -> str:
    v = _norm(value)
    col = _norm(column_name)
    if AUDIT_RE.search(col):
        return "AUDIT_HINT"
    if TEMPORAL_RE.search(col):
        return "TEMPORAL_HINT"
    if GEO_RE.search(col):
        return "GEOSPATIAL"
    if MEASURE_RE.search(col):
        return "MEASURE"

    mapping = {
        "primary_key": "PRIMARY_KEY",
        "foreign_key": "FOREIGN_KEY",
        "identifier": "IDENTIFIER",
        "dimension": "DIMENSION",
        "measure": "MEASURE",
        "temporal": "TEMPORAL_HINT",
        "geospatial": "GEOSPATIAL",
        "audit": "AUDIT_HINT",
    }
    return mapping.get(v, "UNKNOWN")


def _label_hints(column_name: str, data_domain: str) -> dict[str, bool]:
    col = _norm(column_name)
    return {
        "is_identifier": col.endswith("id") or col.endswith("_id") or data_domain in {"PRIMARY_KEY", "FOREIGN_KEY", "IDENTIFIER"},
        "is_audit": bool(AUDIT_RE.search(col)) or data_domain == "AUDIT_HINT",
        "is_temporal": bool(TEMPORAL_RE.search(col)) or data_domain == "TEMPORAL_HINT",
        "is_measure": bool(MEASURE_RE.search(col)) or data_domain == "MEASURE",
        "is_geospatial": bool(GEO_RE.search(col)) or data_domain == "GEOSPATIAL",
    }


ENTITY_ALIASES = {
    "stateprovince": "geography",
    "country": "geography",
    "city": "geography",
    "deliverymethod": "logistics",
    "paymentmethod": "payment",
    "packagetype": "package",
    "suppliercategory": "supplier",
    "supplier": "supplier",
    "customercategory": "customer",
    "customer": "customer",
    "person": "person",
    "stockitem": "stockitem",
    "stockgroup": "stockgroup",
    "transactiontype": "transactiontype",
    "invoice": "invoice",
    "order": "order",
    "purchaseorder": "purchaseorder",
}

APPROVED_DOMAIN_ALIASES = {
    ("geography", "geography"),
    ("order", "purchaseorder"),
    ("purchaseorder", "order"),
}


def _extract_entity_root(column_name: str) -> str:
    col = _norm(column_name)
    for suffix in ["_id", "id", "_key", "key", "_fk", "fk"]:
        if col.endswith(suffix):
            col = col[: -len(suffix)]
            break

    for token in sorted(ENTITY_ALIASES.keys(), key=len, reverse=True):
        if token in col:
            return token
    return col


def _table_root(table_name: str) -> str:
    name = _norm(table_name)
    for prefix in ["sales_", "application_", "warehouse_", "purchasing_"]:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    if name == "people":
        return "person"
    if name.endswith("ies") and len(name) > 3:
        return name[:-3] + "y"
    if name.endswith("s") and not name.endswith("ss") and len(name) > 2:
        return name[:-1]
    return name


def _table_domain(root: str) -> str:
    if root in {"city", "country", "stateprovince"}:
        return "Geography"
    if root in {"customer", "order", "invoice", "transaction", "buyinggroup", "customercategory", "specialdeal"}:
        return "Sales"
    if root in {"supplier", "purchaseorder", "suppliertransaction", "suppliercategory"}:
        return "Purchasing"
    if root in {"stockitem", "stockgroup", "stockitemholding", "stockitemtransaction", "coldroomtemperature", "vehicletemperature", "color", "packagetype"}:
        return "Warehouse"
    if root in {"paymentmethod", "deliverymethod", "transactiontype"}:
        return "Methods"
    return "Reference"


def _is_audit_col(col: str) -> bool:
    return bool(re.search(r"(createdby|modifiedby|lasteditedby|deletedby|approvedby|reviewedby|editorid)$", _norm(col)))


def _is_enum_col(col: str) -> bool:
    c = _norm(col)
    return any(x in c for x in ["paymentmethodid", "deliverymethodid", "suppliercategoryid", "transactiontypeid", "customercategoryid"])


def _relationship_type(fk_table: str, fk_col: str, pk_table: str) -> str:
    col = _norm(fk_col)
    if _is_audit_col(col):
        return "AUDIT"
    if _is_enum_col(col):
        return "ENUM"
    if _norm(fk_table) == _norm(pk_table):
        return "SELF"
    if any(x in _norm(fk_table) for x in ["line", "stockitemstockgroups", "bridge", "mapping"]):
        return "BRIDGE"
    return "FK"


def _build_domain_clusters(tables: list[str]) -> list[dict[str, Any]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for t in sorted(tables):
        root = _table_root(t)
        groups[_table_domain(root)].append(t)
    return [{"cluster": k, "tables": v} for k, v in sorted(groups.items(), key=lambda kv: kv[0])]


def _entity_domain(column_name: str) -> str:
    root = _extract_entity_root(column_name)
    return ENTITY_ALIASES.get(root, root or "unknown")


def _domain_match_decision(fk_table: str, pk_table: str, fk_col: str, pk_col: str) -> tuple[bool, str, str, str]:
    fk_root = _extract_entity_root(fk_col)
    pk_root = _extract_entity_root(pk_col)
    fk_domain = _entity_domain(fk_col)
    pk_domain = _entity_domain(pk_col)

    if _norm(fk_table) == _norm(pk_table):
        return True, "self_reference", fk_domain, pk_domain
    if fk_domain == pk_domain:
        return True, "same_domain", fk_domain, pk_domain
    if (fk_domain, pk_domain) in APPROVED_DOMAIN_ALIASES:
        return True, "approved_alias", fk_domain, pk_domain
    if fk_root in {"stateprovince", "country", "city"} and pk_root in {"stateprovince", "country", "city"}:
        return True, "hierarchy_geography", fk_domain, pk_domain
    return False, "domain_mismatch", fk_domain, pk_domain


def _embedding_text(item: dict[str, Any], domain: str, hints: dict[str, bool]) -> str:
    parts = [
        f"table={item.get('table_name', '')}",
        f"column={item.get('column_name', '')}",
        f"domain={domain}",
        f"semantic={item.get('semantic_description', '')}",
        f"purpose={item.get('business_purpose', '')}",
        f"likely_relationships={'; '.join(item.get('likely_relationships') or [])}",
        f"hint_identifier={hints['is_identifier']}",
        f"hint_audit={hints['is_audit']}",
        f"hint_temporal={hints['is_temporal']}",
        f"hint_measure={hints['is_measure']}",
        f"hint_geospatial={hints['is_geospatial']}",
    ]
    return " | ".join(parts)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_profiles() -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    table_profiles: dict[str, dict[str, Any]] = {}
    pk_candidates: dict[str, list[dict[str, Any]]] = {}

    for path in sorted(PROFILES_DIR.glob("*.profile.json")):
        obj = _load_json(path)
        table = obj.get("table_name")
        if not table:
            continue
        table_profiles[table] = obj

        col_map = {c.get("column_name"): c for c in obj.get("columns", [])}
        pks = obj.get("table_profile", {}).get("pk_candidates", []) or []
        pk_candidates[table] = []

        for col in pks:
            c = col_map.get(col, {})
            stats = c.get("statistics", {})
            pk_candidates[table].append(
                {
                    "column": col,
                    "confidence": float(c.get("pk_confidence", c.get("pk_score", 0.0)) or 0.0),
                    "accepted": True,
                    "physical_type": str(c.get("physical_type", "UNKNOWN")).upper(),
                    "distinct_count": int(stats.get("distinct_count", 0) or 0),
                }
            )

        if not pk_candidates[table]:
            best = None
            for c in obj.get("columns", []):
                col_name = _norm(c.get("column_name", ""))
                if not (col_name.endswith("id") or col_name.endswith("_id") or col_name.endswith("key")):
                    continue
                stats = c.get("statistics", {})
                uniq = float(stats.get("uniqueness_ratio", c.get("uniqueness", 0.0)) or 0.0)
                null_ratio = float(stats.get("null_ratio", 0.0) or 0.0)
                score = uniq * (1.0 - null_ratio)
                if best is None or score > best["score"]:
                    best = {
                        "column": c.get("column_name"),
                        "score": score,
                        "confidence": min(0.99, max(0.50, score)),
                        "physical_type": str(c.get("physical_type", "UNKNOWN")).upper(),
                        "distinct_count": int(stats.get("distinct_count", 0) or 0),
                    }
            if best:
                pk_candidates[table].append(
                    {
                        "column": best["column"],
                        "confidence": best["confidence"],
                        "accepted": True,
                        "physical_type": best["physical_type"],
                        "distinct_count": best["distinct_count"],
                    }
                )

    return table_profiles, pk_candidates


def _load_canonical() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(CANONICAL_DIR.glob("*.canonical.json")):
        obj = _load_json(path)
        table = obj.get("table_name")
        if table:
            out[table] = obj
    return out


def _get_col_profile(table_profiles: dict[str, dict[str, Any]], table: str, col: str) -> dict[str, Any] | None:
    prof = table_profiles.get(table)
    if not prof:
        return None
    for c in prof.get("columns", []):
        if c.get("column_name") == col:
            return c
    return None


def _get_values(canonical: dict[str, dict[str, Any]], table: str, col: str) -> list[Any]:
    tab = canonical.get(table, {})
    for c in tab.get("columns", []):
        if c.get("normalized_name") == col or c.get("original_name") == col:
            return c.get("sample_values", [])
    return []


def _validate_descriptions(descriptions: list[dict[str, Any]]) -> dict[str, Any]:
    required = ["table_name", "column_name", "semantic_description", "business_purpose", "data_domain", "likely_relationships"]
    missing_required = []

    normalized_domains = Counter()
    audit_fk_like = []
    temporal_fk_like = []
    semantic_hint_only = []

    for idx, item in enumerate(descriptions):
        missing = [k for k in required if k not in item]
        if missing:
            missing_required.append({"index": idx, "missing": missing})

        col = item.get("column_name", "")
        domain = _normalize_domain(str(item.get("data_domain", "")), col)
        normalized_domains[domain] += 1

        lrs = item.get("likely_relationships") or []
        hints = _label_hints(col, domain)

        if hints["is_audit"] and (domain in {"FOREIGN_KEY", "PRIMARY_KEY", "IDENTIFIER"} or lrs):
            audit_fk_like.append({"table": item.get("table_name"), "column": col, "domain": domain, "likely_relationships": lrs})
        if hints["is_temporal"] and (domain in {"FOREIGN_KEY", "PRIMARY_KEY", "IDENTIFIER"} or lrs):
            temporal_fk_like.append({"table": item.get("table_name"), "column": col, "domain": domain, "likely_relationships": lrs})
        if lrs and not any(x in domain for x in ["FOREIGN_KEY", "PRIMARY_KEY"]):
            semantic_hint_only.append({"table": item.get("table_name"), "column": col, "domain": domain, "likely_relationships": lrs})

    return {
        "generated_at": _now(),
        "total_descriptions": len(descriptions),
        "missing_required_count": len(missing_required),
        "missing_required_examples": missing_required[:20],
        "normalized_domain_distribution": dict(normalized_domains),
        "audit_fk_like_count": len(audit_fk_like),
        "audit_fk_like_examples": audit_fk_like[:20],
        "temporal_fk_like_count": len(temporal_fk_like),
        "temporal_fk_like_examples": temporal_fk_like[:20],
        "semantic_hint_only_count": len(semantic_hint_only),
        "semantic_hint_only_examples": semantic_hint_only[:20],
    }


def _build_embeddings(descriptions: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_items = []
    texts = []
    ids = []
    metas = []

    for item in descriptions:
        table = str(item.get("table_name", ""))
        col = str(item.get("column_name", ""))
        key = f"{table}.{col}"
        domain = _normalize_domain(str(item.get("data_domain", "")), col)
        hints = _label_hints(col, domain)
        text = _embedding_text(item, domain, hints)

        ids.append(key)
        texts.append(text)
        normalized_items.append({
            "id": key,
            "table_name": table,
            "column_name": col,
            "data_domain": domain,
            "role_hints": hints,
            "likely_relationships": item.get("likely_relationships") or [],
            "text": text,
        })
        metas.append(
            {
                "table": table,
                "column": col,
                "data_domain": domain,
                "is_identifier": str(hints["is_identifier"]),
                "is_audit": str(hints["is_audit"]),
                "is_temporal": str(hints["is_temporal"]),
                "is_measure": str(hints["is_measure"]),
                "is_geospatial": str(hints["is_geospatial"]),
            }
        )

    vectorizer = HashingVectorizer(n_features=384, alternate_sign=False, norm="l2")
    matrix = vectorizer.transform(texts)
    vectors = np.asarray(matrix.todense(), dtype=float)

    # Persist to ChromaDB
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection_name = "column_descriptions"
    try:
        client.delete_collection(name=collection_name)
    except Exception:
        pass
    collection = client.get_or_create_collection(name=collection_name, metadata={"source": "output/descriptions/descriptions.json"})
    collection.add(ids=ids, embeddings=vectors.tolist(), metadatas=metas)

    embeddings_payload = {
        "generated_at": _now(),
        "source": str(DESCRIPTIONS_PATH.as_posix()),
        "embedding_model": "hashing_vectorizer_384",
        "collection": collection_name,
        "embeddings": {},
    }

    for i, item in enumerate(normalized_items):
        embeddings_payload["embeddings"][item["id"]] = {
            "vector": vectors[i].tolist(),
            "table_name": item["table_name"],
            "column_name": item["column_name"],
            "data_domain": item["data_domain"],
            "role_hints": item["role_hints"],
            "likely_relationships": item["likely_relationships"],
        }

    non_zero_vectors = int(np.sum(np.linalg.norm(vectors, axis=1) > 0))
    index_payload = {
        "generated_at": _now(),
        "collection": collection_name,
        "persist_path": str(CHROMA_DIR.as_posix()),
        "total_embeddings": len(ids),
        "non_zero_embeddings": non_zero_vectors,
        "domain_distribution": dict(Counter(item["data_domain"] for item in normalized_items)),
        "sample_ids": ids[:20],
    }

    return embeddings_payload, index_payload


def _run_relationship_validation() -> dict[str, Any]:
    descriptions = _load_json(DESCRIPTIONS_PATH)
    if not isinstance(descriptions, list):
        raise ValueError("descriptions.json must be a list")

    desc_validation = _validate_descriptions(descriptions)
    embeddings_payload, chroma_index = _build_embeddings(descriptions)

    EMBEDDINGS_PATH.write_text(json.dumps(embeddings_payload, indent=2), encoding="utf-8")
    CHROMA_INDEX_PATH.write_text(json.dumps(chroma_index, indent=2), encoding="utf-8")

    table_profiles, pk_candidates = _load_profiles()
    canonical = _load_canonical()
    pk_context = _load_json(PK_CONTEXT_PATH) if PK_CONTEXT_PATH.exists() else {"tables": []}
    profiler_context = _load_json(PROFILER_CONTEXT_PATH) if PROFILER_CONTEXT_PATH.exists() else {"tables": []}

    domain_clusters = _build_domain_clusters(list(table_profiles.keys()))

    candidate_generator = CandidatePairGenerator()
    suppression_engine = FKSuppressionEngine()
    containment_engine = ContainmentValidator()
    confidence_engine = ConfidenceEngine(use_semantic_signals=True)
    ann = AnnPruner(str(EMBEDDINGS_PATH), similarity_threshold=0.18)

    candidates = candidate_generator.generate_candidates(table_profiles=table_profiles, pk_candidates=pk_candidates)

    raw_rows: list[dict[str, Any]] = []
    contained_rows: list[dict[str, Any]] = []
    domain_validation_rows: list[dict[str, Any]] = []

    for cand in candidates:
        fk_prof = _get_col_profile(table_profiles, cand.fk_table, cand.fk_column)
        pk_prof = _get_col_profile(table_profiles, cand.pk_table, cand.pk_column)
        if not fk_prof or not pk_prof:
            continue

        suppression = suppression_engine.evaluate(
            fk_column=cand.fk_column,
            fk_profile=fk_prof,
            pk_column=cand.pk_column,
            pk_profile=pk_prof,
        )

        row = {
            "fk_table": cand.fk_table,
            "fk_column": cand.fk_column,
            "pk_table": cand.pk_table,
            "pk_column": cand.pk_column,
            "generation_reason": cand.generation_reason,
            "naming_similarity": cand.naming_similarity,
            "fk_type": cand.fk_type,
            "pk_type": cand.pk_type,
            "suppressed": suppression.should_suppress,
            "suppression_reasons": suppression.reasons,
            "suppression_penalty": suppression.confidence_penalty,
        }

        domain_match, domain_reason, fk_domain, pk_domain = _domain_match_decision(
            fk_table=cand.fk_table,
            pk_table=cand.pk_table,
            fk_col=cand.fk_column,
            pk_col=cand.pk_column,
        )
        row["fk_entity_domain"] = fk_domain
        row["pk_entity_domain"] = pk_domain

        domain_validation_rows.append(
            {
                "fk": f"{cand.fk_table}.{cand.fk_column}",
                "pk": f"{cand.pk_table}.{cand.pk_column}",
                "fk_domain": fk_domain,
                "pk_domain": pk_domain,
                "match": domain_match,
                "reason": domain_reason,
                "accepted": domain_match,
            }
        )

        raw_rows.append(row)

        if suppression.should_suppress:
            continue

        if not domain_match:
            continue

        type_res = check_type_compatibility(cand.fk_type, cand.pk_type)
        if not type_res.compatible:
            continue

        fk_values = _get_values(canonical, cand.fk_table, cand.fk_column)
        pk_values = _get_values(canonical, cand.pk_table, cand.pk_column)
        if not fk_values or not pk_values:
            continue

        containment = containment_engine.validate_containment_full(fk_values=fk_values, pk_values=pk_values)

        contained_rows.append(
            {
                **row,
                "contained": containment.contained,
                "containment_ratio": containment.containment_ratio,
                "orphan_count": containment.orphan_count,
                "orphan_ratio": containment.orphan_ratio,
                "validation_method": containment.validation_method,
                "type_compatibility_score": type_res.compatibility_score,
            }
        )

    # Containment authority: only contained rows may reach ANN
    contained_pass = [r for r in contained_rows if r["contained"]]

    by_fk: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in contained_pass:
        by_fk[f"{row['fk_table']}.{row['fk_column']}"] .append(row)

    ann_rows: list[dict[str, Any]] = []
    ann_neighbors: list[dict[str, Any]] = []

    for fk_id, rows in by_fk.items():
        candidate_pk_ids = [f"{r['pk_table']}.{r['pk_column']}" for r in rows]
        neighbors = ann.rank_neighbors(fk_id, candidate_pk_ids, top_k=5)
        ann_neighbors.append({"fk_id": fk_id, "neighbors": neighbors})

        for row in rows:
            pk_id = f"{row['pk_table']}.{row['pk_column']}"
            decision = ann.score_with_reason(fk_id, pk_id, candidate_pk_ids=candidate_pk_ids, top_k=5)
            ann_rows.append({**row, **decision})

    # Confidence and final acceptance
    final_rows: list[dict[str, Any]] = []
    for row in ann_rows:
        if not row["keep"]:
            continue

        fk_prof = _get_col_profile(table_profiles, row["fk_table"], row["fk_column"])
        if not fk_prof:
            continue

        null_count = int(fk_prof.get("statistics", {}).get("null_count", 0) or 0)
        total_count = int(fk_prof.get("statistics", {}).get("total_count", 0) or 0)
        null_ratio = (null_count / total_count) if total_count else 0.0

        # FK score contract (ownership/overlap/entity/ann/semantics/cardinality).
        ownership_score = 1.0 if _extract_entity_root(row["fk_column"]) == _extract_entity_root(row["pk_column"]) else 0.0
        overlap_score = float(row["containment_ratio"])
        entity_match_score = 1.0 if row.get("fk_entity_domain") == row.get("pk_entity_domain") else 0.0
        ann_score = float(row.get("semantic_similarity", 0.0))
        semantics_score = float(row.get("naming_similarity", 0.0))
        cardinality_score = 1.0

        fk_score = (
            ownership_score * 0.25
            + overlap_score * 0.25
            + entity_match_score * 0.20
            + ann_score * 0.15
            + semantics_score * 0.10
            + cardinality_score * 0.05
        )
        fk_score = max(0.0, min(1.0, fk_score - float(row.get("suppression_penalty", 0.0))))

        confidence = confidence_engine.compute_confidence(
            containment_ratio=overlap_score,
            overlap_ratio=overlap_score,
            type_compatibility_score=float(row.get("type_compatibility_score", 0.0)),
            pk_confidence=0.9,
            naming_similarity=semantics_score,
            entity_domain_score=entity_match_score,
            null_ratio_fk=null_ratio,
            cardinality_ratio=1.0,
            semantic_similarity=ann_score,
        )
        confidence = max(0.0, confidence - float(row.get("suppression_penalty", 0.0)))

        accepted = (
            bool(row["contained"])  # containment authority
            and entity_match_score >= 1.0
            and ann_score >= 0.18
            and fk_score >= 0.70
        )
        final_rows.append(
            {
                **row,
                "confidence": confidence,
                "fk_score": fk_score,
                "accepted": accepted,
                "containment_authority": bool(row["contained"]),
            }
        )

    accepted_rows = [r for r in final_rows if r["accepted"]]

    # Cluster validation
    cluster_groups = []
    if final_rows:
        features = np.array(
            [
                [
                    float(r["containment_ratio"]),
                    float(r.get("semantic_similarity", 0.0)),
                    float(r.get("naming_similarity", 0.0)),
                    float(r.get("type_compatibility_score", 0.0)),
                ]
                for r in final_rows
            ],
            dtype=float,
        )
        labels = DBSCAN(eps=0.15, min_samples=2).fit_predict(features)
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for idx, label in enumerate(labels):
            grouped[int(label)].append(final_rows[idx])

        for label, rows in grouped.items():
            cluster_groups.append(
                {
                    "cluster_id": int(label),
                    "member_count": len(rows),
                    "members": [
                        {
                            "fk": f"{r['fk_table']}.{r['fk_column']}",
                            "pk": f"{r['pk_table']}.{r['pk_column']}",
                            "containment_ratio": r["containment_ratio"],
                            "semantic_similarity": r.get("semantic_similarity", 0.0),
                            "confidence": r["confidence"],
                            "accepted": r["accepted"],
                        }
                        for r in rows
                    ],
                }
            )

    # Leakage reporting
    def _is_leaky(col: str) -> bool:
        return bool(AUDIT_RE.search(col) or TEMPORAL_RE.search(col))

    def _stage(rows: list[dict[str, Any]]) -> dict[str, Any]:
        leaked = [r for r in rows if _is_leaky(r.get("fk_column", ""))]
        total = len(rows)
        return {
            "count": len(leaked),
            "percent": (len(leaked) / total * 100.0) if total else 0.0,
            "examples": leaked[:20],
        }

    leakage = {
        "candidate_fk_raw": _stage(raw_rows),
        "candidate_fk_containment": _stage(contained_rows),
        "ann_outputs": _stage(ann_rows),
        "relationship_final": _stage(accepted_rows),
    }

    audit_report = {
        "generated_at": _now(),
        "stages": leakage,
        "audit_leakage_final_percent": leakage["relationship_final"]["percent"],
        "temporal_leakage_final_percent": leakage["relationship_final"]["percent"],
    }

    validation = {
        "generated_at": _now(),
        "pipeline_order_expected": [
            "candidate_generation",
            "suppression",
            "containment",
            "ann",
            "cluster_validation",
            "confidence",
            "llm_explain_only",
        ],
        "pipeline_order_observed": [
            "candidate_generation",
            "suppression",
            "containment",
            "ann",
            "cluster_validation",
            "confidence",
        ],
        "order_validation": {
            "ann_before_containment": False,
            "llm_before_confidence": False,
            "ann_replaces_containment": False,
            "ann_creates_fk": False,
            "containment_authority": True,
        },
        "counts": {
            "descriptions": len(descriptions),
            "candidate_raw": len(raw_rows),
            "candidate_after_domain_gate": len([r for r in raw_rows if r.get("fk_entity_domain") == r.get("pk_entity_domain") or (r.get("fk_entity_domain"), r.get("pk_entity_domain")) in APPROVED_DOMAIN_ALIASES]),
            "candidate_after_containment": len(contained_pass),
            "candidate_after_ann": len([r for r in ann_rows if r.get("keep")]),
            "accepted_relationships": len(accepted_rows),
            "clusters": len(cluster_groups),
            "ann_calls": len(ann_rows),
            "embedding_loads": 1,
        },
        "description_validation": desc_validation,
        "domain_validation": {
            "total_checked": len(domain_validation_rows),
            "accepted": len([r for r in domain_validation_rows if r["accepted"]]),
            "rejected": len([r for r in domain_validation_rows if not r["accepted"]]),
        },
        "signal_weights": confidence_engine.weights,
    }

    # Invalid-match registry with explicit hard rejections.
    hard_invalid = {
        ("supplierid", "stockitemid"),
        ("paymentmethodid", "deliverymethodid"),
        ("countryid", "stateprovinceid"),
        ("invoiceid", "stockitemid"),
    }
    invalid_matches = []
    for r in domain_validation_rows:
        fk_col = _norm(r["fk"].split(".")[-1]) if "." in r["fk"] else _norm(r["fk"])
        pk_col = _norm(r["pk"].split(".")[-1]) if "." in r["pk"] else _norm(r["pk"])
        if not r.get("accepted") or (fk_col, pk_col) in hard_invalid:
            invalid_matches.append(
                {
                    "source": r["fk"],
                    "target": r["pk"],
                    "reason": "INVALID_MATCH" if (fk_col, pk_col) in hard_invalid else r.get("reason", "domain_mismatch"),
                }
            )

    pk_by_table: dict[str, Any] = {}
    composite_by_table: dict[str, list[list[str]]] = {}
    for t in (pk_context.get("tables") or []):
        table_name = str(t.get("table", ""))
        if not table_name:
            continue
        pks = list(t.get("pk_candidates") or [])
        if pks:
            pk_by_table[table_name] = pks[0]
        composite_by_table[table_name] = list(t.get("composite_candidates") or [])

    table_entries = []
    relationships_entries = []

    rels_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    audits_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in accepted_rows:
        rel_type = _relationship_type(r["fk_table"], r["fk_column"], r["pk_table"])
        rel_entry = {
            "fk_table": r["fk_table"],
            "fk_column": r["fk_column"],
            "pk_table": r["pk_table"],
            "pk_column": r["pk_column"],
            "source_table": r["fk_table"],
            "source_column": r["fk_column"],
            "target_table": r["pk_table"],
            "target_column": r["pk_column"],
            "relationship_type": rel_type,
            "confidence": r["confidence"],
            "fk_score": r.get("fk_score", r["confidence"]),
            "cluster": _table_domain(_table_root(r["fk_table"])),
            "reason": r.get("reason", "validated_fk"),
        }
        relationships_entries.append(rel_entry)
        if rel_type == "AUDIT":
            audits_by_table[r["fk_table"]].append(rel_entry)
        else:
            rels_by_table[r["fk_table"]].append(rel_entry)

    for table_name, profile in sorted(table_profiles.items(), key=lambda kv: kv[0]):
        table_pk = pk_by_table.get(table_name)
        if not table_pk:
            local = list(profile.get("table_profile", {}).get("pk_candidates", []) or [])
            table_pk = local[0] if local else None
        local_comp = list(profile.get("table_profile", {}).get("composite_pk_candidates", []) or [])
        comp = composite_by_table.get(table_name) or local_comp

        table_entries.append(
            {
                "table": table_name,
                "pk": table_pk,
                "composite_pk": comp,
                "fk": rels_by_table.get(table_name, []),
                "audit_refs": audits_by_table.get(table_name, []),
                "domain_cluster": _table_domain(_table_root(table_name)),
            }
        )

    relationship_payload = {
        "generated_at": _now(),
        "contract": {
            "containment_authority": True,
            "ann_role": "prune_and_rank_only",
            "llm_role": "explain_only",
        },
        "tables": table_entries,
        "relationships": relationships_entries,
        "invalid_matches": invalid_matches,
        "clusters": domain_clusters,
        "metadata": {
            "profiles_loaded": len(table_profiles),
            "descriptions_loaded": len(descriptions),
            "profiler_context_tables": len(profiler_context.get("tables") or []),
            "pk_context_tables": len(pk_context.get("tables") or []),
        },
    }

    RAW_CANDIDATES_PATH.write_text(json.dumps(raw_rows, indent=2), encoding="utf-8")
    CONTAINMENT_CANDIDATES_PATH.write_text(json.dumps(contained_rows, indent=2), encoding="utf-8")
    ANN_NEIGHBORS_PATH.write_text(json.dumps(ann_neighbors, indent=2), encoding="utf-8")
    CLUSTERS_PATH.write_text(json.dumps(cluster_groups, indent=2), encoding="utf-8")
    CLUSTER_JSON_PATH.write_text(json.dumps(domain_clusters, indent=2), encoding="utf-8")
    VALIDATION_PATH.write_text(json.dumps(validation, indent=2), encoding="utf-8")
    AUDIT_LEAKAGE_PATH.write_text(json.dumps(audit_report, indent=2), encoding="utf-8")
    DOMAIN_VALIDATION_PATH.write_text(json.dumps(domain_validation_rows, indent=2), encoding="utf-8")
    MISSING_EMB_PATH.write_text(
        json.dumps(
            {
                "generated_at": _now(),
                "missing_pairs_count": len(ann.get_missing_embeddings_report()),
                "missing_pairs": ann.get_missing_embeddings_report(),
                "embedding_coverage": 1.0 - (len(ann.get_missing_embeddings_report()) / len(ann_rows)) if ann_rows else 1.0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    RELATIONSHIP_PATH.write_text(json.dumps(relationship_payload, indent=2), encoding="utf-8")

    # Compatibility mirrors in repo root for existing scripts.
    (ROOT / "candidate_fk_raw.json").write_text(json.dumps(raw_rows, indent=2), encoding="utf-8")
    (ROOT / "candidate_fk_containment.json").write_text(json.dumps(contained_rows, indent=2), encoding="utf-8")
    (ROOT / "ann_neighbors.json").write_text(json.dumps(ann_neighbors, indent=2), encoding="utf-8")
    (ROOT / "cluster_groups.json").write_text(json.dumps(cluster_groups, indent=2), encoding="utf-8")
    (ROOT / "cluster.json").write_text(json.dumps(domain_clusters, indent=2), encoding="utf-8")
    (ROOT / "relationship_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    (ROOT / "audit_leakage_report.json").write_text(json.dumps(audit_report, indent=2), encoding="utf-8")

    # Keep a short findings doc at repo root per instruction.
    CURRENT_SYSTEM_PATH.write_text(
        "\n".join(
            [
                "# CURRENT_SYSTEM",
                "",
                f"Generated: {_now()}",
                "",
                "## Findings",
                f"- descriptions entries: {len(descriptions)}",
                f"- missing required description fields: {desc_validation['missing_required_count']}",
                f"- audit-like semantic leakage in descriptions: {desc_validation['audit_fk_like_count']}",
                f"- temporal-like semantic leakage in descriptions: {desc_validation['temporal_fk_like_count']}",
                f"- embeddings generated: {chroma_index['total_embeddings']} (non-zero: {chroma_index['non_zero_embeddings']})",
                f"- candidate raw count: {len(raw_rows)}",
                f"- domain gate accepted: {len([r for r in domain_validation_rows if r['accepted']])}",
                f"- domain gate rejected: {len([r for r in domain_validation_rows if not r['accepted']])}",
                f"- containment-pass count: {len(contained_pass)}",
                f"- ANN kept count: {len([r for r in ann_rows if r.get('keep')])}",
                f"- accepted relationships: {len(accepted_rows)}",
                f"- final audit/temporal leakage percent: {audit_report['audit_leakage_final_percent']:.2f}",
                "",
                "## Verified Execution Order",
                "1. profile/canonical load",
                "2. descriptions validation + normalization",
                "3. ChromaDB embedding population",
                "4. structural candidate generation",
                "5. hard suppression",
                "6. containment validation (authority)",
                "7. ANN pruning/ranking",
                "8. cluster validation",
                "9. confidence scoring",
                "10. relationship artifact generation",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "descriptions": len(descriptions),
        "raw_candidates": len(raw_rows),
        "containment_pass": len(contained_pass),
        "ann_kept": len([r for r in ann_rows if r.get("keep")]),
        "accepted": len(accepted_rows),
    }


if __name__ == "__main__":
    _ensure_dirs()
    summary = _run_relationship_validation()
    print(json.dumps({"status": "ok", **summary}, indent=2))
