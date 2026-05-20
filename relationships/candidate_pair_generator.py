"""
Candidate Pair Generator

Generates FK->PK candidate pairs while avoiding O(n²) explosion.

Strategy:
1. Only consider PK candidates (not all columns)
2. Use naming heuristics (orders.customer_id → customers.customer_id)
3. Filter by type compatibility
4. Filter by cardinality compatibility
5. Optional: Use semantic ANN for additional candidates

Anti-Patterns Prevented:
- Comparing every column vs every column (O(n²))
- Comparing columns across incompatible types
- Comparing low-cardinality non-PK columns
- Self-table comparisons (except self-referential)

Complexity:
- Without optimization: O(tables² * columns²)
- With PK filtering: O(tables * fk_columns * pk_candidates)
- Typical: ~10-100 candidates per table instead of 10,000+
"""

from typing import List, Dict, Set, Tuple, Optional
import re
from relationships.relationship_models import CandidatePair
from relationships.type_compatibility import check_type_compatibility


class CandidatePairGenerator:
    """
    Generates candidate FK->PK pairs using intelligent heuristics.
    
    Avoids O(n²) explosion by:
    - Only considering PK candidates as targets
    - Using naming patterns to filter candidates
    - Applying type compatibility filters
    - Filtering by cardinality ratios
    """
    
    # Columns that look like FK references (used to gate type-compat fallback)
    FK_NAME_SUFFIXES = ("_id", "id", "_key", "key", "_fk", "_ref", "_code", "_num", "_no")

    # Audit / noise columns — never generate as FK candidates
    SKIP_COLUMN_PATTERNS = [
        r"^validfrom$", r"^validto$", r"^lasteditedby$", r"^createdby$",
        r"^modifiedby$", r"^rowguid$", r".*guid.*", r".*uuid.*",
        r"^is_", r"^has_",
    ]

    def __init__(
        self,
        min_type_compatibility: float = 0.5,
        max_cardinality_ratio: float = 1.05,  # FK distinct / PK distinct (sample tolerant)
        enable_naming_heuristics: bool = True,
        enable_self_referential: bool = True,
    ):
        """
        Initialize candidate pair generator.

        Args:
            min_type_compatibility: Minimum type compatibility score (0.0-1.0)
            max_cardinality_ratio: Max ratio of FK distinct / PK distinct
            enable_naming_heuristics: Use naming patterns for candidate generation
            enable_self_referential: Allow self-referential relationships
        """
        self.min_type_compatibility = min_type_compatibility
        self.max_cardinality_ratio = max_cardinality_ratio
        self.enable_naming_heuristics = enable_naming_heuristics
        self.enable_self_referential = enable_self_referential
        self._skip_re = [re.compile(p, re.IGNORECASE) for p in self.SKIP_COLUMN_PATTERNS]
    
    def generate_candidates(
        self,
        table_profiles: Dict[str, Dict],
        pk_candidates: Dict[str, List[Dict]],
    ) -> List[CandidatePair]:
        """
        Generate candidate FK->PK pairs.
        
        Args:
            table_profiles: Dict mapping table_name -> profile with column statistics
            pk_candidates: Dict mapping table_name -> list of PK candidate dicts
        
        Returns:
            List of CandidatePair objects for validation
        """
        candidates = set()  # Use set to deduplicate
        
        # Build PK index for fast lookup
        pk_index = self._build_pk_index(pk_candidates)
        
        # For each table, generate FK candidates from its columns
        for fk_table, fk_profile in table_profiles.items():
            fk_columns = fk_profile.get("columns", [])

            for fk_col_profile in fk_columns:
                fk_col = fk_col_profile["column_name"]
                fk_type = fk_col_profile.get("physical_type", "UNKNOWN")
                fk_distinct = fk_col_profile.get("distinct_count", 0)

                # Skip audit/noise/GUID columns entirely
                if self._is_skip_column(fk_col):
                    continue

                # Skip if this column is already a PK in its own table
                if self._is_column_pk(fk_table, fk_col, pk_candidates):
                    continue

                # Generate candidates for this FK column
                column_candidates = self._generate_candidates_for_column(
                    fk_table=fk_table,
                    fk_col=fk_col,
                    fk_type=fk_type,
                    fk_distinct=fk_distinct,
                    pk_index=pk_index,
                    pk_candidates=pk_candidates,
                )

                candidates.update(column_candidates)
        
        return list(candidates)
    
    def _build_pk_index(
        self,
        pk_candidates: Dict[str, List[Dict]],
    ) -> Dict[str, List[Dict]]:
        """
        Build an index of PK candidates for fast lookup.
        
        Returns:
            Dict mapping pk_table -> list of PK candidate dicts
        """
        pk_index = {}
        
        for table_name, candidates in pk_candidates.items():
            pk_index[table_name] = [
                {
                    "column": c["column"],
                    "confidence": c["confidence"],
                    "accepted": c.get("accepted", True),
                    "physical_type": c.get("physical_type", "UNKNOWN"),
                    "distinct_count": c.get("distinct_count", 0),
                }
                for c in candidates
                if c.get("accepted", True)  # Only accepted PK candidates
            ]
        
        return pk_index
    
    def _is_column_pk(
        self,
        table: str,
        column: str,
        pk_candidates: Dict[str, List[Dict]],
    ) -> bool:
        """Check if a column is a PK candidate in its own table."""
        table_pks = pk_candidates.get(table, [])
        for pk in table_pks:
            if pk["column"] == column and pk.get("accepted", True):
                return True
        return False
    
    def _generate_candidates_for_column(
        self,
        fk_table: str,
        fk_col: str,
        fk_type: str,
        fk_distinct: int,
        pk_index: Dict[str, List[Dict]],
        pk_candidates: Dict[str, List[Dict]],
    ) -> Set[CandidatePair]:
        """
        Generate PK candidates for a specific FK column.
        
        Strategy:
        1. Naming heuristics (customer_id → customers.customer_id)
        2. Type-compatible PKs across all tables
        3. Cardinality filtering
        """
        candidates = set()
        
        # Strategy 1: Naming heuristics
        if self.enable_naming_heuristics:
            naming_candidates = self._generate_naming_candidates(
                fk_table=fk_table,
                fk_col=fk_col,
                fk_type=fk_type,
                fk_distinct=fk_distinct,
                pk_index=pk_index,
            )
            candidates.update(naming_candidates)
        
        # Strategy 2: Type-compatible scan — ONLY when:
        #   a) naming found zero candidates (no naming signal at all), AND
        #   b) the column name looks like a FK reference (_id, _key, etc.)
        # This prevents O(n²) explosion for generic columns.
        if len(candidates) == 0 and self._is_fk_name_pattern(fk_col):
            type_candidates = self._generate_type_compatible_candidates(
                fk_table=fk_table,
                fk_col=fk_col,
                fk_type=fk_type,
                fk_distinct=fk_distinct,
                pk_index=pk_index,
            )
            candidates.update(type_candidates)

        return candidates
    
    def _generate_naming_candidates(
        self,
        fk_table: str,
        fk_col: str,
        fk_type: str,
        fk_distinct: int,
        pk_index: Dict[str, List[Dict]],
    ) -> Set[CandidatePair]:
        """
        Generate candidates using naming heuristics.
        
        Patterns:
        - orders.customer_id → customers.customer_id
        - sales.city_id → cities.city_id
        - items.parent_item_id → items.item_id (self-referential)
        """
        candidates = set()
        
        # Extract entity name from FK column
        # Examples: customer_id → customer, cityid → city
        entity_name = self._extract_entity_name(fk_col)
        if not entity_name:
            return candidates
        
        # Find PK columns with matching patterns
        for pk_table, pk_list in pk_index.items():
            # Skip self-table unless self-referential enabled
            if pk_table == fk_table and not self.enable_self_referential:
                continue
            
            for pk_candidate in pk_list:
                pk_col = pk_candidate["column"]
                pk_type = pk_candidate["physical_type"]
                pk_distinct = pk_candidate["distinct_count"]
                pk_confidence = pk_candidate["confidence"]
                
                # Check if names match
                naming_similarity = self._compute_naming_similarity(
                    fk_col, pk_col, entity_name, pk_table
                )
                
                if naming_similarity < 0.5:
                    continue
                
                # Check type compatibility
                type_result = check_type_compatibility(fk_type, pk_type)
                if not type_result.compatible:
                    continue
                
                # Check cardinality compatibility
                if pk_distinct > 0:
                    cardinality_ratio = fk_distinct / pk_distinct
                    if cardinality_ratio > self.max_cardinality_ratio:
                        continue
                
                # Valid candidate
                candidate = CandidatePair(
                    fk_table=fk_table,
                    fk_column=fk_col,
                    pk_table=pk_table,
                    pk_column=pk_col,
                    fk_type=fk_type,
                    pk_type=pk_type,
                    pk_confidence=pk_confidence,
                    pk_accepted=pk_candidate["accepted"],
                    generation_reason="naming_heuristic",
                    naming_similarity=naming_similarity,
                    type_compatible=True,
                )
                candidates.add(candidate)
        
        return candidates
    
    def _generate_type_compatible_candidates(
        self,
        fk_table: str,
        fk_col: str,
        fk_type: str,
        fk_distinct: int,
        pk_index: Dict[str, List[Dict]],
    ) -> Set[CandidatePair]:
        """
        Generate candidates by scanning type-compatible PKs.
        
        Fallback when naming heuristics don't find strong matches.
        """
        candidates = set()
        
        for pk_table, pk_list in pk_index.items():
            # Skip self-table unless self-referential enabled
            if pk_table == fk_table and not self.enable_self_referential:
                continue
            
            for pk_candidate in pk_list:
                pk_col = pk_candidate["column"]
                pk_type = pk_candidate["physical_type"]
                pk_distinct = pk_candidate["distinct_count"]
                pk_confidence = pk_candidate["confidence"]
                
                # Check type compatibility
                type_result = check_type_compatibility(fk_type, pk_type)
                if type_result.compatibility_score < self.min_type_compatibility:
                    continue
                
                # Check cardinality compatibility
                if pk_distinct > 0:
                    cardinality_ratio = fk_distinct / pk_distinct
                    if cardinality_ratio > self.max_cardinality_ratio:
                        continue
                
                # Valid candidate
                naming_similarity = self._compute_naming_similarity(
                    fk_col, pk_col, "", pk_table
                )
                
                candidate = CandidatePair(
                    fk_table=fk_table,
                    fk_column=fk_col,
                    pk_table=pk_table,
                    pk_column=pk_col,
                    fk_type=fk_type,
                    pk_type=pk_type,
                    pk_confidence=pk_confidence,
                    pk_accepted=pk_candidate["accepted"],
                    generation_reason="type_match",
                    naming_similarity=naming_similarity,
                    type_compatible=True,
                )
                candidates.add(candidate)
        
        return candidates
    
    def _is_skip_column(self, col: str) -> bool:
        """Return True if the column should be skipped entirely as a FK candidate."""
        for pattern in self._skip_re:
            if pattern.search(col):
                return True
        return False

    def _is_fk_name_pattern(self, col: str) -> bool:
        """Return True if the column name suggests it could be a FK reference."""
        c = col.lower().strip()
        return any(c.endswith(s) for s in self.FK_NAME_SUFFIXES)

    def _extract_entity_name(self, column_name: str) -> Optional[str]:
        """
        Extract entity name from FK column.

        Examples:
        - customer_id → customer
        - cityid → city
        - delivery_city_id → city
        - parent_item_id → item
        """
        col_lower = column_name.lower().strip()

        # Remove common FK suffixes
        suffixes = ["_id", "id", "_key", "key", "_fk", "fk"]
        for suffix in suffixes:
            if col_lower.endswith(suffix):
                entity = col_lower[: -len(suffix)]
                if entity:
                    return entity

        return None
    
    def _compute_naming_similarity(
        self,
        fk_col: str,
        pk_col: str,
        fk_entity: str,
        pk_table: str,
    ) -> float:
        """
        Compute naming similarity between FK and PK columns.
        
        Args:
            fk_col: FK column name (e.g., "customer_id")
            pk_col: PK column name (e.g., "customer_id")
            fk_entity: Extracted entity name from FK (e.g., "customer")
            pk_table: PK table name (e.g., "customers")
        
        Returns:
            Similarity score 0.0-1.0
        """
        fk_lower = fk_col.lower().strip()
        pk_lower = pk_col.lower().strip()
        
        # Exact match
        if fk_lower == pk_lower:
            return 1.0
        
        # Normalize table name (remove prefixes, handle plurals)
        pk_table_normalized = self._normalize_table_name(pk_table)
        
        # Check if FK entity matches PK table
        if fk_entity and pk_table_normalized:
            if fk_entity == pk_table_normalized:
                return 0.95  # Strong match: customer_id → customers table
            if fk_entity.rstrip("s") == pk_table_normalized.rstrip("s"):
                return 0.90  # Plural variant match
        
        # Check if FK contains PK column name
        if pk_lower in fk_lower or fk_lower in pk_lower:
            return 0.80
        
        # Check common substring ratio
        # Use simple overlap ratio
        common_length = len(set(fk_lower) & set(pk_lower))
        max_length = max(len(fk_lower), len(pk_lower))
        if max_length > 0:
            overlap_ratio = common_length / max_length
            return min(0.7, overlap_ratio)
        
        return 0.0
    
    def _normalize_table_name(self, table_name: str) -> str:
        """
        Normalize table name for matching.
        
        Examples:
        - Sales_Customers → customer
        - application_cities → city
        - warehouse_colors → color
        """
        name_lower = table_name.lower().strip()
        
        # Remove common prefixes
        prefixes = ["application_", "sales_", "purchasing_", "warehouse_", "dbo_", "public_"]
        for prefix in prefixes:
            if name_lower.startswith(prefix):
                name_lower = name_lower[len(prefix):]
                break
        
        # Handle plurals
        if name_lower.endswith("ies"):
            name_lower = name_lower[:-3] + "y"  # cities → city
        elif name_lower.endswith("es"):
            name_lower = name_lower[:-2]  # addresses → address
        elif name_lower.endswith("s"):
            name_lower = name_lower[:-1]  # customers → customer
        
        return name_lower
