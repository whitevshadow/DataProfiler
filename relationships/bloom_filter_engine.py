"""
Bloom Filter Engine

Provides probabilistic membership testing for FK containment pruning.

Purpose:
- Quickly reject impossible FK relationships
- Avoid expensive full containment validation
- Scale to large PK sets efficiently

Bloom Filter Properties:
- Space efficient: O(n) bits instead of O(n * value_size)
- False positives: possible (bloom says "maybe")
- False negatives: IMPOSSIBLE (bloom says "no" → definitive rejection)

Use Case:
    PK = {1, 2, 3, 4, 5, ..., 1M values}
    FK = {1001, 1002, 1003}
    
    Bloom filter trained on PK values.
    Query: 1001 in bloom? → NO → reject immediately
    Query: 1 in bloom? → MAYBE → requires full validation

Critical Rules:
- Bloom filter is PRUNING ONLY
- Bloom filter does NOT prove containment
- Positive results require deterministic validation
"""

import math
import hashlib
from typing import Set, List, Any, Optional
from relationships.relationship_models import OverlapEstimate


class BloomFilter:
    """
    Space-efficient probabilistic membership test.
    
    Supports add() and contains() operations.
    False positive rate configurable via bit array size and hash count.
    """
    
    def __init__(
        self,
        expected_elements: int,
        false_positive_rate: float = 0.01,
    ):
        """
        Initialize Bloom filter.
        
        Args:
            expected_elements: Expected number of elements to insert
            false_positive_rate: Target false positive probability (0.0-1.0)
        """
        self.expected_elements = expected_elements
        self.false_positive_rate = false_positive_rate
        
        # Calculate optimal bit array size and hash function count
        self.bit_count = self._calculate_bit_count(
            expected_elements, false_positive_rate
        )
        self.hash_count = self._calculate_hash_count(
            self.bit_count, expected_elements
        )
        
        # Initialize bit array
        self.bit_array = [False] * self.bit_count
        self.element_count = 0
    
    def add(self, item: Any) -> None:
        """Add an item to the Bloom filter."""
        item_str = str(item)
        for seed in range(self.hash_count):
            index = self._hash(item_str, seed)
            self.bit_array[index] = True
        self.element_count += 1
    
    def contains(self, item: Any) -> bool:
        """
        Check if item MIGHT be in the set.
        
        Returns:
            True: item MIGHT be present (requires validation)
            False: item is DEFINITELY NOT present (authoritative rejection)
        """
        item_str = str(item)
        for seed in range(self.hash_count):
            index = self._hash(item_str, seed)
            if not self.bit_array[index]:
                return False  # Definitive NO
        return True  # Maybe (requires validation)
    
    def _hash(self, item: str, seed: int) -> int:
        """Generate hash index for item with given seed."""
        hasher = hashlib.md5()
        hasher.update(f"{item}:{seed}".encode())
        hash_value = int(hasher.hexdigest(), 16)
        return hash_value % self.bit_count
    
    def _calculate_bit_count(self, n: int, p: float) -> int:
        """
        Calculate optimal bit array size.
        
        Formula: m = -(n * ln(p)) / (ln(2)^2)
        """
        if n == 0:
            return 1000  # Default minimum
        m = -(n * math.log(p)) / (math.log(2) ** 2)
        return max(1000, int(m))
    
    def _calculate_hash_count(self, m: int, n: int) -> int:
        """
        Calculate optimal hash function count.
        
        Formula: k = (m/n) * ln(2)
        """
        if n == 0:
            return 3  # Default
        k = (m / n) * math.log(2)
        return max(1, min(20, int(k)))  # Limit to reasonable range
    
    def get_memory_usage_bytes(self) -> int:
        """Estimate memory usage in bytes."""
        # Python bool is 1 byte each (simplified)
        return len(self.bit_array)
    
    def get_actual_false_positive_rate(self) -> float:
        """Calculate actual false positive rate based on current state."""
        if self.element_count == 0:
            return 0.0
        # FP rate formula: (1 - e^(-kn/m))^k
        exponent = -(self.hash_count * self.element_count) / self.bit_count
        fp_rate = (1 - math.exp(exponent)) ** self.hash_count
        return fp_rate


class BloomFilterEngine:
    """
    Engine for building and querying Bloom filters for FK containment checks.
    """
    
    def __init__(
        self,
        false_positive_rate: float = 0.01,
        max_bloom_size_mb: int = 100,
    ):
        """
        Initialize Bloom filter engine.
        
        Args:
            false_positive_rate: Target false positive rate
            max_bloom_size_mb: Maximum Bloom filter size in MB
        """
        self.false_positive_rate = false_positive_rate
        self.max_bloom_size_mb = max_bloom_size_mb
        self.max_bloom_size_bytes = max_bloom_size_mb * 1024 * 1024
    
    def build_bloom_filter(
        self,
        pk_values: List[Any],
    ) -> BloomFilter:
        """
        Build a Bloom filter from PK values.
        
        Args:
            pk_values: List of primary key values
        
        Returns:
            Trained BloomFilter instance
        """
        bloom = BloomFilter(
            expected_elements=len(pk_values),
            false_positive_rate=self.false_positive_rate,
        )
        
        # Check size limit
        if bloom.get_memory_usage_bytes() > self.max_bloom_size_bytes:
            # Adjust false positive rate to fit memory budget
            adjusted_fp_rate = self._calculate_adjusted_fp_rate(
                len(pk_values),
                self.max_bloom_size_bytes,
            )
            bloom = BloomFilter(
                expected_elements=len(pk_values),
                false_positive_rate=adjusted_fp_rate,
            )
        
        # Train the bloom filter
        for value in pk_values:
            if value is not None:  # Skip nulls
                bloom.add(value)
        
        return bloom
    
    def estimate_overlap(
        self,
        fk_values: List[Any],
        bloom: BloomFilter,
    ) -> OverlapEstimate:
        """
        Estimate overlap between FK values and PK values using Bloom filter.
        
        Args:
            fk_values: List of foreign key values
            bloom: Trained BloomFilter on PK values
        
        Returns:
            OverlapEstimate with approximate overlap statistics
        """
        if not fk_values:
            return OverlapEstimate(
                overlap_count=0,
                overlap_ratio=0.0,
                is_approximate=True,
                bloom_filter_used=True,
            )
        
        # Count FK values that MIGHT be in PK set
        possible_matches = 0
        definite_misses = 0
        
        for fk_value in fk_values:
            if fk_value is None:
                continue
            
            if bloom.contains(fk_value):
                possible_matches += 1
            else:
                definite_misses += 1
        
        total_checked = possible_matches + definite_misses
        if total_checked == 0:
            overlap_ratio = 0.0
        else:
            # Approximate overlap ratio (inflated due to false positives)
            overlap_ratio = possible_matches / total_checked
        
        return OverlapEstimate(
            overlap_count=possible_matches,
            overlap_ratio=overlap_ratio,
            is_approximate=True,
            bloom_filter_used=True,
            sample_size=total_checked,
        )
    
    def should_reject_candidate(
        self,
        fk_sample: List[Any],
        bloom: BloomFilter,
        rejection_threshold: float = 0.10,
    ) -> bool:
        """
        Decide whether to reject FK candidate based on Bloom filter test.
        
        If < rejection_threshold of FK values pass Bloom filter,
        reject the relationship immediately.
        
        Args:
            fk_sample: Sample of FK values
            bloom: Bloom filter trained on PK values
            rejection_threshold: Minimum overlap ratio to proceed
        
        Returns:
            True if relationship should be rejected, False otherwise
        """
        overlap = self.estimate_overlap(fk_sample, bloom)
        return overlap.overlap_ratio < rejection_threshold
    
    def _calculate_adjusted_fp_rate(
        self,
        n_elements: int,
        max_bytes: int,
    ) -> float:
        """
        Calculate adjusted false positive rate to fit memory budget.
        
        Given: max_bytes, n_elements
        Solve for: p (false positive rate)
        
        From: m = -(n * ln(p)) / (ln(2)^2)
        """
        m_bits = max_bytes * 8
        ln2_squared = math.log(2) ** 2
        
        # Solve: p = e^(-(m * ln2_squared) / n)
        exponent = -(m_bits * ln2_squared) / n_elements
        adjusted_fp_rate = math.exp(exponent)
        
        # Clamp to reasonable range
        return max(0.001, min(0.5, adjusted_fp_rate))


# Singleton instance
_bloom_engine = BloomFilterEngine()


def build_bloom_filter(pk_values: List[Any]) -> BloomFilter:
    """Convenience function to build a Bloom filter."""
    return _bloom_engine.build_bloom_filter(pk_values)


def estimate_overlap_with_bloom(
    fk_values: List[Any],
    bloom: BloomFilter,
) -> OverlapEstimate:
    """Convenience function to estimate overlap."""
    return _bloom_engine.estimate_overlap(fk_values, bloom)
