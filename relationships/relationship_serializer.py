"""
Relationship Serializer

Handles serialization of RelationshipReport to JSON format.

Output Format:
    RelationshipReport.json
    
    Contains:
    - Detected relationships with evidence
    - Validation results
    - Execution metadata
    - Summary statistics
"""

import json
from typing import Dict, Any
from datetime import datetime
from relationships.relationship_models import RelationshipReport


class RelationshipSerializer:
    """Serializes RelationshipReport to JSON format."""
    
    def __init__(self, indent: int = 2):
        """
        Initialize serializer.
        
        Args:
            indent: JSON indentation level
        """
        self.indent = indent
    
    def serialize(self, report: RelationshipReport) -> str:
        """
        Serialize RelationshipReport to JSON string.
        
        Args:
            report: RelationshipReport to serialize
        
        Returns:
            JSON string
        """
        report_dict = report.to_dict()
        return json.dumps(report_dict, indent=self.indent, ensure_ascii=False)
    
    def save_to_file(self, report: RelationshipReport, filepath: str) -> None:
        """
        Save RelationshipReport to JSON file.
        
        Args:
            report: RelationshipReport to save
            filepath: Output file path
        """
        json_str = self.serialize(report)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json_str)
    
    def deserialize(self, json_str: str) -> Dict[str, Any]:
        """
        Deserialize JSON string to dict.
        
        Args:
            json_str: JSON string
        
        Returns:
            Deserialized dict
        """
        return json.loads(json_str)
    
    def load_from_file(self, filepath: str) -> Dict[str, Any]:
        """
        Load RelationshipReport from JSON file.
        
        Args:
            filepath: Input file path
        
        Returns:
            Deserialized relationship report as dict
        """
        with open(filepath, "r", encoding="utf-8") as f:
            return self.deserialize(f.read())


# Singleton instance
_serializer = RelationshipSerializer()


def serialize_relationship_report(report: RelationshipReport) -> str:
    """Convenience function to serialize report."""
    return _serializer.serialize(report)


def save_relationship_report(report: RelationshipReport, filepath: str) -> None:
    """Convenience function to save report to file."""
    _serializer.save_to_file(report, filepath)
