"""Validation script for plan1.md - Single PK per table with root ownership."""

import json
from profiler.services import profile_file

validation_tables = [
    "data/Application_Cities.csv",
    "data/purchasing_purchaseorderlines.csv",
    "data/purchasing_purchaseorders.csv",
    "data/sales_orders.csv",
    "data/sales_invoicelines.csv",
    "data/sales_specialdeals.csv",
    "data/warehouse_coldroomtemperatures.csv",
    "data/warehouse_colors.csv",
]

print("=" * 80)
print("PLAN1.MD VALIDATION - Single PK per Table with Root Ownership")
print("=" * 80)

all_pass = True

for p in validation_tables:
    r = profile_file(path=p, sample_size=1000, output_base="output")
    table_name = r.get("table_name")
    pk_candidates = r.get("pk_candidates", [])
    
    profile_path = r.get("profile_path")
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)
    
    col_map = {c.get("column_name", "").lower(): c for c in profile.get("columns", [])}
    
    pk_count = len(pk_candidates)
    check1 = pk_count == 1
    
    check2 = True
    if "lasteditedby" in col_map:
        if col_map["lasteditedby"].get("pk_candidate"):
            check2 = False
    
    check3 = True
    for temporal_col in ["validfrom", "validto"]:
        if temporal_col in col_map:
            if col_map[temporal_col].get("pk_candidate"):
                check3 = False
    
    check4 = True
    for c in profile.get("columns", []):
        for key in c.keys():
            if "fk" in key.lower() or "referenced" in key.lower() or "relational" in key.lower():
                check4 = False
                break
    
    table_pass = check1 and check2 and check3 and check4
    if not table_pass:
        all_pass = False
    
    status = "PASS" if table_pass else "FAIL"
    print(f"\n{status} | {table_name}")
    print(f"  PK count: {pk_count} (expected: 1) -> {'OK' if check1 else 'FAIL'}")
    print(f"  PK candidates: {pk_candidates}")
    print(f"  lasteditedby not PK: {'OK' if check2 else 'FAIL'}")
    print(f"  temporal not PK: {'OK' if check3 else 'FAIL'}")
    print(f"  no FK leakage: {'OK' if check4 else 'FAIL'}")

print("\n" + "=" * 80)
print(f"FINAL: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
print("=" * 80)
