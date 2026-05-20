# Canonical JSON — Reusable Intermediate Artifact

## Overview

**Canonical JSON** is the lightweight, cached intermediate representation between raw data parsing (Layer 5) and downstream analysis layers.

### 🚀 Key Design Decision

**Format engines ONLY parse, NEVER profile.**

This separation creates a clean architecture:
- **Layer 5** (Format Engines): Raw data → CanonicalTable IR
- **Canonical JSON**: Persisted artifact (cache layer)
- **Layer 6+**: All downstream analysis consumes Canonical JSON

---

## Why Persist Canonical JSON?

### Without Persistence ❌

Every downstream layer must:
- ✗ Reread files
- ✗ Reparse data
- ✗ Rerun normalization
- ✗ Resample rows

**Very expensive.** Non-scalable.

### With Canonical JSON ✅

Downstream layers reuse:
- ✓ Schema
- ✓ Normalized columns
- ✓ Sampled values
- ✓ Statistics
- ✓ Semantic hints

**Huge scalability improvement.**

---

## Architecture Flow

```
┌─────────────────┐
│   Raw Data      │  CSV, JSON, Parquet, Excel, PostgreSQL, etc.
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Format Engine   │  Parse format-specific structure
│  (Layer 5)      │  Design: ONLY parse, NEVER profile
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ CanonicalTable  │  In-memory IR (Python objects)
│   (Memory)      │  Schema + rows + metadata
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Canonical JSON  │  ⭐ Persistent Artifact (THIS LAYER)
│   (Disk Cache)  │  Lightweight, NOT full dataset
└────────┬────────┘
         │
         ├──────→ Layer 6: Statistical Profiler
         ├──────→ Layer 7: PK/FK Detection
         ├──────→ Layer 8: Semantic Layer
         ├──────→ Layer 9: LLM Reasoning
         └──────→ Layer 10: Knowledge Graph
```

---

## Canonical JSON Schema

### Complete Structure

```json
{
  "table_id": "tbl_001",
  "table_name": "customers",
  
  "source": {
    "source_type": "file",
    "format": "csv",
    "path": "/data/customers.csv"
  },
  
  "metadata": {
    "row_count_estimate": 1050000,
    "column_count": 5,
    "size_mb": 125.4,
    "sampling_strategy": "reservoir_hll",
    "engine": "csv_engine",
    "encoding": "utf-8",
    "delimiter": ",",
    "compression": null
  },
  
  "columns": [
    {
      "column_id": "col_000",
      "original_name": "Customer ID",
      "normalized_name": "customer_id",
      "position": 0,
      "physical_type": "STRING",
      "semantic_type": null,
      "nullable": false,
      
      "sample_values": [
        "1001",
        "1002",
        "1003"
      ],
      
      "statistics": {
        "null_count": 0,
        "distinct_estimate": 1050000,
        "avg_length": 8
      }
    }
  ]
}
```

---

## Schema Breakdown

### 1. Table Metadata

```json
{
  "table_id": "tbl_001",
  "table_name": "customers"
}
```

**Purpose:**
- Stable references across system
- Graph identity for lineage
- Unique identifier

### 2. Source Metadata

```json
{
  "source_type": "file",
  "format": "csv",
  "path": "/data/customers.csv"
}
```

**Purpose:**
- Lineage tracking
- Debugging
- Governance
- Reproducibility

### 3. Dataset Metadata

```json
{
  "row_count_estimate": 1050000,
  "column_count": 5,
  "size_mb": 125.4,
  "sampling_strategy": "reservoir_hll",
  "engine": "csv_engine"
}
```

**Purpose:**
- Query planning
- Cost estimation
- Optimizer decisions
- Quality assessment

**⚠️ IMPORTANT:** Track `sampling_strategy` and `engine` — otherwise confidence becomes ambiguous.

### 4. Column Metadata

```json
{
  "column_id": "col_000",
  "original_name": "Customer ID",
  "normalized_name": "customer_id",
  "position": 0,
  "physical_type": "STRING",
  "semantic_type": null,
  "nullable": false
}
```

#### Why Both Names?

| Field | Purpose |
|-------|---------|
| `original_name` | Lineage, debugging, user display |
| `normalized_name` | Execution consistency, SQL generation |

#### Physical Type vs Semantic Type

**Critical distinction:**

| Value | `physical_type` | `semantic_type` |
|-------|----------------|----------------|
| "1001" | STRING | identifier |
| "2024-05-14" | STRING | date |
| "john@example.com" | STRING | email |

- `physical_type`: Observed storage type (Layer 5)
- `semantic_type`: Inferred meaning (Layer 6+)

### 5. Sample Values 🚀

```json
{
  "sample_values": [
    "India",
    "USA",
    "Germany"
  ]
}
```

**Why Store Samples?**

Used by:
- Type inference (Layer 6)
- Semantic layer (Layer 8)
- LLM reasoning (Layer 9)
- Debugging
- Quality analysis
- Relationship hints

**⚠️ IMPORTANT:** Never store all rows. Store representative samples only.

#### Recommended Sample Sizes

| Dataset Size | Sample Count |
|-------------|--------------|
| Tiny (<1K) | Full |
| Small (1K-100K) | 100-1000 |
| Medium (100K-10M) | 1000-5000 |
| Huge (>10M) | Sketch summaries |

### 6. Lightweight Statistics

```json
{
  "statistics": {
    "null_count": 0,
    "distinct_estimate": 1050000,
    "avg_length": 8
  }
}
```

#### What to Store

| Statistic | Store? | Why |
|-----------|--------|-----|
| `null_count` | ✅ | Nullability inference |
| `distinct_estimate` | ✅ | Cardinality hints |
| `avg_length` | ✅ | String type hints |
| `min/max` | ⚠️ Optional | Type inference |
| Quantiles | ❌ | Too heavy |
| Histograms | ❌ | Separate artifact |

**⚠️ Design Rule:** Canonical JSON should remain lightweight. Heavy profiling artifacts belong elsewhere.

---

## What to Store vs NOT Store

### ✅ DO Store

| Category | Store? | Rationale |
|----------|--------|-----------|
| Schema | ✅ | Required for all downstream layers |
| Normalized column names | ✅ | Execution consistency |
| Inferred types | ✅ | Query planning hints |
| Sample rows | ✅ | Semantic analysis |
| Metadata | ✅ | Lineage, governance |
| Lightweight stats | ✅ | Type inference hints |

### ❌ DON'T Store

| Category | Store? | Rationale |
|----------|--------|-----------|
| Full dataset | ❌ | Too heavy, not intermediate |
| All rows | ❌ | Samples sufficient |
| Heavy profiling stats | ❌ | Belongs in FileProfile.json |
| Embeddings | ❌ | Separate layer |
| ANN index | ❌ | Separate layer |

---

## Benefits

### 🎯 Performance

| Without Canonical JSON | With Canonical JSON |
|----------------------|-------------------|
| Parse CSV every time | Parse once, cache |
| 10 seconds × 100 runs = 16 minutes | 10 seconds + 100 × 0.1s = 20 seconds |
| Compute schema repeatedly | Load from JSON |

**80-95% time savings** on repeated operations.

### 🎯 Scalability

- **Lightweight:** ~3KB per table (vs MB/GB raw data)
- **Fast:** JSON load is 100x faster than CSV parse
- **Cacheable:** Disk, Redis, S3 — anywhere

### 🎯 Debugging

```json
{
  "original_name": "Customer ID",
  "normalized_name": "customer_id",
  "sample_values": ["1001", "1002", "1003"]
}
```

You can see:
- What the original column name was
- What it was normalized to
- What the actual data looks like

### 🎯 Lineage

```json
{
  "source": {
    "path": "/data/customers.csv",
    "format": "csv"
  },
  "metadata": {
    "engine": "csv_engine",
    "sampling_strategy": "reservoir_hll"
  }
}
```

You can trace:
- Where data came from
- How it was parsed
- What sampling was applied

---

## Usage

### Basic Flow

```python
from profiler.engines import registry
from pathlib import Path

# Step 1: Parse raw data
table = registry.parse(
    file_path=Path("data/customers.csv"),
    file_format="csv",
    encoding="utf-8",
    sample_size=1000
)

# Step 2: Compute lightweight statistics
table.compute_lightweight_statistics()

# Step 3: Save Canonical JSON
output_path = Path("output/canonical/customers.canonical.json")
table.save_canonical_json(output_path)

# Step 4: Downstream layers load from cache
import json
with open(output_path) as f:
    canonical = json.load(f)

# Now use canonical for profiling, PK/FK detection, etc.
```

### Column Normalization

```python
from profiler.engines.format_engines import CanonicalTable

# Normalize column names
CanonicalTable.normalize_column_name("Customer ID")       # "customer_id"
CanonicalTable.normalize_column_name("Email-Address")     # "email_address"
CanonicalTable.normalize_column_name("Total Price ($)")   # "total_price"
```

---

## File Structure

```
output/
└── canonical/                      # ⭐ Canonical JSON cache
    ├── customers.canonical.json
    ├── orders.canonical.json
    ├── products.canonical.json
    └── ...

# NOT YET IMPLEMENTED (Future):
├── profiles/                       # Layer 6: FileProfile.json
├── relationships/                  # Layer 7: RelationshipReport.json
├── semantic/                       # Layer 8: SemanticCatalog.json
└── quality/                        # Layer 9: QualityReport.json
```

---

## Artifact Separation

| Artifact | Purpose | Layer |
|----------|---------|-------|
| **CanonicalTable.json** | Normalized IR | Layer 5 ✅ |
| FileProfile.json | Profiling output | Layer 6 (Future) |
| RelationshipReport.json | FK graph | Layer 7 (Future) |
| SemanticCatalog.json | Embeddings/ontology | Layer 8 (Future) |
| QualityReport.json | Anomalies | Layer 9 (Future) |

**Design:** Each layer produces separate artifacts. Canonical JSON is the foundation.

---

## Testing

Run tests:

```bash
python tests/test_canonical_json.py
```

Expected output:
```
✓ JSON Generation
✓ JSON Persistence
✓ Column Normalization
✓ Lightweight Statistics
✓ Batch Persistence
✓ JSON Structure

Total: 6/6 tests passed
```

---

## Real Example

From `application_deliverymethods.canonical.json`:

```json
{
  "table_id": "tbl_f0befa",
  "table_name": "application_deliverymethods",
  "source": {
    "source_type": "file",
    "format": "csv",
    "path": "data\\application_deliverymethods.csv"
  },
  "metadata": {
    "row_count_estimate": 10,
    "column_count": 5,
    "size_mb": 0.0,
    "engine": "csv_engine"
  },
  "columns": [
    {
      "column_id": "col_000",
      "original_name": "DeliveryMethodID",
      "normalized_name": "deliverymethodid",
      "position": 0,
      "physical_type": "UNKNOWN",
      "nullable": false,
      "sample_values": ["1", "2", "3", "4", "5"],
      "statistics": {
        "null_count": 0,
        "distinct_estimate": 10,
        "avg_length": 1.1
      }
    }
  ]
}
```

**File size:** 2.9 KB (lightweight!)

---

## Next Steps

With Canonical JSON implemented, you can now build:

### Layer 6: Statistical Profiler
- Input: Canonical JSON
- Output: FileProfile.json
- Stats: Distribution, quantiles, histograms, type inference

### Layer 7: PK/FK Detection
- Input: Multiple Canonical JSONs
- Output: RelationshipReport.json
- Analysis: Find foreign keys across tables

### Layer 8: Semantic Layer
- Input: Canonical JSON + sample values
- Output: SemanticCatalog.json
- Analysis: Embeddings, ontology, entity resolution

### Layer 9: LLM Reasoning
- Input: Canonical JSON metadata
- Output: Natural language insights
- Analysis: Data understanding, recommendations

---

## Key Takeaways

1. **Lightweight** — Schema + samples, NOT full dataset
2. **Cached** — Parse once, reuse many times
3. **Lineage** — Track original → normalized names
4. **Foundation** — Input for all downstream layers
5. **Scalable** — 3KB JSON vs GB raw data

Canonical JSON is the **reusable intermediate artifact** that makes the entire system efficient and scalable. 🚀
