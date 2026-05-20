"""Join recommendation engine for NeuLeap Data Profiler.

Recommends SQL joins based ONLY on TRUE_FK relationships.
NEVER uses semantic-only or text similarity matches.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class JoinRecommendation:
    """Single join recommendation."""
    
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    join_type: str  # INNER JOIN, LEFT JOIN, etc.
    confidence: float  # 0.0-1.0
    relationship_class: str  # Should be TRUE_FK
    containment_ratio: float  # Percentage of FK values found in PK
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JoinRecommendation:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
    
    def to_sql(self) -> str:
        """Generate SQL join syntax.
        
        Returns:
            SQL join clause
        """
        return (
            f"{self.join_type} {self.right_table} "
            f"ON {self.left_table}.{self.left_column} = {self.right_table}.{self.right_column}"
        )


class JoinRecommender:
    """Recommends joins based on TRUE_FK relationships only."""
    
    # Minimum confidence for join recommendation
    MIN_CONFIDENCE = 0.7
    
    # Minimum containment ratio for TRUE_FK
    MIN_CONTAINMENT = 0.9
    
    def __init__(self, relationships_path: Path | None = None):
        """Initialize join recommender.
        
        Args:
            relationships_path: Path to relationships.json
        """
        self.relationships_path = relationships_path or Path("output/relationships/relationships.json")
        self.relationships: list[dict[str, Any]] = []
        self._load_relationships()
    
    def _load_relationships(self) -> None:
        """Load relationships from disk."""
        if not self.relationships_path.exists():
            return
        
        try:
            data = json.loads(self.relationships_path.read_text(encoding="utf-8"))
            self.relationships = data.get("relationships", [])
        except Exception as e:
            print(f"Warning: Could not load relationships: {e}")
    
    def recommend_joins(
        self,
        table: str | None = None,
        min_confidence: float | None = None
    ) -> list[JoinRecommendation]:
        """Recommend joins for a table or all tables.
        
        Args:
            table: Optional table name to filter recommendations
            min_confidence: Optional minimum confidence threshold
            
        Returns:
            List of join recommendations
        """
        min_conf = min_confidence if min_confidence is not None else self.MIN_CONFIDENCE
        recommendations: list[JoinRecommendation] = []
        
        for rel in self.relationships:
            # ONLY TRUE_FK relationships
            if rel.get("relationship_class") != "TRUE_FK":
                continue
            
            # Check confidence
            confidence = rel.get("confidence", 0.0)
            if confidence < min_conf:
                continue
            
            # Check containment ratio
            containment = rel.get("containment_ratio", 0.0)
            if containment < self.MIN_CONTAINMENT:
                continue
            
            # Extract join information
            source_table = rel.get("source_table", "")
            source_column = rel.get("source_column", "")
            target_table = rel.get("target_table", "")
            target_column = rel.get("target_column", "")
            
            # Filter by table if specified
            if table and table.lower() not in (source_table.lower(), target_table.lower()):
                continue
            
            # Determine join type based on containment
            join_type = self._determine_join_type(containment)
            
            # Create recommendation
            recommendation = JoinRecommendation(
                left_table=source_table,
                left_column=source_column,
                right_table=target_table,
                right_column=target_column,
                join_type=join_type,
                confidence=confidence,
                relationship_class="TRUE_FK",
                containment_ratio=containment
            )
            
            recommendations.append(recommendation)
        
        # Sort by confidence descending
        recommendations.sort(key=lambda r: r.confidence, reverse=True)
        
        return recommendations
    
    def _determine_join_type(self, containment_ratio: float) -> str:
        """Determine appropriate join type based on containment.
        
        Args:
            containment_ratio: FK containment in PK (0.0-1.0)
            
        Returns:
            SQL join type
        """
        if containment_ratio >= 0.98:
            # Nearly all FK values exist in PK - INNER JOIN is safe
            return "INNER JOIN"
        elif containment_ratio >= 0.9:
            # Most FK values exist - INNER JOIN with potential data loss
            return "INNER JOIN"
        else:
            # Some FK values missing - LEFT JOIN preserves FK side
            return "LEFT JOIN"
    
    def save_recommendations(
        self,
        recommendations: list[JoinRecommendation],
        output_path: Path | None = None
    ) -> None:
        """Save join recommendations to disk.
        
        Args:
            recommendations: List of join recommendations
            output_path: Optional output path (default: output/joins/join_recommendations.json)
        """
        output_path = output_path or Path("output/joins/join_recommendations.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "recommendations": [r.to_dict() for r in recommendations],
            "count": len(recommendations),
            "criteria": {
                "min_confidence": self.MIN_CONFIDENCE,
                "min_containment": self.MIN_CONTAINMENT,
                "relationship_class": "TRUE_FK"
            }
        }
        
        output_path.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )
    
    def generate_sql_script(
        self,
        base_table: str,
        recommendations: list[JoinRecommendation] | None = None
    ) -> str:
        """Generate SQL script with all recommended joins for a base table.
        
        Args:
            base_table: Base table for FROM clause
            recommendations: Optional list of recommendations (default: all for base_table)
            
        Returns:
            SQL SELECT statement with joins
        """
        if recommendations is None:
            recommendations = self.recommend_joins(table=base_table)
        
        # Filter to relevant joins
        relevant_joins = [
            r for r in recommendations
            if r.left_table.lower() == base_table.lower()
        ]
        
        if not relevant_joins:
            return f"SELECT * FROM {base_table};"
        
        # Build SQL
        sql_lines = [f"SELECT *", f"FROM {base_table}"]
        
        for rec in relevant_joins:
            sql_lines.append(rec.to_sql())
        
        sql_lines.append(";")
        
        return "\n".join(sql_lines)
    
    def validate_recommendations(self) -> dict[str, Any]:
        """Validate all recommendations meet criteria.
        
        Returns:
            Validation report
        """
        total = len(self.relationships)
        true_fk_only = sum(1 for r in self.relationships 
                          if r.get("relationship_class") == "TRUE_FK")
        high_confidence = sum(1 for r in self.relationships 
                             if r.get("relationship_class") == "TRUE_FK" 
                             and r.get("confidence", 0) >= self.MIN_CONFIDENCE)
        high_containment = sum(1 for r in self.relationships 
                              if r.get("relationship_class") == "TRUE_FK" 
                              and r.get("containment_ratio", 0) >= self.MIN_CONTAINMENT)
        
        return {
            "total_relationships": total,
            "true_fk_count": true_fk_only,
            "high_confidence_count": high_confidence,
            "high_containment_count": high_containment,
            "recommendations_count": len(self.recommend_joins()),
            "rejection_reasons": {
                "not_true_fk": total - true_fk_only,
                "low_confidence": true_fk_only - high_confidence,
                "low_containment": high_confidence - high_containment
            }
        }


def reject_semantic_joins(relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter out semantic-only joins (not TRUE_FK).
    
    Args:
        relationships: List of relationships
        
    Returns:
        Filtered list with only TRUE_FK relationships
    """
    return [
        r for r in relationships
        if r.get("relationship_class") == "TRUE_FK"
        and r.get("containment_ratio", 0.0) >= 0.9
    ]


def validate_pk_presence(relationships: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Validate that target columns are actual PKs.
    
    Args:
        relationships: List of relationships
        
    Returns:
        Dictionary mapping tables to their PK columns
    """
    pk_map: dict[str, list[str]] = {}
    
    for rel in relationships:
        if rel.get("relationship_class") != "TRUE_FK":
            continue
        
        target_table = rel.get("target_table", "")
        target_column = rel.get("target_column", "")
        
        if target_table not in pk_map:
            pk_map[target_table] = []
        
        if target_column not in pk_map[target_table]:
            pk_map[target_table].append(target_column)
    
    return pk_map
