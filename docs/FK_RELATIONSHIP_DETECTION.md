# Foreign Key Relationship Detection Layer

**Enterprise-Grade Semantic Data Intelligence Engine (SDIE)**  
**Version:** 1.0.0  
**Schema Version:** v1.0.0  
**Author:** SDIE Architecture Team  
**Date:** 2026-05-15

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Design Principles](#design-principles)
4. [Pipeline Stages](#pipeline-stages)
5. [Algorithms & Data Structures](#algorithms--data-structures)
6. [Scalability & Performance](#scalability--performance)
7. [Output Schema](#output-schema)
8. [Production Deployment](#production-deployment)
9. [Future Enhancements](#future-enhancements)

---

## Executive Summary

The **FK Relationship Detection Layer** is a production-grade, deterministic-first relationship intelligence system that detects foreign key relationships across enterprise datasets.

### Key Features

- **Deterministic Validation**: Containment validation is authoritative truth
- **Scalable Architecture**: Avoids O(n²) explosion, scales to TB-scale data
- **Explainable Evidence**: Every relationship has confidence scores and reasoning
- **Modular Design**: Each component is isolated and testable
- **Bloom Filter Pruning**: Efficient probabilistic rejection of impossible relationships
- **Suppression Rules**: Prevents invalid FK patterns (temporal, boolean, descriptive)
- **Graph-Ready Output**: Exports to multiple graph formats (JSON, DOT, NetworkX)

### Pipeline Position

```
Layer 1: Connector          → Connect to data sources
Layer 2: Validator           → Validate format/encoding
Layer 2.5: Classifier        → Classify complexity
Layer 3: Planner             → Plan execution strategy
Layer 4: Sampler             → Adaptive sampling
Layer 5: Format Engines      → Parse to CanonicalTable
Layer 6: Profiling Engine    → Statistics & PK detection
Layer 7: RELATIONSHIP LAYER  → FK detection (THIS LAYER)
```

### Input Artifacts

- **FileProfile.json**: Column statistics, distinct counts, null ratios
- **CanonicalTable.json**: Schema + sample values for validation
- **PK Candidates**: List of primary key candidates per table

### Output Artifact

- **RelationshipReport.json**: Detected FK relationships with evidence, validation, and confidence scores

---

## System Architecture

### Module Structure

```
relationships/
├── __init__.py                      # Package exports
├── relationship_models.py           # Pydantic data models
├── relationship_engine.py           # Main orchestrator
├── candidate_pair_generator.py     # Generate FK->PK pairs (avoid O(n²))
├── type_compatibility.py           # Type matching rules
├── bloom_filter_engine.py          # Probabilistic pruning
├── containment_validator.py        # Authoritative validation
├── confidence_engine.py            # Evidence fusion
├── suppression_rules.py            # Invalid pattern detection
├── relationship_serializer.py      # JSON output
└── graph_builder.py                # Graph export utilities
```

### Component Responsibilities

| Component | Responsibility | Key Output |
|-----------|----------------|------------|
| **CandidatePairGenerator** | Generate FK→PK candidates using naming heuristics and type filtering | List of `CandidatePair` objects |
| **TypeCompatibilityEngine** | Validate type compatibility (INTEGER↔BIGINT, UUID↔STRING) | `TypeCompatibilityResult` with score |
| **BloomFilterEngine** | Probabilistic membership testing for early rejection | `BloomFilter` for PK sets |
| **ContainmentValidator** | **AUTHORITATIVE**: Validate FK ⊆ PK containment | `ContainmentResult` with orphan count |
| **ConfidenceEngine** | Fuse evidence into unified confidence score | Float confidence (0.0-1.0) |
| **FKSuppressionEngine** | Prevent temporal/audit/boolean FK detection | `SuppressionResult` with reasons |
| **RelationshipEngine** | Orchestrate full pipeline | `RelationshipReport` |

---

## Design Principles

### 1. Deterministic-First Validation

```
FK detection = CONTAINMENT VALIDATION

FK values ⊆ PK values (with threshold)
```

- **Containment ratio** is the authoritative metric
- ANN/semantic similarity is ONLY for candidate retrieval
- Bloom filters are ONLY for pruning (NOT validation)

### 2. Avoid O(n²) Explosion

**Anti-Pattern:**
```python
# DON'T: Compare every column vs every column
for fk_table in tables:
    for fk_col in fk_table.columns:
        for pk_table in tables:
            for pk_col in pk_table.columns:
                validate(fk_col, pk_col)  # O(n²) explosion
```

**Correct Approach:**
```python
# DO: Filter to PK candidates only
for fk_table in tables:
    for fk_col in fk_table.columns:
        for pk_table, pk_candidates in pk_index.items():
            for pk_col in pk_candidates:  # Only PKs
                if type_compatible(fk_col, pk_col):
                    if naming_matches(fk_col, pk_col):
                        validate(fk_col, pk_col)
```

### 3. Explainable Confidence

Every relationship has:
- **Containment Ratio**: |FK ∩ PK| / |FK|
- **Overlap Ratio**: |FK ∩ PK| / |PK|
- **Type Compatibility Score**: 0.0-1.0
- **PK Confidence**: Confidence of target PK candidate
- **Naming Similarity**: Column name matching score

Confidence Formula:
```python
confidence = (
    containment_ratio * 0.45 +      # DOMINANT
    overlap_ratio * 0.25 +
    type_compatibility * 0.15 +
    pk_confidence * 0.10 +
    naming_similarity * 0.05
)
```

### 4. Suppression-First Safety

Suppress invalid FK patterns:
- Temporal columns: `created_at`, `updated_at`, `valid_from`
- Boolean columns: `is_active`, `is_deleted`
- Constant columns: All values identical
- Low cardinality: < 10 distinct values
- Descriptive fields: `name`, `description`, `comments`
- Mutable attributes: `phone`, `email`, `address`
- Measures: `amount`, `price`, `population`
- Geospatial: `location`, `coordinates`

---

## Pipeline Stages

### Stage 1: Candidate Pair Generation

**Goal:** Generate FK→PK candidate pairs without O(n²) explosion.

**Strategy:**
1. Build PK index: Only consider PK candidates
2. Naming heuristics: `orders.customer_id` → `customers.customer_id`
3. Type filtering: Reject incompatible types early
4. Cardinality filtering: FK distinct < PK distinct

**Naming Patterns:**
```python
customer_id → customer → customers table
cityid → city → cities table
delivery_city_id → city → cities table
parent_item_id → item → items table (self-referential)
```

**Output:** List of `CandidatePair` objects

**Complexity:** O(tables * fk_columns * pk_candidates_per_table)  
Typical: ~10-100 candidates instead of 10,000+

---

### Stage 2: Type Compatibility Filtering

**Goal:** Reject impossible type pairings.

**Compatibility Matrix:**

| FK Type | PK Type | Score | Coercion |
|---------|---------|-------|----------|
| INTEGER | INTEGER | 1.0 | No |
| INTEGER | BIGINT | 0.95 | Yes |
| INTEGER | STRING | 0.3 | Yes (risky) |
| UUID | STRING | 0.9 | No (common) |
| BOOLEAN | INTEGER | 0.2 | Yes (rare) |
| FLOAT | DOUBLE | 0.95 | No |

**Rules:**
- Exact match: 1.0 score
- Safe coercion: 0.8-0.95 score
- Risky coercion: 0.3-0.5 score
- Incompatible: < 0.3 score

**Output:** `TypeCompatibilityResult` with compatibility_score

---

### Stage 3: Bloom Filter Pruning

**Goal:** Quickly reject impossible FK relationships.

**Algorithm:**
```python
# Build Bloom filter on PK values
bloom = BloomFilter(pk_values, false_positive_rate=0.01)

# Test FK sample
overlap_estimate = 0
for fk_value in fk_sample:
    if bloom.contains(fk_value):
        overlap_estimate += 1

# Reject if overlap < threshold
if overlap_estimate / len(fk_sample) < 0.10:
    REJECT  # Definitive rejection
```

**Properties:**
- False negatives: IMPOSSIBLE
- False positives: Possible (requires full validation)
- Memory: O(n) bits instead of O(n * value_size)

**Output:** Prune candidates with < 10% estimated overlap

---

### Stage 4: Containment Validation (AUTHORITATIVE)

**Goal:** Validate FK ⊆ PK using deterministic set operations.

**Algorithm:**
```python
pk_set = set(pk_values) - {None}
fk_non_null = [v for v in fk_values if v is not None]

contained_count = sum(1 for fk in fk_non_null if fk in pk_set)
containment_ratio = contained_count / len(fk_non_null)

orphan_count = len(fk_non_null) - contained_count
orphan_ratio = orphan_count / len(fk_non_null)
```

**Thresholds:**
- `containment_ratio >= 0.95`: Strong FK
- `containment_ratio >= 0.85`: Acceptable FK
- `containment_ratio < 0.85`: Weak/rejected FK

**Output:** `ContainmentResult` with containment_ratio, orphan_count

---

### Stage 5: Confidence Scoring

**Goal:** Fuse multiple evidence signals into unified confidence score.

**Weighted Fusion:**
```python
confidence = (
    containment_ratio * 0.45 +      # DOMINANT SIGNAL
    overlap_ratio * 0.25 +
    type_compatibility * 0.15 +
    pk_confidence * 0.10 +
    naming_similarity * 0.05
)

# Apply penalties
if containment_ratio < 0.70:
    confidence = min(confidence, 0.60)  # Hard cap

if null_ratio_fk > 0.5:
    confidence -= (null_ratio_fk - 0.5) * 0.20

if cardinality_ratio > 1.0:
    confidence -= min(0.30, (cardinality_ratio - 1.0) * 0.50)
```

**Acceptance Criteria:**
- `confidence >= 0.85`: Strong FK
- `confidence >= 0.75`: Acceptable FK (default threshold)
- `confidence >= 0.60`: Weak FK (flag for review)
- `confidence < 0.60`: Rejected FK

**Output:** Float confidence score (0.0-1.0)

---

### Stage 6: Suppression Rules

**Goal:** Prevent detection of invalid FK patterns.

**Suppression Logic:**
```python
# 1. Temporal/Audit
if re.search(r"created.*at|updated.*at|valid.*from", column.lower()):
    SUPPRESS

# 2. Boolean
if column.type == "BOOLEAN" or column.distinct_count == 2:
    SUPPRESS

# 3. Constant
if column.distinct_count == 1:
    SUPPRESS

# 4. Low Cardinality
if column.distinct_count < 10:
    SUPPRESS

# 5. Descriptive
if re.search(r".*name$|.*description$|.*comments?$", column.lower()):
    PENALTY = 0.30  # Don't hard suppress, just penalize

# ... and 5 more rules
```

**Output:** `SuppressionResult` with should_suppress, reasons, penalty

---

### Stage 7: Relationship Report Generation

**Goal:** Generate structured RelationshipReport.json.

**Report Structure:**
```json
{
  "relationship_report_id": "rel_abc123",
  "schema_version": "v1.0.0",
  "artifact_type": "RelationshipReport",
  "generation_timestamp": "2026-05-15T10:30:00Z",
  "summary": {
    "total_relationships_detected": 15,
    "total_relationships_accepted": 12,
    "total_relationships_rejected": 3,
    "total_tables_analyzed": 8,
    "total_candidate_pairs_evaluated": 45
  },
  "relationships": [...]
}
```

---

## Algorithms & Data Structures

### Bloom Filter Implementation

**Purpose:** Probabilistic membership test for PK sets.

**Algorithm:**
```python
class BloomFilter:
    def __init__(self, n: int, p: float):
        # Optimal bit count: m = -(n * ln(p)) / (ln(2)²)
        self.bit_count = int(-(n * log(p)) / (log(2) ** 2))
        
        # Optimal hash count: k = (m/n) * ln(2)
        self.hash_count = int((self.bit_count / n) * log(2))
        
        self.bit_array = [False] * self.bit_count
    
    def add(self, item):
        for seed in range(self.hash_count):
            index = hash(item, seed) % self.bit_count
            self.bit_array[index] = True
    
    def contains(self, item):
        for seed in range(self.hash_count):
            index = hash(item, seed) % self.bit_count
            if not self.bit_array[index]:
                return False  # DEFINITIVE NO
        return True  # MAYBE (requires validation)
```

**False Positive Rate:**
```
FP rate = (1 - e^(-kn/m))^k

For n=10,000, p=0.01:
  m ≈ 95,851 bits (12 KB)
  k ≈ 7 hash functions
  Actual FP ≈ 1%
```

---

### Containment Validation Algorithm

**Purpose:** Authoritative FK ⊆ PK validation.

**Full Scan (Exact):**
```python
def validate_containment_full(fk_values, pk_values):
    pk_set = set(pk_values) - {None}
    fk_non_null = [v for v in fk_values if v is not None]
    
    contained = 0
    orphans = []
    
    for fk_val in fk_non_null:
        if fk_val in pk_set:
            contained += 1
        else:
            orphans.append(fk_val)
    
    containment_ratio = contained / len(fk_non_null)
    orphan_count = len(orphans)
    
    return ContainmentResult(
        contained=(containment_ratio >= 0.85),
        containment_ratio=containment_ratio,
        orphan_count=orphan_count,
        ...
    )
```

**Complexity:**
- Time: O(|PK| + |FK|)
- Space: O(|PK distinct|) for set

**Sampled (Approximate):**
```python
def validate_containment_sampled(fk_sample, pk_values, total_fk_count):
    pk_set = set(pk_values) - {None}
    fk_non_null = [v for v in fk_sample if v is not None]
    
    contained = sum(1 for v in fk_non_null if v in pk_set)
    sample_containment = contained / len(fk_non_null)
    
    # Extrapolate to full dataset
    estimated_orphans = int((1 - sample_containment) * total_fk_count)
    
    return ContainmentResult(
        containment_ratio=sample_containment,
        orphan_count=estimated_orphans,
        is_approximate=True,
        ...
    )
```

---

### Candidate Pair Generation Algorithm

**Purpose:** Generate FK→PK candidates without O(n²).

**Naming Heuristic:**
```python
def extract_entity_name(column: str) -> str:
    # customer_id → customer
    # cityid → city
    # delivery_city_id → city
    
    col_lower = column.lower()
    
    suffixes = ["_id", "id", "_key", "key"]
    for suffix in suffixes:
        if col_lower.endswith(suffix):
            return col_lower[:-len(suffix)]
    
    return None

def normalize_table_name(table: str) -> str:
    # Sales_Customers → customer
    # application_cities → city
    
    name = table.lower()
    
    # Remove prefixes
    for prefix in ["application_", "sales_", "purchasing_"]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    
    # Handle plurals
    if name.endswith("ies"):
        name = name[:-3] + "y"  # cities → city
    elif name.endswith("s"):
        name = name[:-1]  # customers → customer
    
    return name
```

**Matching Logic:**
```python
# Extract entity from FK: customer_id → customer
fk_entity = extract_entity_name(fk_column)

# Normalize PK table: Sales_Customers → customer
pk_entity = normalize_table_name(pk_table)

# Check match
if fk_entity == pk_entity:
    naming_similarity = 0.95  # Strong match
```

---

## Scalability & Performance

### Complexity Analysis

| Stage | Time Complexity | Space Complexity |
|-------|----------------|------------------|
| Candidate Generation | O(T * C * P) | O(C * P) |
| Type Filtering | O(N) | O(1) |
| Bloom Filter Build | O(P) | O(P) |
| Bloom Filter Query | O(F * k) | O(1) |
| Containment Validation | O(F + P) | O(P_distinct) |
| Confidence Scoring | O(1) | O(1) |

**Legend:**
- T = number of tables
- C = average columns per table
- P = average PK candidates per table
- F = FK sample size
- k = Bloom filter hash count (~7)

**Without Optimization:**
- Every column vs every column: O(T² * C²)
- For 100 tables, 20 cols: 4,000,000 comparisons

**With Optimization:**
- PK filtering + naming: O(T * C * P)
- For 100 tables, 20 cols, 2 PKs: 4,000 comparisons
- **1000x reduction**

### Memory Requirements

| Component | Memory per Table |
|-----------|------------------|
| Table Profile | ~1 KB (metadata) |
| PK Candidate | ~100 bytes |
| Bloom Filter (10K PKs) | ~12 KB |
| Sample Values (1K rows) | ~10-100 KB |
| **Total per Table** | **~50 KB** |

**For 1,000 tables:** ~50 MB memory

### Execution Time Estimates

| Dataset Size | Tables | Relationships | Time (Full Scan) | Time (Sampled) |
|--------------|--------|---------------|------------------|----------------|
| Small | 10 | 5 | < 1 sec | < 0.5 sec |
| Medium | 100 | 50 | ~10 sec | ~3 sec |
| Large | 1,000 | 500 | ~5 min | ~30 sec |
| Enterprise | 10,000 | 5,000 | ~2 hours | ~10 min |

**Assumptions:**
- Python engine (single-threaded)
- Full scan: All FK values validated
- Sampled: 10% FK sample validated

**With DuckDB Pushdown:**
- Large datasets: ~30 sec (parallel SQL)
- Enterprise: ~5 min (distributed)

---

## Output Schema

### RelationshipReport.json

```json
{
  "relationship_report_id": "rel_abc123def456",
  "schema_version": "v1.0.0",
  "artifact_type": "RelationshipReport",
  "generation_timestamp": "2026-05-15T10:30:00.000Z",
  
  "summary": {
    "total_relationships_detected": 15,
    "total_relationships_accepted": 12,
    "total_relationships_rejected": 3,
    "total_tables_analyzed": 8,
    "total_candidate_pairs_evaluated": 45,
    "graph_node_count": 8,
    "graph_edge_count": 12
  },
  
  "execution_metadata": {
    "execution_engine": "python",
    "execution_time_seconds": 3.456
  },
  
  "relationships": [
    {
      "relationship_id": "fk_001",
      "relationship_type": "foreign_key",
      
      "from": {
        "table": "orders",
        "column": "customer_id",
        "physical_type": "INTEGER",
        "logical_type": "IDENTIFIER"
      },
      
      "to": {
        "table": "customers",
        "column": "customer_id",
        "physical_type": "INTEGER",
        "logical_type": "IDENTIFIER"
      },
      
      "confidence": 0.9800,
      "accepted": true,
      
      "evidence": {
        "containment_ratio": 1.0000,
        "overlap_ratio": 0.9900,
        "type_match": true,
        "type_compatibility_score": 1.0,
        "pk_confidence": 0.9700,
        "naming_similarity": 0.9500,
        "cardinality_ratio": 0.8500,
        "null_ratio_fk": 0.0000,
        "is_approximate": false,
        "bloom_filter_passed": true,
        "orphan_count": 0
      },
      
      "validation": {
        "containment_validated": true,
        "orphan_count": 0,
        "orphan_ratio": 0.0000,
        "referential_integrity_score": 1.0000,
        "validation_method": "full_scan",
        "has_orphans": false,
        "is_weak_reference": false,
        "is_ambiguous": false,
        "warnings": []
      },
      
      "execution_metadata": {
        "engine": "python",
        "sampling_strategy": "full_scan",
        "is_approximate": false,
        "deterministic_seed": 42,
        "profiler_version": "1.0.0",
        "relationship_rule_version": "1.0.0",
        "detection_timestamp": "2026-05-15T10:30:00.000Z"
      },
      
      "composite_key": false
    }
  ]
}
```

---

## Production Deployment

### Integration with SDIE Pipeline

```python
# After profiling layer
from relationships import detect_relationships
from relationships.relationship_serializer import save_relationship_report

# Load inputs
table_profiles = load_table_profiles("output/profiles/")
pk_candidates = load_pk_candidates("output/profiles/")
canonical_tables = load_canonical_tables("output/canonical/")

# Run FK detection
report = detect_relationships(
    table_profiles=table_profiles,
    pk_candidates=pk_candidates,
    canonical_tables=canonical_tables,
    acceptance_threshold=0.75,
)

# Save output
save_relationship_report(report, "output/relationship_report.json")
```

### Configuration Options

```python
engine = RelationshipEngine(
    acceptance_threshold=0.75,       # Confidence threshold
    use_bloom_filters=True,          # Enable Bloom pruning
    validation_method="full",        # "full", "sampled", "hybrid"
    deterministic_seed=42,           # For reproducibility
)
```

### Performance Tuning

**For Small Datasets (<1M rows):**
- Use `validation_method="full"` for exact results
- Disable Bloom filters (overhead not worth it)

**For Large Datasets (1M-100M rows):**
- Use `validation_method="sampled"` with 10K sample
- Enable Bloom filters for pruning
- Consider DuckDB engine for parallel validation

**For Enterprise Scale (>100M rows):**
- Use `validation_method="hybrid"`
- Bloom filter pruning required
- DuckDB engine with distributed execution
- Metadata-only mode for initial discovery

---

## Future Enhancements

### Phase 2: Composite Keys

Detect multi-column PKs and FKs:
```python
# (order_id, line_number) → composite PK
# orders_lines.order_id → orders.order_id (partial FK)
```

**Algorithm:**
- Detect column groups with combined uniqueness
- Validate containment on tuple sets
- Support partial FK relationships

### Phase 3: DuckDB Integration

Push containment validation to SQL:
```sql
-- Validate FK containment
SELECT COUNT(*) AS orphan_count
FROM fk_table
WHERE fk_col NOT IN (SELECT pk_col FROM pk_table);
```

**Benefits:**
- Parallel execution
- Spill to disk for large sets
- SQL query optimization

### Phase 4: ANN Candidate Retrieval

Use semantic embeddings to find FK candidates:
```python
# Embed column names and sample values
fk_embedding = embed("orders.customer_identifier")

# Retrieve similar PK columns
candidates = ann_index.search(fk_embedding, k=10)

# THEN validate deterministically
for candidate in candidates:
    validate_containment(fk, candidate)
```

**Critical:** ANN is ONLY for candidate retrieval, NOT validation.

### Phase 5: Graph Analytics

Export to graph databases:
- Neo4j: Cypher queries
- NetworkX: Graph algorithms
- DuckDB: SQL graph traversal

Detect:
- Cyclic dependencies
- Orphaned tables
- Relationship clusters
- Schema normalization opportunities

---

## Conclusion

The **FK Relationship Detection Layer** provides enterprise-grade relationship intelligence with:

✅ **Deterministic validation** - Containment is truth  
✅ **Scalable architecture** - Avoids O(n²), handles TB-scale  
✅ **Explainable evidence** - Confidence scores with reasoning  
✅ **Production-ready** - Modular, tested, documented  
✅ **Graph-ready output** - Multiple export formats  
✅ **Future-proof** - Extensible for composite keys, ANN, DuckDB  

**The system is ready for production deployment.**

---

**End of FK Relationship Detection Layer Documentation**
