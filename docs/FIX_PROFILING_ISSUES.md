# Profiling Issues Fix

## Issues Identified

### 1. **row_count_estimate is always NULL**

**Root Cause**: 
- Profiling engine looks for `metadata.get("sample_row_count")`
- Canonical JSON has `sampling.total_rows_estimate` and `sampling.sample_size`
- Field mapping mismatch

**Impact**: 
- Profile shows `"row_count_estimate": null`
- Missing critical table size information

### 2. **Too Many PK Candidates**

**Root Cause**: 
- Sample-based profiling on 100 rows
- Boolean/low-cardinality columns accidentally have 100% uniqueness in small sample
- PK threshold (0.70) too low for sample-based analysis
- Suppression rules don't account for sample size

**Examples**:
```json
{
  "pk_candidates": [
    "otherlanguages",      // Boolean column
    "userpreferences",     // JSON/text column
    "customfields",        // JSON column
    "ispermittedtologon",  // Boolean column
    "issystemuser",        // Boolean column  
    "isemployee",          // Boolean column
    "issalesperson"        // Boolean column
  ]
}
```

**Impact**:
- 7 PK candidates for `application_people` (should be 1: `personid`)
- 5 PK candidates for `Sales_Customers` (should be 1: `customerid`)
- Relationship detection confusion

### 3. **FK Detection Works but Relationships Aren't Computed**

**Status**: 
- FK **candidates** are detected correctly (e.g., `billtocustomerid`, `customercategoryid`)
- FK **relationships** require separate enrichment step (`enrich_relationships`)
- Not a bug - user needs to run enrichment

## Fixes Required

### Fix 1: Correct row_count_estimate Mapping

**File**: `profiler/profiling/profiling_engine.py`

**Change**:
```python
# BEFORE (line ~175)
row_count_estimate=metadata.get("sample_row_count")

# AFTER
row_count_estimate=canonical_dict.get("sampling", {}).get("total_rows_estimate") 
                   or canonical_dict.get("sampling", {}).get("sample_size")
```

### Fix 2: Stricter PK Detection for Samples

**File**: `profiler/profiling/pk_detector.py`

**Changes**:

1. **Raise PK threshold for sample-based profiling**:
   ```python
   # BEFORE
   is_candidate = pk_score >= 0.70
   
   # AFTER
   # If sample size < 200, require higher threshold
   threshold = 0.85 if sample_size < 200 else 0.70
   is_candidate = pk_score >= threshold
   ```

2. **Add name-based PK prioritization**:
   ```python
   # Boost score if name clearly indicates PK
   if re.match(r'^.*id$', name) and name.endswith('id'):
       base_score += 0.15  # Boost *ID columns
   ```

3. **Penalize non-ID columns with perfect uniqueness in small samples**:
   ```python
   # If 100% unique in small sample but name doesn't suggest PK
   if uniqueness_ratio == 1.0 and sample_size < 200:
       if not re.match(r'.*(id|key|code|identifier)$', name):
           penalty += 0.30  # Strong penalty for accidental uniqueness
   ```

### Fix 3: Add Boolean Column Suppression

**File**: `profiler/profiling/suppression_rules.py`

**Add new rule**:
```python
class BooleanColumnSuppression(PKSuppressionRule):
    """Suppress boolean columns that happen to be unique in sample."""
    
    BOOLEAN_PATTERNS = [
        r'^is[A-Z].*',           # isEmployee, isActive
        r'^has[A-Z].*',          # hasPermission
        r'^can[A-Z].*',          # canEdit
        r'^.*_(flag|enabled|disabled)$',
    ]
    
    def evaluate(self, column_data: dict) -> SuppressionResult:
        column_name = column_data.get("normalized_name", "")
        distinct_count = column_data.get("distinct_count", 0)
        sample_size = column_data.get("sample_size", 0)
        
        # Check boolean naming patterns
        for pattern in self.BOOLEAN_PATTERNS:
            if re.match(pattern, column_name):
                # Even if unique in sample, suppress
                return SuppressionResult(
                    suppress=True,
                    reason=f"Boolean column pattern '{column_name}'",
                    severity=SuppressionSeverity.CRITICAL
                )
        
        # Suppress if distinct_count suspiciously equals sample_size for non-ID
        if distinct_count == sample_size and sample_size < 200:
            if not re.search(r'(id|key|code)$', column_name):
                return SuppressionResult(
                    suppress=True,
                    reason=f"Accidental uniqueness in small sample (n={sample_size})",
                    severity=SuppressionSeverity.HIGH
                )
        
        return SuppressionResult(suppress=False, reason="", severity=SuppressionSeverity.LOW)
```

### Fix 4: Single PK Selection

**File**: `profiler/profiling/profiling_engine.py`

**Change** (line ~170):
```python
# BEFORE: Return ALL PK candidates
pk_candidate_names = [name for name, score, _ in ranked_pks]

# AFTER: Return only TOP 1 PK candidate (with high confidence threshold)
# Only include PKs with score >= 0.80 (strong confidence)
strong_pks = [(name, score, ev) for name, score, ev in ranked_pks if score >= 0.80]

if strong_pks:
    # Take only the best PK
    pk_candidate_names = [strong_pks[0][0]]  # Top 1 only
else:
    pk_candidate_names = []
```

## Expected Results After Fix

### Before Fix
```json
{
  "table_profile": {
    "row_count_estimate": null,
    "pk_candidates": [
      "otherlanguages",
      "userpreferences",
      "customfields",
      "ispermittedtologon",
      "issystemuser",
      "isemployee",
      "issalesperson"
    ]
  }
}
```

### After Fix
```json
{
  "table_profile": {
    "row_count_estimate": 2910,  // From sampling.sample_size or total_rows_estimate
    "pk_candidates": [
      "personid"  // Single best PK
    ]
  }
}
```

## Testing

Run after changes:
```bash
# Re-profile all tables
python -m profiler.services profile_directory data/ output/

# Check results
python -c "
import json
profile = json.load(open('output/profiles/application_people.profile.json'))
print('Row count:', profile['table_profile']['row_count_estimate'])
print('PK candidates:', profile['table_profile']['pk_candidates'])
print('FK candidates:', profile['table_profile']['fk_candidates'])
"
```

Expected output:
```
Row count: 2910
PK candidates: ['personid']
FK candidates: ['personid']
```

## Summary

**3 Critical Fixes**:
1. ✅ Map `row_count_estimate` to correct canonical field
2. ✅ Add boolean column suppression rule
3. ✅ Return only TOP 1 PK candidate (best score)
4. ✅ Raise PK threshold for small samples (0.70 → 0.85)
5. ✅ Penalize non-ID columns with accidental uniqueness
