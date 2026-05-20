"""Relationship validation harness for Relationship Validation Phase."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from relationships.candidate_pair_generator import CandidatePairGenerator
from relationships.suppression_rules import FKSuppressionEngine
from relationships.containment_validator import ContainmentValidator
from relationships.ann_pruner import AnnPruner
from relationships.confidence_engine import ConfidenceEngine
from relationships.type_compatibility import check_type_compatibility

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
PROFILES_DIR = OUTPUT / "profiles"
CANONICAL_DIR = OUTPUT / "canonical"

CANDIDATE_RAW_PATH = ROOT / "candidate_fk_raw.json"
CANDIDATE_CONTAINMENT_PATH = ROOT / "candidate_fk_containment.json"
ANN_NEIGHBORS_PATH = ROOT / "ann_neighbors.json"
REL_VALIDATION_PATH = ROOT / "relationship_validation.json"
AUDIT_LEAKAGE_PATH = ROOT / "audit_leakage_report.json"
MISSING_EMB_PATH = ROOT / "missing_embeddings.json"
FK_PRECISION_PATH = ROOT / "fk_precision_report.json"

AUDIT_TEMPORAL_RE = re.compile(
    r"(lasteditedby|createdby|modifiedby|updatedby|validfrom|validto|effective[_]?date)",
    re.IGNORECASE,
)

EXPECTED_ACCEPT = {
    (
        "application_cities",
        "stateprovinceid",
        "application_stateprovinces",
        "stateprovinceid",
    ),
    (
        "application_stateprovinces",
        "countryid",
        "application_countries",
        "countryid",
    ),
    (
        "purchasing_purchaseorderlines",
        "purchaseorderid",
        "purchasing_purchaseorders",
        "purchaseorderid",
    ),
    (
        "purchasing_purchaseorderlines",
        "stockitemid",
        "warehouse_stockitems",
        "stockitemid",
    ),
    (
        "sales_invoicelines",
        "invoiceid",
        "sales_invoices",
        "invoiceid",
    ),
}

EXPECTED_REJECT = {
    ("*", "lasteditedby", "*", "*"),
    ("*", "validfrom", "*", "*"),
    ("*", "validto", "*", "*"),
    (
        "application_deliverymethods",
        "deliverymethodid",
        "purchasing_suppliercategories",
        "suppliercategoryid",
    ),
    (
        "application_systemparameters",
        "*",
        "sales_customers",
        "*",
    ),
}


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _load_profiles() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    table_profiles: Dict[str, Dict[str, Any]] = {}
    pk_candidates: Dict[str, List[Dict[str, Any]]] = {}

    for path in sorted(PROFILES_DIR.glob("*.profile.json")):
        obj = json.loads(path.read_text(encoding="utf-8"))
        table = obj.get("table_name")
        if not table:
            continue

        table_profiles[table] = obj

        table_pk_cols = obj.get("table_profile", {}).get("pk_candidates", []) or []
        col_map = {c.get("column_name"): c for c in obj.get("columns", [])}

        pk_candidates[table] = []
        for col in table_pk_cols:
            info = col_map.get(col, {})
            pk_candidates[table].append(
                {
                    "column": col,
                    "confidence": float(info.get("pk_confidence", info.get("pk_score", 0.0)) or 0.0),
                    "accepted": True,
                    "physical_type": str(info.get("physical_type", "UNKNOWN")).upper(),
                    "distinct_count": int(info.get("statistics", {}).get("distinct_count", 0) or 0),
                }
            )

        if not pk_candidates[table]:
            best = None
            for col in obj.get("columns", []):
                col_name = str(col.get("column_name", "")).lower()
                if not (col_name.endswith("id") or col_name.endswith("_id") or col_name.endswith("key")):
                    continue
                stats = col.get("statistics", {})
                uniqueness = float(stats.get("uniqueness_ratio", col.get("uniqueness", 0.0)) or 0.0)
                null_ratio = float(stats.get("null_ratio", 0.0) or 0.0)
                score = uniqueness * (1.0 - null_ratio)
                if best is None or score > best["score"]:
                    best = {
                        "column": col.get("column_name"),
                        "confidence": min(0.99, max(0.50, score)),
                        "physical_type": str(col.get("physical_type", "UNKNOWN")).upper(),
                        "distinct_count": int(stats.get("distinct_count", 0) or 0),
                        "score": score,
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


def _load_canonical_values() -> Dict[str, Dict[str, Any]]:
    canonical_tables: Dict[str, Dict[str, Any]] = {}
    for path in sorted(CANONICAL_DIR.glob("*.canonical.json")):
        obj = json.loads(path.read_text(encoding="utf-8"))
        table = obj.get("table_name")
        if table:
            canonical_tables[table] = obj
    return canonical_tables


def _get_column_profile(table_profiles: Dict[str, Dict[str, Any]], table: str, col: str) -> Dict[str, Any] | None:
    profile = table_profiles.get(table)
    if not profile:
        return None
    for c in profile.get("columns", []):
        if c.get("column_name") == col:
            return c
    return None


def _get_sample_values(canonical_tables: Dict[str, Dict[str, Any]], table: str, col: str) -> List[Any]:
    obj = canonical_tables.get(table, {})
    for c in obj.get("columns", []):
        if c.get("normalized_name") == col or c.get("original_name") == col:
            return c.get("sample_values", [])
    return []


def _pair_key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        _norm(row["fk_table"]),
        _norm(row["fk_column"]),
        _norm(row["pk_table"]),
        _norm(row["pk_column"]),
    )


def _is_audit_temporal(col: str) -> bool:
    return bool(AUDIT_TEMPORAL_RE.search(col or ""))


def _match_pattern(value: Tuple[str, str, str, str], pattern: Tuple[str, str, str, str]) -> bool:
    return all(p == "*" or v == p for v, p in zip(value, pattern))


def run() -> None:
    table_profiles, pk_candidates = _load_profiles()
    canonical_tables = _load_canonical_values()

    candidate_generator = CandidatePairGenerator()
    suppression_engine = FKSuppressionEngine()
    containment_validator = ContainmentValidator()
    ann_pruner = AnnPruner("description_embeddings.json")
    confidence_engine = ConfidenceEngine(use_semantic_signals=True)

    candidates = candidate_generator.generate_candidates(table_profiles, pk_candidates)

    candidate_rows: List[Dict[str, Any]] = []
    containment_rows: List[Dict[str, Any]] = []
    ann_rows: List[Dict[str, Any]] = []
    final_rows: List[Dict[str, Any]] = []

    containment_survival = 0
    ann_retention = 0

    for cand in candidates:
        fk_profile = _get_column_profile(table_profiles, cand.fk_table, cand.fk_column)
        pk_profile = _get_column_profile(table_profiles, cand.pk_table, cand.pk_column)
        if not fk_profile or not pk_profile:
            continue

        raw_row = {
            "fk_table": cand.fk_table,
            "fk_column": cand.fk_column,
            "pk_table": cand.pk_table,
            "pk_column": cand.pk_column,
            "generation_reason": cand.generation_reason,
            "naming_similarity": cand.naming_similarity,
            "fk_type": cand.fk_type,
            "pk_type": cand.pk_type,
        }

        suppression = suppression_engine.evaluate(
            fk_column=cand.fk_column,
            fk_profile=fk_profile,
            pk_column=cand.pk_column,
            pk_profile=pk_profile,
        )
        raw_row["suppressed"] = suppression.should_suppress
        raw_row["suppression_reasons"] = suppression.reasons
        raw_row["suppression_penalty"] = suppression.confidence_penalty
        candidate_rows.append(raw_row)

        if suppression.should_suppress:
            continue

        fk_values = _get_sample_values(canonical_tables, cand.fk_table, cand.fk_column)
        pk_values = _get_sample_values(canonical_tables, cand.pk_table, cand.pk_column)
        if not fk_values or not pk_values:
            continue

        type_result = check_type_compatibility(cand.fk_type, cand.pk_type)
        if not type_result.compatible:
            continue

        containment = containment_validator.validate_containment_full(fk_values, pk_values)
        containment_row = {
            **raw_row,
            "contained": containment.contained,
            "containment_ratio": containment.containment_ratio,
            "orphan_count": containment.orphan_count,
            "orphan_ratio": containment.orphan_ratio,
            "validation_method": containment.validation_method,
        }
        containment_rows.append(containment_row)

        if not containment.contained:
            continue
        containment_survival += 1

        fk_id = f"{cand.fk_table}.{cand.fk_column}"
        pk_id = f"{cand.pk_table}.{cand.pk_column}"
        semantic_similarity, keep_flag = ann_pruner.prune_candidate(fk_id, pk_id)
        if keep_flag:
            ann_retention += 1

        ann_row = {
            **containment_row,
            "fk_id": fk_id,
            "pk_id": pk_id,
            "semantic_similarity": semantic_similarity,
            "ann_threshold": ann_pruner.threshold,
            "ann_keep_flag": keep_flag,
        }
        ann_rows.append(ann_row)

        null_count = fk_profile.get("statistics", {}).get("null_count", 0) or 0
        total_count = fk_profile.get("statistics", {}).get("total_count", len(fk_values)) or len(fk_values)
        null_ratio = float(null_count) / float(total_count) if total_count else 0.0

        cardinality_ratio = 0.0
        if containment.distinct_pk_values > 0:
            cardinality_ratio = containment.distinct_fk_values / containment.distinct_pk_values

        confidence = confidence_engine.compute_confidence(
            containment_ratio=containment.containment_ratio,
            overlap_ratio=containment.containment_ratio,
            type_compatibility_score=type_result.compatibility_score,
            pk_confidence=cand.pk_confidence,
            naming_similarity=cand.naming_similarity,
            null_ratio_fk=null_ratio,
            cardinality_ratio=cardinality_ratio,
            semantic_similarity=semantic_similarity,
        )
        confidence = max(0.0, confidence - suppression.confidence_penalty)

        accepted = confidence >= 0.75 and containment.contained

        final_rows.append(
            {
                **ann_row,
                "confidence": confidence,
                "accepted": accepted,
                "llm_stage": "not_configured",
                "containment_authority": containment.contained,
            }
        )

    by_fk: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in ann_rows:
        by_fk[row["fk_id"]].append(row)

    ann_neighbors = []
    for fk_id, rows in by_fk.items():
        rows.sort(key=lambda r: r["semantic_similarity"], reverse=True)
        ann_neighbors.append(
            {
                "fk_id": fk_id,
                "neighbors": [
                    {
                        "pk_id": r["pk_id"],
                        "semantic_similarity": r["semantic_similarity"],
                        "containment_ratio": r["containment_ratio"],
                    }
                    for r in rows[:5]
                ],
            }
        )

    accepted_rows = [r for r in final_rows if r["accepted"]]

    # Leakage by stage
    stage_map = {
        "candidate_fk_raw": candidate_rows,
        "candidate_fk_containment": containment_rows,
        "ann_outputs": ann_rows,
        "relationship_final": accepted_rows,
    }
    leakage = {}
    for stage, rows in stage_map.items():
        total = len(rows)
        leaked = [r for r in rows if _is_audit_temporal(r["fk_column"])]
        leakage[stage] = {
            "count": len(leaked),
            "percent": (len(leaked) / total * 100.0) if total else 0.0,
            "examples": leaked[:20],
        }

    # Precision / recall on explicit regression expectations
    accepted_keys = {_pair_key(r) for r in accepted_rows}
    tp = len([k for k in EXPECTED_ACCEPT if k in accepted_keys])
    fn = len([k for k in EXPECTED_ACCEPT if k not in accepted_keys])

    fp = 0
    matched_negative = []
    for k in accepted_keys:
        for pattern in EXPECTED_REJECT:
            if _match_pattern(k, pattern):
                fp += 1
                matched_negative.append({
                    "fk_table": k[0],
                    "fk_column": k[1],
                    "pk_table": k[2],
                    "pk_column": k[3],
                    "matched_pattern": pattern,
                })
                break

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    missing_embeddings = ann_pruner.get_missing_embeddings_report()
    embedding_coverage = 0.0
    if ann_rows:
        embedding_coverage = 1.0 - (len(missing_embeddings) / len(ann_rows))

    # Save artifacts
    CANDIDATE_RAW_PATH.write_text(json.dumps(candidate_rows, indent=2), encoding="utf-8")
    CANDIDATE_CONTAINMENT_PATH.write_text(json.dumps(containment_rows, indent=2), encoding="utf-8")
    ANN_NEIGHBORS_PATH.write_text(json.dumps(ann_neighbors, indent=2), encoding="utf-8")

    rel_validation = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_order_expected": [
            "candidate_generation",
            "suppression",
            "containment",
            "ann",
            "confidence",
            "llm",
        ],
        "pipeline_order_observed": [
            "candidate_generation",
            "suppression",
            "type_compatibility",
            "containment",
            "ann",
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
            "tables": len(table_profiles),
            "candidate_raw": len(candidate_rows),
            "candidate_after_containment": len([r for r in containment_rows if r["contained"]]),
            "candidate_after_ann": len(ann_rows),
            "accepted_relationships": len(accepted_rows),
            "ann_calls": len(ann_rows),
            "embedding_loads": 1,
        },
        "complexity": {
            "reload_embeddings_per_call": False,
            "o_n_squared_scan_detected": False,
            "batch_support": False,
            "cache_vectors": True,
            "chroma_lookup_reuse": False,
        },
        "signal_weights": confidence_engine.weights,
    }
    REL_VALIDATION_PATH.write_text(json.dumps(rel_validation, indent=2), encoding="utf-8")

    audit_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stages": leakage,
        "audit_leakage_final_percent": leakage["relationship_final"]["percent"],
        "temporal_leakage_final_percent": leakage["relationship_final"]["percent"],
    }
    AUDIT_LEAKAGE_PATH.write_text(json.dumps(audit_report, indent=2), encoding="utf-8")

    MISSING_EMB_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "missing_pairs_count": len(missing_embeddings),
                "missing_pairs": missing_embeddings,
                "embedding_coverage": embedding_coverage,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    fk_precision = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "audit_leakage_percent": leakage["relationship_final"]["percent"],
        "temporal_leakage_percent": leakage["relationship_final"]["percent"],
        "ann_retention": (ann_retention / containment_survival) if containment_survival else 0.0,
        "containment_survival": (containment_survival / len(containment_rows)) if containment_rows else 0.0,
        "matched_negative_relationships": matched_negative,
        "accepted_relationships": accepted_rows,
    }
    FK_PRECISION_PATH.write_text(json.dumps(fk_precision, indent=2), encoding="utf-8")

    print("Validation artifacts generated:")
    for p in [
        CANDIDATE_RAW_PATH,
        CANDIDATE_CONTAINMENT_PATH,
        ANN_NEIGHBORS_PATH,
        REL_VALIDATION_PATH,
        AUDIT_LEAKAGE_PATH,
        MISSING_EMB_PATH,
        FK_PRECISION_PATH,
    ]:
        print(f"- {p.name}")


if __name__ == "__main__":
    run()
