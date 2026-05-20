# NeuLeap Fix Plan.md

## Goal

Refactor the pipeline one phase at a time so each change can be executed, checked, and validated before moving to the next phase.

**Main rule:** change logic first, verify output second, then move forward only if the phase passes.

---

## Current Code Logic Overview

The existing pipeline currently has these major areas:

1. **Canonical / Intake layer**
   - Reads source files
   - Normalizes column names
   - Captures schema metadata

2. **Statistics / Profiling layer**
   - Computes counts, nulls, distincts, entropy, lengths, numeric stats
   - Uses DuckDB for heavy statistics in the newer version

3. **PK detection layer**
   - Scores columns as primary key candidates
   - Applies suppression rules

4. **Relationship layer**
   - Detects candidate relationships
   - Builds `relationship.json`
   - Should stay separate from profiling

5. **Enrichment layer**
   - Adds semantic meaning, low‑cardinality insights, descriptions
   - Must not alter structural truth

6. **Visualization / DBML / ER layer**
   - Builds `schema.dbml`, ERD, charts, viewer state

---

## Non‑Negotiable Rule

**Profiling must not contain FK or relationship logic**

Profiling is allowed to do only:

- statistics
- type inference
- quality scoring
- PK scoring
- suppression
- profile output

Profiling must **not** do:

- FK detection
- relationship inference
- join discovery
- graph building
- DBML refs
- reference overlap checks
- containment‑based parent lookup

FK and relationship logic must live in a **later layer**.

---

# Execution Order

## Phase 1 — Remove relationship leakage from profiling

**Objective**: Make the profiler pure.

**What to change**
- Remove FK imports from profiling code
- Remove any FK scoring from `_profile_column()`
- Remove relational role classification from profiling
- Remove FK fields from the profiler model if possible, or mark them deprecated and unused
- Remove any join, overlap, containment, `referenced_entity`, or relationship evidence logic from profiling

**Must keep**
- statistics
- PK scoring
- suppression
- quality
- semantic hints such as identifier / temporal / audit / measure / dimension

**Validate**
Run profiling on:
- `warehouse_colors`
- `warehouse_coldroomtemperatures`
- `sales_specialdeals`

Check:
- no FK output appears
- no relationship logic appears
- PK logic still works
- audit and temporal columns are tagged correctly

**Pass condition**: Profiling output is clean and FK‑free.

---

## Phase 2 — Fix type normalization and profile statistics

**Objective**: Correct type mistakes before adjusting key logic.

**What to change**
- Convert whole‑number floats like `7.0` into integer where appropriate
- Detect boolean values only when the values truly behave like booleans
- Keep unknown types only when evidence is insufficient
- Ensure `LastEditedBy` is integer or audit‑like, not boolean
- Ensure `validfrom` / `validto` are temporal, not identifiers

**Validate**
Re‑check:
- `warehouse_colors`
- `purchasing_suppliercategories`
- `sales_orders`
- `warehouse_coldroomtemperatures`

**Pass condition**: The obvious type mistakes are gone.

---

## Phase 3 — Fix uniqueness and key scoring

**Objective**: Stop PK over‑detection and the small‑table false suppression problem.

**What to change**
- Compute uniqueness ratio correctly
- Use non‑null counts as denominator for uniqueness, not total rows
- Use a weighted PK score instead of a simple uniqueness threshold
- Keep suppression rules, but do not let low‑cardinality automatically kill real keys
- Add small‑table confidence reduction, not automatic rejection

**Example rules**
- `specialdealid` should not be rejected just because the table has 2 rows
- `coldroomtemperatureid` should still be allowed as a PK candidate
- `colorid` should remain a strong PK candidate

**Validate**
Re‑check:
- `sales_specialdeals`
- `warehouse_coldroomtemperatures`
- `warehouse_colors`

**Pass condition**: Real keys survive small‑table cases, while fake keys remain suppressed.

---

## Phase 4 — Tighten PK suppression rules

**Objective**: Make suppression strong against obvious false positives.

**What to change**
Maintain suppression for:
- temporal fields
- audit fields
- constant columns
- zero‑entropy columns
- descriptive text columns
- geospatial columns
- measure columns
- mutable business attributes

**Important**: Do **not** suppress real key columns only because the table is small.

**Validate**
Check that the following are not PKs:
- `validfrom`
- `validto`
- `lasteditedby`
- `colorname`
- `countryname`
- `population`

**Pass condition**: The suppression engine blocks obvious wrong keys and still allows real identifiers.

---

## Phase 5 — Validate canonical and profile consistency

**Objective**: Confirm that `canonical.json` and `profile.json` agree on the real shape of each table.

**What to inspect**
For each file, verify:
- column count matches
- names are normalized consistently
- physical type is sensible
- sample values match the declared type
- audit and temporal columns are tagged correctly
- identifier columns are not mis‑classified as measures or booleans

**Priority files**
- `Application_Cities`
- `purchasing_purchaseorders`
- `purchasing_purchaseorderlines`
- `purchasing_suppliercategories`
- `sales_orders`
- `sales_specialdeals`
- `warehouse_colors`
- `warehouse_coldroomtemperatures`

**Pass condition**: Canonical and profile outputs are aligned.

---

## Phase 6 — Relationship layer only

**Objective**: Move all FK and relationship logic here.

**What to change**
- Relationship detection uses profiling outputs only as input
- Relationship layer can use PK candidates, statistics, descriptions, and semantic signals
- Relationship layer may use DuckDB support checks, ANN, clustering, or containment
- Profiling must remain untouched by relationship logic

**Validate**
Run relationship detection after profiling is clean.

**Pass condition**: `relationship.json` contains only the relationship layer’s output and does not contaminate profiling.

---

## Phase 7 — DBML and ER generation

**Objective**: Use `relationship.json` as the single source of truth for DBML and diagrams.

**What to change**
- DBML exporter should not invent keys
- DBML should use the validated PK list and only `TRUE_FK` relationships
- ER rendering should read from `relationship.json` and DBML only

**Validate**
Check that:
- only one PK is assigned per table unless a composite key is explicitly validated
- FK refs are realistic
- audit columns do not become DBML keys

**Pass condition**: The diagram becomes structurally realistic.

---

## Phase 8 — Enrichment layer

**Objective**: Allow enrichment to explain data, not redefine structure.

**What to change**
- low‑cardinality enrichment may add semantic meaning
- descriptions may explain business context
- enrichment must not create or rewrite PK/FK decisions

**Validate**
Confirm enrichment does not alter:
- PK outputs
- relationship outputs
- DBML outputs

**Pass condition**: Enrichment is informational only.

---

# Validation Checklist for Every Phase

Before moving to the next phase, check:
- Did the logic change as intended?
- Did the output improve?
- Did any unrelated behavior break?
- Are the key files still structurally valid?
- Is the change isolated to the current phase?

If any answer is no, stop and fix that phase first.

---

# Suggested Review Order for Files

1. `canonical.json`
2. `profile.json`
3. `pk.json`
4. `quality.json`
5. `relationship.json`
6. `low_cardinality_insights.json`
7. `descriptions.json`
8. `schema.dbml`
9. `erd.html`

---

## Final Acceptance Criteria

The system is correct when:
- profiling contains no FK logic
- PK detection is accurate and stable
- small tables do not lose real primary keys
- temporal and audit fields are not promoted to keys
- canonical and profile outputs agree
- `relationship.json` is realistic
- DBML uses only validated structure
- enrichment does not alter structure
- the UI can render stable, trustworthy diagrams

---

**Working Rule for Implementation**

**One phase at a time.** Do not combine phases. Do not patch outputs directly. Fix the logic, run the phase, inspect the result, and only then continue.
