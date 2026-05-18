# LLM-Powered Semantic Relationship Detection

## Overview

This system uses **NVIDIA's seed-oss-36b-instruct** model to generate rich semantic column descriptions, then combines **semantic similarity (ANN retrieval) with deterministic validation (containment)** to detect foreign key relationships across your database schema.

### Key Innovation

**Deterministic validation is authoritative, semantic similarity is for candidate discovery.**

- ✓ LLM generates rich business-focused column descriptions
- ✓ TF-IDF embeddings + cosine similarity for candidate retrieval
- ✓ DBSCAN clustering groups semantically related columns
- ✓ Containment validation (FK ⊆ PK) is the authoritative truth
- ✓ Relationship adjudication distinguishes TRUE_FK from SEMANTICALLY_RELATED

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    PROFILE.JSON (INPUT)                         │
│  Column statistics, sample values, type information             │
└────────────────┬───────────────────────────────────────────────┘
                 │
                 v
┌────────────────────────────────────────────────────────────────┐
│              STAGE 1: LLM Description Generation                │
│  NVIDIA seed-oss-36b-instruct generates:                        │
│    - semantic_role (identifier, measure, dimension, etc.)       │
│    - business_meaning (rich business context)                   │
│    - identifier_type (primary_surrogate, foreign_reference)     │
│    - entity_reference (customer, product, order)                │
│    - relationship_hints (FK detection hints)                    │
│    - data_quality_notes (quality observations)                  │
└────────────────┬───────────────────────────────────────────────┘
                 │
                 v
┌────────────────────────────────────────────────────────────────┐
│                   DESCRIPTIONS.JSON (CACHED)                    │
│  Rich semantic descriptions for all columns                     │
└────────────────┬───────────────────────────────────────────────┘
                 │
                 v
┌────────────────────────────────────────────────────────────────┐
│            STAGE 2: Embedding & ANN Retrieval                   │
│  - TF-IDF vectorization (500 features, bigrams)                 │
│  - Cosine similarity matrix                                     │
│  - ANN candidate retrieval (min_similarity=0.30)                │
│  - High recall, low precision (catch all possibilities)         │
└────────────────┬───────────────────────────────────────────────┘
                 │
                 v
┌────────────────────────────────────────────────────────────────┐
│              STAGE 3: Semantic Clustering (DBSCAN)              │
│  Group related columns:                                         │
│    - customer-related identifiers                               │
│    - product-related fields                                     │
│    - temporal audit fields                                      │
│  Clusters are hints, NOT authoritative relationships            │
└────────────────┬───────────────────────────────────────────────┘
                 │
                 v
┌────────────────────────────────────────────────────────────────┐
│         STAGE 4: Deterministic Containment Validation           │
│  For each semantic candidate:                                   │
│    containment_ratio = |FK ∩ PK| / |FK|                         │
│  >= 0.95: Perfect FK                                            │
│  >= 0.85: Strong FK                                             │
│  <  0.85: Weak/Rejected                                         │
│  AUTHORITATIVE TRUTH - overrides semantic similarity            │
└────────────────┬───────────────────────────────────────────────┘
                 │
                 v
┌────────────────────────────────────────────────────────────────┐
│            STAGE 5: Confidence Scoring (Weighted)               │
│  Weighted fusion of evidence:                                   │
│    - containment_ratio: 0.45 (DOMINANT)                         │
│    - semantic_similarity: 0.20                                  │
│    - type_compatibility: 0.15                                   │
│    - pk_confidence: 0.10                                        │
│    - naming_similarity: 0.10                                    │
└────────────────┬───────────────────────────────────────────────┘
                 │
                 v
┌────────────────────────────────────────────────────────────────┐
│              STAGE 6: Relationship Adjudication                 │
│  Classify each relationship:                                    │
│    - TRUE_FK: High containment + good semantics                 │
│    - SEMANTICALLY_RELATED: High semantics, low containment      │
│    - SHARED_ENTITY_DOMAIN: Same business domain                 │
│    - POSSIBLE_REFERENCE: Moderate evidence                      │
│    - FALSE_POSITIVE: Insufficient evidence                      │
└────────────────┬───────────────────────────────────────────────┘
                 │
                 v
┌────────────────────────────────────────────────────────────────┐
│                 RELATIONSHIPS.JSON (OUTPUT)                     │
│  Complete relationship graph with:                              │
│    - Classification (TRUE_FK, SEMANTICALLY_RELATED, etc.)       │
│    - Confidence scores                                          │
│    - Semantic similarity                                        │
│    - Containment ratio                                          │
│    - Explainable reasoning                                      │
└────────────────────────────────────────────────────────────────┘
```

---

## Setup

### 1. Install Dependencies

```bash
pip install openai python-dotenv scikit-learn numpy
```

### 2. Set NVIDIA API Key

The system uses NVIDIA's API for LLM description generation. Set your API key:

**Option A: Environment Variable**
```bash
export NVIDIA_API_KEY="nvapi-YOUR_KEY_HERE"
```

**Option B: .env File**
```bash
echo "NVIDIA_API_KEY=nvapi-YOUR_KEY_HERE" > .env
```

Get your API key from: https://integrate.api.nvidia.com

### 3. Prepare Input Data

The pipeline requires two inputs:

1. **profile.json** (required): Column statistics from profiling engine
   - Location: `output/profiles/*.json`
   - Contains: column types, distinct counts, null counts, sample values

2. **canonical.json** (optional): Canonical table representations
   - Location: `output/canonical/*.json`
   - Contains: sample values for containment validation
   - If not provided, validation will be limited

---

## Usage

### Run Complete Pipeline

```bash
python demo_llm_semantic_pipeline.py
```

This will:
1. Load profiles from `output/profiles/`
2. Generate LLM descriptions → `output/descriptions.json`
3. Perform ANN retrieval + clustering
4. Validate with containment
5. Generate relationships → `output/relationships.json`

### Programmatic Usage

```python
from demo_llm_semantic_pipeline import LLMSemanticPipeline

pipeline = LLMSemanticPipeline(
    nvidia_api_key="nvapi-YOUR_KEY_HERE",
    min_semantic_similarity=0.30,
    use_clustering=True,
)

summary = pipeline.run_full_pipeline(
    profile_json_path="output/profiles",
    canonical_json_path="output/canonical",
    output_dir="output",
)

print(f"Found {summary['true_fk_count']} TRUE_FK relationships")
```

### Generate Descriptions Only

If you just want to generate LLM descriptions without relationship detection:

```python
from relationships.llm_description_generator import generate_llm_descriptions

descriptions = generate_llm_descriptions(
    profile_json_path="output/profiles",
    output_json_path="output/descriptions.json",
)
```

---

## Output Files

### descriptions.json

LLM-generated semantic descriptions for all columns:

```json
{
  "schema_version": "v1.0.0",
  "artifact_type": "LLMColumnDescriptions",
  "tables": {
    "Sales_Customers": [
      {
        "table_name": "Sales_Customers",
        "column_name": "customer_id",
        "semantic_role": "identifier",
        "business_meaning": "Unique surrogate key identifying each customer in the system. Serves as the primary identifier for customer entity relationships across the database.",
        "identifier_type": "primary_surrogate",
        "entity_reference": "customer",
        "relationship_hints": [
          "primary_key_for_customer",
          "referenced_by_orders",
          "referenced_by_transactions"
        ],
        "data_quality_notes": [
          "perfect_uniqueness",
          "no_nulls"
        ]
      }
    ]
  }
}
```

### relationships.json

Adjudicated relationships with classifications:

```json
{
  "schema_version": "v1.0.0_semantic",
  "artifact_type": "SemanticRelationships",
  "relationships": [
    {
      "fk_table": "Sales_Orders",
      "fk_column": "customer_id",
      "pk_table": "Sales_Customers",
      "pk_column": "customer_id",
      "relationship_class": "TRUE_FK",
      "confidence": 0.95,
      "semantic_similarity": 0.87,
      "containment_ratio": 1.0,
      "type_compatibility": 1.0,
      "adjudication_reasoning": [
        "Perfect containment (1.00)",
        "Strong semantic alignment (0.87)",
        "Validated as TRUE foreign key relationship"
      ],
      "semantic_cluster_id": 2,
      "suppression_warnings": null
    }
  ]
}
```

---

## Relationship Classifications

### TRUE_FK
- **Criteria**: High containment (≥0.85) + adequate semantics (≥0.60)
- **Interpretation**: Validated foreign key relationship
- **Action**: Include in schema documentation and ER diagrams

### SEMANTICALLY_RELATED
- **Criteria**: Low containment (<0.50) + high semantics (≥0.75)
- **Interpretation**: Similar meaning but not a direct FK
- **Examples**: customer_id ↔ client_id (synonyms), order_date ↔ ship_date (related temporal fields)
- **Action**: Consider for business glossary, but NOT a structural FK

### SHARED_ENTITY_DOMAIN
- **Criteria**: Same entity reference + insufficient containment
- **Interpretation**: Both reference the same business entity
- **Examples**: customer_id in different dimension tables
- **Action**: Document as related fields in the same domain

### POSSIBLE_REFERENCE
- **Criteria**: Moderate containment (0.50-0.85) + moderate semantics
- **Interpretation**: Requires manual review
- **Action**: Investigate with domain experts

### FALSE_POSITIVE
- **Criteria**: Low everything
- **Interpretation**: No relationship
- **Action**: Ignore

---

## Configuration

### Semantic Similarity Threshold

Control candidate recall/precision:

```python
pipeline = LLMSemanticPipeline(
    min_semantic_similarity=0.30,  # High recall (more candidates)
    # min_semantic_similarity=0.60,  # High precision (fewer candidates)
)
```

**Recommendation**: Use 0.30 for discovery phase, then tighten to 0.50 for production.

### Clustering

DBSCAN semantic clustering groups related columns:

```python
pipeline = LLMSemanticPipeline(
    use_clustering=True,  # Enable clustering
)
```

Clusters help identify:
- Semantically related identifier families
- Business domain groupings
- Cross-schema entity references

### LLM Model Configuration

Customize the LLM generation:

```python
from relationships.llm_description_generator import NVIDIADescriptionGenerator

generator = NVIDIADescriptionGenerator(
    model="bytedance/seed-oss-36b-instruct",
    temperature=0.7,  # Lower = more focused, Higher = more creative
    max_tokens=1024,  # Max description length
)
```

---

## Performance

### WideWorldImporters Dataset (27 tables, 240 columns)

| Stage | Time | Output |
|-------|------|--------|
| LLM Description Generation | ~120s | 240 descriptions |
| Embedding Generation | ~2s | 240 × 500 matrix |
| ANN Candidate Retrieval | ~0.5s | 150 candidates |
| DBSCAN Clustering | ~0.3s | 12 clusters |
| Containment Validation | ~3s | 150 validated |
| Adjudication | ~0.2s | 45 TRUE_FK |
| **Total** | **~126s** | **45 relationships** |

### Caching

LLM descriptions are cached in `descriptions.json`. On subsequent runs:
- **First run**: ~126s (LLM generation)
- **Cached runs**: ~6s (skip LLM, load descriptions)

---

## Design Principles

### 1. Deterministic Validation is Authoritative

**Semantic similarity finds candidates, containment validates them.**

```
if containment_ratio >= 0.95:
    # TRUE_FK regardless of semantic similarity
    relationship_class = TRUE_FK
elif semantic_similarity >= 0.80 and containment_ratio < 0.50:
    # Semantically similar but NOT a FK
    relationship_class = SEMANTICALLY_RELATED
```

### 2. High Recall, Precision via Validation

**Cast a wide semantic net, then filter with deterministic evidence.**

- ANN threshold: 0.30 (captures synonyms, variants, cross-schema references)
- Validation: Containment ratio >= 0.85 for acceptance

### 3. Explainable Adjudication

**Every relationship includes reasoning.**

```json
"adjudication_reasoning": [
  "Strong containment (0.92)",
  "Adequate semantic similarity (0.67)",
  "Type compatible (1.00)",
  "Validated as TRUE foreign key relationship"
]
```

### 4. Suppression Rules Prevent Invalid Patterns

**Temporal, audit, and measure fields are suppressed.**

- `created_at`, `updated_at`: Temporal (not FKs)
- `created_by`, `modified_by`: Audit (user references, not entity FKs)
- `amount`, `price`, `quantity`: Measures (not identifiers)

---

## Troubleshooting

### "NVIDIA_API_KEY not found"

```bash
export NVIDIA_API_KEY="nvapi-YOUR_KEY_HERE"
# or
echo "NVIDIA_API_KEY=nvapi-YOUR_KEY_HERE" > .env
```

### "Profile path not found"

Run the profiling engine first:

```bash
python profiling_agent.py
```

This generates `output/profiles/*.json`.

### LLM Generation Fails

If the LLM API is unavailable, the system falls back to rule-based descriptions:

```
[WARNING] LLM generation failed for Sales_Customers.customer_id: Connection timeout
Using fallback description...
```

Fallback descriptions are less rich but functional.

### Low Relationship Recall

If you're missing relationships:

1. **Lower semantic threshold**: `min_semantic_similarity=0.20`
2. **Check sample values**: Containment validation requires sample values in canonical.json
3. **Review suppression rules**: Temporal/audit fields are intentionally suppressed

---

## API Reference

### LLMSemanticPipeline

```python
class LLMSemanticPipeline:
    def __init__(
        nvidia_api_key: Optional[str] = None,
        min_semantic_similarity: float = 0.30,
        use_clustering: bool = True,
    )
    
    def run_full_pipeline(
        profile_json_path: str,
        canonical_json_path: Optional[str] = None,
        output_dir: str = "output",
    ) -> Dict[str, Any]
```

### NVIDIADescriptionGenerator

```python
class NVIDIADescriptionGenerator:
    def generate_description(
        table_name: str,
        column_name: str,
        column_profile: Dict[str, Any],
        is_pk_candidate: bool = False,
    ) -> LLMColumnDescription
    
    def generate_descriptions_for_tables(
        table_profiles: Dict[str, Dict[str, Any]],
        pk_candidates: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, List[LLMColumnDescription]]
```

---

## Roadmap

### Planned Enhancements

- [ ] **Multi-model support**: GPT-4, Claude, Gemini as LLM backends
- [ ] **Graph visualization**: D3.js interactive relationship explorer
- [ ] **Incremental updates**: Only regenerate descriptions for changed columns
- [ ] **Confidence calibration**: Learn from user feedback
- [ ] **Cross-database relationships**: Detect FKs across different databases
- [ ] **Composite key detection**: Multi-column FKs

---

## License

Part of the Semantic Data Intelligence Engine (SDIE) profiling system.

---

## Support

For issues or questions:
- Review documentation in `docs/`
- Check existing test files: `test_semantic_relationships.py`
- Run demo: `demo_llm_semantic_pipeline.py`
