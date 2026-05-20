# CURRENT_SYSTEM

Generated: 2026-05-20T10:41:26.700972+00:00

## Findings
- descriptions entries: 367
- missing required description fields: 0
- audit-like semantic leakage in descriptions: 25
- temporal-like semantic leakage in descriptions: 0
- embeddings generated: 367 (non-zero: 367)
- candidate raw count: 436
- domain gate accepted: 103
- domain gate rejected: 333
- containment-pass count: 37
- ANN kept count: 37
- accepted relationships: 34
- final audit/temporal leakage percent: 0.00

## Verified Execution Order
1. profile/canonical load
2. descriptions validation + normalization
3. ChromaDB embedding population
4. structural candidate generation
5. hard suppression
6. containment validation (authority)
7. ANN pruning/ranking
8. cluster validation
9. confidence scoring
10. relationship artifact generation