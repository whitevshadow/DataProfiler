"""Session state management for NeuLeap Data Profiler.

Tracks pipeline execution state across agent sessions to avoid redundant work.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class SessionState:
    """Persistent state for profiling session."""
    
    # Session ID
    session_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    
    # Dataset paths
    dataset_path: str | None = None
    output_base: str | None = None
    
    # Artifact paths (completed stages)
    profile_path: str | None = None
    quality_path: str | None = None
    pk_path: str | None = None
    relationship_path: str | None = None
    enrichment_path: str | None = None
    description_path: str | None = None
    canonical_path: str | None = None
    dbml_path: str | None = None  # Path to schema.dbml for embedded viewer
    
    # Pipeline metrics
    tables: int = 0
    rows: int = 0
    columns: int = 0
    fk_count: int = 0
    quality_score: float = 0.0
    
    # Current context
    current_entity: str | None = None  # Current table being viewed
    current_selection: list[str] = field(default_factory=list)  # Selected columns/tables
    last_command: str | None = None
    
    # Stage completion flags
    profile_complete: bool = False
    quality_complete: bool = False
    pk_complete: bool = False
    relationship_complete: bool = False
    enrichment_complete: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
    
    def has_profiles(self) -> bool:
        """Check if profiles are available."""
        return self.profile_complete and self.profile_path is not None
    
    def has_relationships(self) -> bool:
        """Check if relationships are available."""
        return self.relationship_complete and self.relationship_path is not None
    
    def has_enrichment(self) -> bool:
        """Check if enrichment is available."""
        return self.enrichment_complete and self.enrichment_path is not None
    
    def mark_profile_complete(self, profile_path: str, tables: int, rows: int, columns: int) -> None:
        """Mark profiling stage complete."""
        self.profile_complete = True
        self.profile_path = profile_path
        self.tables = tables
        self.rows = rows
        self.columns = columns
        self.updated_at = datetime.now().isoformat()
    
    def mark_relationship_complete(self, relationship_path: str, fk_count: int) -> None:
        """Mark relationship detection stage complete."""
        self.relationship_complete = True
        self.relationship_path = relationship_path
        self.fk_count = fk_count
        self.updated_at = datetime.now().isoformat()
    
    def mark_enrichment_complete(self, enrichment_path: str) -> None:
        """Mark enrichment stage complete."""
        self.enrichment_complete = True
        self.enrichment_path = enrichment_path
        self.updated_at = datetime.now().isoformat()
    
    def mark_quality_complete(self, quality_path: str, quality_score: float) -> None:
        """Mark quality stage complete."""
        self.quality_complete = True
        self.quality_path = quality_path
        self.quality_score = quality_score
        self.updated_at = datetime.now().isoformat()
    
    def mark_pk_complete(self, pk_path: str) -> None:
        """Mark PK detection stage complete."""
        self.pk_complete = True
        self.pk_path = pk_path
        self.updated_at = datetime.now().isoformat()


class SessionStateManager:
    """Manages session state persistence."""
    
    def __init__(self, state_file: Path | None = None):
        """Initialize session state manager.
        
        Args:
            state_file: Path to session state JSON file (default: output/session_state.json)
        """
        self.state_file = state_file or Path("output/session/session_state.json")
        self.current_state: SessionState | None = None
    
    def load_or_create(self, session_id: str | None = None) -> SessionState:
        """Load existing session state or create new one.
        
        Args:
            session_id: Optional session ID to load specific session
            
        Returns:
            SessionState instance
        """
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                self.current_state = SessionState.from_dict(data)
                return self.current_state
            except Exception as e:
                print(f"Warning: Could not load session state: {e}")
        
        # Create new session
        session_id = session_id or self._generate_session_id()
        now = datetime.now().isoformat()
        self.current_state = SessionState(
            session_id=session_id,
            created_at=now,
            updated_at=now
        )
        return self.current_state
    
    def save(self, state: SessionState | None = None) -> None:
        """Save session state to disk.
        
        Args:
            state: SessionState to save (default: current_state)
        """
        state = state or self.current_state
        if state is None:
            return
        
        # Ensure directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Save to disk
        self.state_file.write_text(
            json.dumps(state.to_dict(), indent=2),
            encoding="utf-8"
        )
    
    def get_current(self) -> SessionState:
        """Get current session state.
        
        Returns:
            Current SessionState instance
        """
        if self.current_state is None:
            self.current_state = self.load_or_create()
        return self.current_state
    
    def clear(self) -> None:
        """Clear current session state."""
        self.current_state = None
        if self.state_file.exists():
            self.state_file.unlink()
    
    def _generate_session_id(self) -> str:
        """Generate new session ID."""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def update_from_profile_result(self, result: dict[str, Any]) -> None:
        """Update session state from profile result.
        
        Args:
            result: Profile result dictionary
        """
        state = self.get_current()
        
        if "profile_path" in result:
            tables = result.get("tables_profiled", 0)
            rows = result.get("total_rows", 0)
            columns = result.get("total_columns", 0)
            state.mark_profile_complete(
                profile_path=result["profile_path"],
                tables=tables,
                rows=rows,
                columns=columns
            )
        
        if "output_base" in result:
            state.output_base = result["output_base"]
        
        self.save(state)
    
    def update_from_relationship_result(self, result: dict[str, Any]) -> None:
        """Update session state from relationship detection result.
        
        Args:
            result: Relationship detection result dictionary
        """
        state = self.get_current()
        
        if "relationships_path" in result:
            fk_count = result.get("true_fk_count", 0)
            state.mark_relationship_complete(
                relationship_path=result["relationships_path"],
                fk_count=fk_count
            )
        
        self.save(state)
    
    def update_from_enrichment_result(self, result: dict[str, Any]) -> None:
        """Update session state from enrichment result.
        
        Args:
            result: Enrichment result dictionary
        """
        state = self.get_current()
        
        if "descriptions_path" in result:
            state.mark_enrichment_complete(enrichment_path=result["descriptions_path"])
        
        self.save(state)
