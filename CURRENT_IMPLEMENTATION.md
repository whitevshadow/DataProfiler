# Current Relationship Implementation

Generated: 2026-05-20

## Scope Reviewed

- relationships/relationship_engine.py
- relationships/ann_pruner.py
- relationships/confidence_engine.py
- relationships/containment_validator.py
- relationships/candidate_pair_generator.py
- relationships/suppression_rules.py
- relationships/semantic_embedding_engine.py

## Import/Dependency Graph

- RelationshipEngine
  - CandidatePairGenerator
  - FKSuppressionEngine
  - check_type_compatibility
  - BloomFilterEngine
  - ContainmentValidator
  - AnnPruner
  - ConfidenceEngine
- AnnPruner
  - JSON embedding file lookup (description_embeddings.json)
  - Cosine similarity (in-memory vectors)
- ConfidenceEngine
  - Weighted fusion of containment/type/naming/pk/semantic
- ContainmentValidator
  - Deterministic FK subset checks (authoritative)
- CandidatePairGenerator
  - Naming and type/cardinality heuristics for FK->PK candidates
- FKSuppressionEngine
  - Rule-based suppression/penalty layer for unsafe FK candidates
- SemanticEmbeddingEngine
  - Separate ANN/embedding generation path (NVIDIA embeddings)
  - Not currently wired as runtime store for AnnPruner

## Observed Runtime Order

Observed from source and runtime validation:

1. Candidate generation
2. Suppression
3. Type compatibility
4. Containment
5. ANN semantic scoring (advisory)
6. Confidence
7. Acceptance decision

Notes:

- ANN is after containment.
- LLM stage is not in this execution path.
- Containment remains acceptance authority (accepted requires containment.contained).

## Current Behavior Details

### RelationshipEngine

- suppression engine is initialized and active.
- missing PK metadata is backfilled with deterministic identifier fallback.
- ANN cannot veto containment-passing candidates.
- semantic similarity is included in confidence input and evidence.
- missing embedding diagnostics are persisted to missing_embeddings.json.

### AnnPruner

- embeddings loaded once at initialization.
- missing embedding fallback behavior:
  - semantic_similarity = 0.0
  - keep = true
  - pair recorded in missing diagnostics
- cosine similarity for available vectors.

### ConfidenceEngine

Current semantic weights:

- containment: 0.45
- semantic_similarity: 0.15
- type_compatibility: 0.15
- pk_confidence: 0.10
- naming_similarity: 0.15

This keeps semantic below containment and below dominance thresholds.

### ContainmentValidator

- exact set-based full containment with orphan accounting.
- authoritative pass/fail signal for relationship validity.

### CandidatePairGenerator

- avoids full O(N^2) column cross-product.
- naming heuristic first, then restricted type-compat fallback.
- cardinality ratio gate is sample-tolerant (1.05).

### FK Suppression

- temporal/audit fields are suppressed.
- low-cardinality FK suppression now penalizes confidence instead of hard reject in identifier-aligned cases.
- measure pattern matching corrected to suffix-based patterns (prevents false suppression of countryid).

### Semantic Embedding Engine / Chroma Readiness

- current engine uses remote embedding API and in-memory vectors.
- no ChromaEmbeddingStore implementation found.
- no chromadb collection integration found.
- AnnPruner still uses JSON file, not a Chroma backend.

## Runtime Smoke Test

Executed RelationshipEngine end-to-end after fixes:

- candidates generated: 436
- accepted relationships: 111
- pipeline completed without crash

## Generated Validation Artifacts

- candidate_fk_raw.json
- candidate_fk_containment.json
- ann_neighbors.json
- relationship_validation.json
- audit_leakage_report.json
- missing_embeddings.json
- fk_precision_report.json
