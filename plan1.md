# plan1.md

## Goal

Refactor NeuLeap key detection so that **Primary Key detection chooses exactly one real PK per table** using name ownership, semantic evidence, suppression rules, and table context. No direct output patching—fix the logic.

---

## Phase 1 — Define Table Ownership

For each table, determine the *owner* identifier (root name).

**Examples**
- `sales_orders` → `order`
- `sales_invoicelines` → `invoiceline`
- `purchasing_purchaseorderlines` → `purchaseorderline`
- `warehouse_colors` → `color`
- `Application_Cities` → `city`
- `Application_Countries` → `country`

**Rules**
1. The owner identifier is the strongest PK candidate.
2. Columns matching `<owner>id` receive a strong boost.
3. Other `*_id` columns in the same table are **not** allowed to auto‑become PKs.

**Example**
- `sales_orders.orderid` → strong PK anchor
- `sales_orders.customerid` → not PK (FK candidate only)
- `sales_orders.salespersonpersonid` → not PK

---

## Phase 2 — Single PK Selection

Every table must have exactly one default PK candidate unless the table is explicitly validated as a composite‑key table.

**Default rule**
- Choose the top‑scoring *anchor* column as PK.
- If two columns score similarly, prefer in order:
  1. Table‑root identifier name
  2. Exact `*_id` match to table name
  3. Lowest ambiguity
  4. Highest stability
  5. Best suppression‑free evidence

**Never allow** multiple identifiers as PKs (e.g., `orderid` + `customerid`) unless a composite‑key validation explicitly proves it.

---

## Phase 3 — Name‑Based PK Scoring

Weighted PK score (sum = 1.0):
- 0.40 uniqueness
- 0.20 non‑null ratio
- 0.15 entropy
- 0.15 table‑name match
- 0.10 type stability

**Boosts** (+)
- Exact table‑root match
- `id` suffix
- `*_id` pattern
- Integer or UUID identifier type

**Penalties** (‑)
- Audit names (`lasteditedby`, `createdby`, `modifiedby`, `updatedby`)
- Temporal names (`validfrom`, `validto`, `timestamp`, `effective_date`)
- Descriptive names (`name`, `description`, `comment`, `title`)
- Measure names (`amount`, `price`, `quantity`, `population`, `rate`)
- Geospatial names (`location`, `latitude`, `longitude`)
- Small‑table over‑fitting penalty

**Threshold**: candidate PK only if score ≥ 0.70, but final PK selection still enforces a single anchor per table.

---

## Phase 4 — Suppression Rules

Hard‑suppress as PK candidates:
- Audit columns
- Temporal columns
- Constant columns
- Zero‑entropy columns
- Descriptive text columns
- Measure columns
- Geospatial columns
- Mutable business attributes

**Special rule**: `lasteditedby` is always treated as audit metadata, may become an FK reference later, **must never be a PK**.

---

## Phase 5 — Compete Identifier Columns Against Table Root

If a table has multiple identifier‑like columns:
- Only the *owner identifier* may become PK.
- All other identifier‑like columns are downgraded to FK‑only or non‑PK roles.
- Name similarity to table root beats generic `*_id` patterns.

**Examples**
- `sales_orders`
  - `orderid` → PK
  - `customerid`, `salespersonpersonid`, `contactpersonid` → FK only
- `purchasing_purchaseorderlines`
  - `purchaseorderlineid` → PK
  - `purchaseorderid`, `stockitemid`, `packagetypeid` → FK only
- `sales_invoicelines`
  - `invoicelineid` → PK
  - `invoiceid`, `stockitemid`, `packagetypeid` → FK only

---

## Phase 6 — Keep FK Logic Out of Profiling

**Profiling layer may emit only**:
- `pk_candidate`
- `pk_confidence`
- `quality`
- `type`
- `statistics`
- Semantic hints (identifier, audit, temporal, measure, dimension)

**Profiling must NOT emit** any relationship information:
- `fk_candidate`
- `fk_confidence`
- `referenced_entity`
- `relational_role`
- `relationship evidence`
- `join support`

All FK and relationship inference belongs in the *relationship layer*.

---

## Phase 7 — Handle Small Tables Correctly

Small tables should **not** lose a real PK simply because they contain few rows.
- Reduce PK confidence slightly for small tables but still allow the owner identifier to win.
- Ensure examples such as:
  - `sales_specialdeals.specialdealid`
  - `warehouse_coldroomtemperatures.coldroomtemperatureid`
  - `warehouse_colors.colorid`
  remain PKs.

---

## Phase 8 — Output Rules

For each table, the profiler must emit:
- **Exactly one** default PK candidate (the chosen anchor).
- Other ID‑like columns downgraded to non‑PK roles.
- **No FK fields** or relationship leakage.
- If a table truly requires a composite PK, this must be explicitly validated and rare.

---

## Phase 9 — Validation Checks

After implementing the changes, run validation on the following tables:
- `Application_Cities`
- `purchasing_purchaseorderlines`
- `purchasing_purchaseorders`
- `sales_orders`
- `sales_invoicelines`
- `sales_specialdeals`
- `warehouse_coldroomtemperatures`
- `warehouse_colors`

**Check that**:
- Each table has **one real PK anchor**.
- `lasteditedby` is **not** a PK.
- `validfrom` / `validto` are **not** PKs.
- Identifier‑like columns do not multiply PKs.
- No FK logic appears in profiling output.

---

## Final Objective

Make key selection deterministic and single‑owner:
- One table → one anchor PK.
- All other identifier‑like columns downgraded unless explicitly validated as composite.
- Relationship logic handled later.
- Audit fields never promoted to PK.

**Do not patch output directly** – fix the ranking, suppression, and ownership logic in the code.
