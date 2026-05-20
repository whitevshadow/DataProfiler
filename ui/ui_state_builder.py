"""UI state builder for frontend counters and status display.

Generates ui_state.json with real-time metrics for frontend display.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class UIState:
    """UI state data for frontend counters."""
    
    # Counters
    tables: int = 0
    rows: int = 0
    columns: int = 0
    fk_count: int = 0
    descriptions: int = 0
    
    # Scores
    quality_score: float = 0.0
    
    # Stage completion
    profile_complete: bool = False
    quality_complete: bool = False
    pk_complete: bool = False
    relationship_complete: bool = False
    enrichment_complete: bool = False
    
    # Status message
    status: str = "Ready"
    last_updated: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UIState:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class UIStateBuilder:
    """Builds and emits UI state events for frontend consumption."""
    
    def __init__(self, output_path: Path | None = None):
        """Initialize UI state builder.
        
        Args:
            output_path: Path to ui_state.json (default: output/ui/ui_state.json)
        """
        self.output_path = output_path or Path("output/ui/ui_state.json")
        self.current_state = UIState()
    
    def load(self) -> UIState:
        """Load current UI state from disk."""
        if self.output_path.exists():
            try:
                data = json.loads(self.output_path.read_text(encoding="utf-8"))
                self.current_state = UIState.from_dict(data)
                return self.current_state
            except Exception:
                pass
        return self.current_state
    
    def save(self) -> None:
        """Save UI state to disk."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(self.current_state.to_dict(), indent=2),
            encoding="utf-8"
        )
    
    def emit_profile_complete(
        self,
        tables: int,
        rows: int,
        columns: int,
        status: str = "Profile complete"
    ) -> None:
        """Emit PROFILE_COMPLETE event.
        
        Args:
            tables: Number of tables profiled
            rows: Total row count
            columns: Total column count
            status: Status message
        """
        from datetime import datetime
        
        self.current_state.tables = tables
        self.current_state.rows = rows
        self.current_state.columns = columns
        self.current_state.profile_complete = True
        self.current_state.status = status
        self.current_state.last_updated = datetime.now().isoformat()
        
        self.save()
    
    def emit_quality_complete(
        self,
        quality_score: float,
        status: str = "Quality assessment complete"
    ) -> None:
        """Emit QUALITY_COMPLETE event.
        
        Args:
            quality_score: Overall quality score (0.0-1.0)
            status: Status message
        """
        from datetime import datetime
        
        self.current_state.quality_score = quality_score
        self.current_state.quality_complete = True
        self.current_state.status = status
        self.current_state.last_updated = datetime.now().isoformat()
        
        self.save()
    
    def emit_pk_complete(
        self,
        status: str = "Primary key detection complete"
    ) -> None:
        """Emit PK_COMPLETE event.
        
        Args:
            status: Status message
        """
        from datetime import datetime
        
        self.current_state.pk_complete = True
        self.current_state.status = status
        self.current_state.last_updated = datetime.now().isoformat()
        
        self.save()
    
    def emit_relationship_complete(
        self,
        fk_count: int,
        status: str = "Relationship detection complete"
    ) -> None:
        """Emit RELATIONSHIP_COMPLETE event.
        
        Args:
            fk_count: Number of FK relationships detected
            status: Status message
        """
        from datetime import datetime
        
        self.current_state.fk_count = fk_count
        self.current_state.relationship_complete = True
        self.current_state.status = status
        self.current_state.last_updated = datetime.now().isoformat()
        
        self.save()
    
    def emit_enrichment_complete(
        self,
        descriptions: int,
        status: str = "Enrichment complete"
    ) -> None:
        """Emit ENRICHMENT_COMPLETE event.
        
        Args:
            descriptions: Number of descriptions generated
            status: Status message
        """
        from datetime import datetime
        
        self.current_state.descriptions = descriptions
        self.current_state.enrichment_complete = True
        self.current_state.status = status
        self.current_state.last_updated = datetime.now().isoformat()
        
        self.save()
    
    def get_current(self) -> UIState:
        """Get current UI state.
        
        Returns:
            Current UIState instance
        """
        return self.current_state
    
    def clear(self) -> None:
        """Clear UI state."""
        self.current_state = UIState()
        self.save()


def build_ui_state_from_outputs(output_base: Path) -> UIState:
    """Build UI state by reading output artifacts.
    
    Args:
        output_base: Base output directory (e.g. output/)
        
    Returns:
        UIState with metrics extracted from artifacts
    """
    state = UIState()
    
    # Read profile data
    profile_file = output_base / "profiles" / "profile.json"
    if profile_file.exists():
        try:
            profile_data = json.loads(profile_file.read_text(encoding="utf-8"))
            if isinstance(profile_data, dict):
                state.tables = profile_data.get("tables", 0)
                state.rows = sum(t.get("metadata", {}).get("row_count_estimate", 0) 
                               for t in profile_data.get("tables", []))
                state.columns = sum(len(t.get("columns", [])) 
                                   for t in profile_data.get("tables", []))
                state.profile_complete = True
        except Exception:
            pass
    
    # Read relationship data
    relationship_file = output_base / "relationships" / "relationships.json"
    if relationship_file.exists():
        try:
            rel_data = json.loads(relationship_file.read_text(encoding="utf-8"))
            if isinstance(rel_data, dict):
                relationships = rel_data.get("relationships", [])
                state.fk_count = sum(1 for r in relationships 
                                    if r.get("relationship_class") == "TRUE_FK")
                state.relationship_complete = True
        except Exception:
            pass
    
    # Read description data
    description_file = output_base / "descriptions" / "descriptions.json"
    if description_file.exists():
        try:
            desc_data = json.loads(description_file.read_text(encoding="utf-8"))
            if isinstance(desc_data, list):
                state.descriptions = sum(len(t.get("columns", [])) for t in desc_data)
            elif isinstance(desc_data, dict):
                state.descriptions = sum(len(t.get("columns", [])) 
                                        for t in desc_data.get("tables", []))
            state.enrichment_complete = True
        except Exception:
            pass
    
    # Read quality data
    quality_file = output_base / "quality" / "quality_report.json"
    if quality_file.exists():
        try:
            quality_data = json.loads(quality_file.read_text(encoding="utf-8"))
            if isinstance(quality_data, dict):
                state.quality_score = quality_data.get("overall_score", 0.0)
                state.quality_complete = True
        except Exception:
            pass
    
    return state
