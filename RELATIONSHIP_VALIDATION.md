# Relationship Validation Phase

Generated: 2026-05-20

## Validation Outcome

Validation executed across candidate generation, suppression, containment, ANN semantics, confidence scoring, leakage checks, and regression targets.

Implementation was validated first, then architecture issues were patched.

No direct edits were made to relationship.json.

## Pipeline Order Validation

Expected:

candidate generation -> suppression -> containment -> ANN -> confidence -> LLM

Observed:

candidate generation -> suppression -> type compatibility -> containment -> ANN -> confidence

Status:

- ANN before containment: false
- LLM before confidence: false
- ANN replacing containment: false
- ANN creating FK: false
- containment authority: true

Result: PASS (containment remains authoritative)

## ANN Integration Validation

Checks:

- description_embeddings.json present: no
- missing embedding handling crashes: no
- missing embedding handling rejects candidate: no
- fallback semantic similarity on missing: 0.0
- candidate retained when embedding missing: yes
- missing embedding diagnostics emitted: yes (missing_embeddings.json)
- cosine metric: yes
- threshold handling: yes
- vector normalization: cosine denominator normalization in place
- batch ANN retrieval in AnnPruner: no (pairwise only)

Result: PARTIAL PASS

Reason:

- fallback behavior is correct and non-destructive.
- embedding coverage is low due absent embedding store/file.

## Complexity Validation

Checks:

- embedding load once per run: yes
- vector cache reuse: yes
- reload per candidate: no
- O(N^2) raw cross product in runtime path: not detected
- batch retrieval in AnnPruner: no
- Chroma lookup reuse: no (not implemented yet)

Result: PASS with optimization gaps

## Containment Authority Validation

Validated behavior:

- containment pass + ANN low -> retained
- containment fail + ANN high -> rejected by containment gate
- acceptance requires containment.contained true

Result: PASS

## Audit/Temporal Leakage Validation

From audit_leakage_report.json:

- candidate_fk_raw leakage: 0.0%
- candidate_fk_containment leakage: 0.0%
- ann_outputs leakage: 0.0%
- relationship_final leakage: 0.0%

Result: PASS

## Semantic Signal Validation

Current weights:

- containment: 0.45
- semantic_similarity: 0.15
- type_compatibility: 0.15
- naming_similarity: 0.15
- pk_confidence: 0.10

Constraint checks:

- semantic <= 20%: pass
- containment >= 40%: pass
- naming >= 15%: pass
- type >= 15%: pass

Result: PASS

## Regression Validation (Step 10)

Expected accept cases:

- Application_Cities.stateprovinceid -> Application_StateProvinces.stateprovinceid
- Application_StateProvinces.countryid -> Application_Countries.countryid
- purchasing_purchaseorderlines.purchaseorderid -> purchasing_purchaseorders.purchaseorderid
- purchasing_purchaseorderlines.stockitemid -> warehouse_stockitems.stockitemid
- sales_invoicelines.invoiceid -> sales_invoices.invoiceid

Expected reject cases:

- lasteditedby joins
- validfrom joins
- deliverymethod -> suppliercategory
- systemparameter -> customer

Metrics from fk_precision_report.json:

- precision: 1.00
- recall: 1.00
- audit leakage: 0.0%
- temporal leakage: 0.0%
- ANN retention: 1.00
- containment survival: 0.3165

Result: PASS for specified regression set

## ChromaDB Readiness Validation

Current state:

- description_embeddings JSON path expected by AnnPruner: yes
- ChromaEmbeddingStore implementation found: no
- chromadb collection wiring found: no
- collection column_descriptions provisioning: no
- persistent path/metadata/batch insert/latency hooks: no

Result: NOT READY

## Architecture Issues Found and Fixed

1. RelationshipEngine missing suppression engine initialization
- Fixed by wiring FKSuppressionEngine in constructor.

2. ANN could veto candidates before confidence
- Fixed by making ANN advisory only; containment stays authoritative.

3. Missing embedding fallback was unsafe for trust semantics
- Fixed behavior to semantic_similarity=0.0 and keep candidate.
- Added missing pair diagnostics export.

4. Confidence weighting allowed semantic to dominate naming requirement
- Adjusted weights to maintain containment dominance and naming/type minimums.

5. FK low-cardinality suppression caused false negatives
- Converted hard suppression path to penalty in aligned identifier cases.

6. Measure suppression overmatched countryid ("count" substring)
- Fixed to suffix-anchored metric patterns.

7. Missing PK metadata caused silent recall loss (e.g., sales_invoices.invoiceid)
- Added deterministic PK fallback hydration in RelationshipEngine.

## Success Criteria Check

- Containment authority = TRUE: PASS
- ANN override = FALSE: PASS
- Audit leakage < 0.5%: PASS
- Temporal leakage < 0.5%: PASS
- Embedding coverage > 95%: FAIL (description embeddings unavailable)
- ANN cache working: PASS
- Precision > 0.92: PASS
- Recall > 0.88: PASS
- No silent FK loss (regression set): PASS

## Remaining Blocker

Embedding coverage remains below target because description_embeddings.json is not present and no Chroma-backed embedding store is implemented/wired yet.

This is now isolated as infrastructure readiness, not a pipeline correctness bug.
