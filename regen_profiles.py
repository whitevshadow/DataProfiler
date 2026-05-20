"""Regenerate all profiles with fixed profiler."""
from profiler.profiling.profiling_engine import batch_profile
from pathlib import Path
import time
import json

start = time.time()
results = batch_profile(
    Path('output/canonical'),
    Path('output/profiles'),
    parallel=True,
    max_workers=4
)
elapsed = time.time() - start

print(f'\n✅ Re-profiled {len(results)} tables in {elapsed:.1f}s')

# Check sample results
print('\nSample results:')
p1 = json.load(open('output/profiles/application_people.profile.json'))
p2 = json.load(open('output/profiles/Sales_Customers.profile.json'))
p3 = json.load(open('output/profiles/sales_orders.profile.json'))

print(f"  application_people:")
print(f"    row_count: {p1['table_profile']['row_count_estimate']}")
print(f"    PK candidates: {p1['table_profile']['pk_candidates']}")

print(f"  Sales_Customers:")
print(f"    row_count: {p2['table_profile']['row_count_estimate']}")
print(f"    PK candidates: {p2['table_profile']['pk_candidates']}")

print(f"  sales_orders:")
print(f"    row_count: {p3['table_profile']['row_count_estimate']}")
print(f"    PK candidates: {p3['table_profile']['pk_candidates']}")

print("\n✅ All profiles regenerated successfully!")
