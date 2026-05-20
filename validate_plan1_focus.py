"""Focused validation for plan1 PK tuning on previously failing tables."""

import json
import logging
from profiler.services import profile_file

# Reduce noisy suppression warnings in console output.
logging.getLogger("profiler.profiling.suppression_rules").setLevel(logging.ERROR)

validation_tables = [
    "data/purchasing_purchaseorderlines.csv",
    "data/purchasing_purchaseorders.csv",
    "data/sales_orders.csv",
    "data/sales_invoicelines.csv",
    "data/warehouse_coldroomtemperatures.csv",
]

print("=" * 80)
print("FOCUSED VALIDATION - PK root-first selection")
print("=" * 80)

all_pass = True

for path in validation_tables:
    result = profile_file(path=path, sample_size=1000, output_base="output")
    table_name = result.get("table_name", "unknown")
    pk_candidates = result.get("pk_candidates", [])

    with open(result["profile_path"], "r", encoding="utf-8") as handle:
        profile = json.load(handle)

    col_map = {c.get("column_name", "").lower(): c for c in profile.get("columns", [])}

    check_one_pk = len(pk_candidates) == 1

    check_temporal_audit = True
    for col in ("lasteditedby", "validfrom", "validto"):
        if col in col_map and col_map[col].get("pk_candidate"):
            check_temporal_audit = False

    check_fk_clean = True
    for col in profile.get("columns", []):
        for key in col.keys():
            key_l = key.lower()
            if "fk" in key_l or "referenced" in key_l or "relational" in key_l:
                check_fk_clean = False
                break

    passed = check_one_pk and check_temporal_audit and check_fk_clean
    all_pass = all_pass and passed

    print(f"\n{'PASS' if passed else 'FAIL'} | {table_name}")
    print(f"  pk_candidates={pk_candidates}")
    print(f"  exactly_one_pk={'OK' if check_one_pk else 'FAIL'}")
    print(f"  audit_temporal_not_pk={'OK' if check_temporal_audit else 'FAIL'}")
    print(f"  no_fk_leakage={'OK' if check_fk_clean else 'FAIL'}")

print("\n" + "=" * 80)
print(f"FINAL: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
print("=" * 80)
