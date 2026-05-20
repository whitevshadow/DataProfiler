"""Agent context for maintaining conversation and execution state.

Tracks current execution context, selected entities, and conversation flow.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """Current agent execution context."""
    
    # Current selection/focus
    current_entity: str | None = None  # Current table being viewed
    selected_node: str | None = None  # Selected node in tree/graph
    selected_columns: list[str] = field(default_factory=list)
    
    # Last executed commands
    last_command: str | None = None
    last_tool: str | None = None
    last_intent: str | None = None
    
    # Current view state
    current_view: str = "chat"  # chat, er, dbml, tree, chart
    view_params: dict[str, Any] = field(default_factory=dict)
    
    # Execution mode
    auto_execute: bool = True  # Auto-execute high-confidence intents
    confirmation_required: bool = False  # Waiting for user confirmation
    pending_action: dict[str, Any] | None = None  # Action awaiting confirmation
    
    # Filter state
    active_filters: dict[str, Any] = field(default_factory=dict)
    
    # Session metadata
    session_id: str | None = None
    workspace_path: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentContext:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
    
    def update_selection(self, entity: str | None = None, node: str | None = None) -> None:
        """Update current selection.
        
        Args:
            entity: Entity name (table)
            node: Node ID in tree/graph
        """
        if entity is not None:
            self.current_entity = entity
        if node is not None:
            self.selected_node = node
    
    def clear_selection(self) -> None:
        """Clear current selection."""
        self.current_entity = None
        self.selected_node = None
        self.selected_columns = []
    
    def update_view(self, view: str, params: dict[str, Any] | None = None) -> None:
        """Update current view.
        
        Args:
            view: View name (chat, er, dbml, tree, chart)
            params: Optional view parameters
        """
        self.current_view = view
        if params:
            self.view_params = params
    
    def set_pending_action(self, action: dict[str, Any]) -> None:
        """Set an action that requires confirmation.
        
        Args:
            action: Action details
        """
        self.confirmation_required = True
        self.pending_action = action
    
    def confirm_action(self) -> dict[str, Any] | None:
        """Confirm and retrieve pending action.
        
        Returns:
            Pending action or None
        """
        action = self.pending_action
        self.confirmation_required = False
        self.pending_action = None
        return action
    
    def cancel_action(self) -> None:
        """Cancel pending action."""
        self.confirmation_required = False
        self.pending_action = None
    
    def add_filter(self, filter_name: str, filter_value: Any) -> None:
        """Add a filter.
        
        Args:
            filter_name: Filter name
            filter_value: Filter value
        """
        self.active_filters[filter_name] = filter_value
    
    def remove_filter(self, filter_name: str) -> None:
        """Remove a filter.
        
        Args:
            filter_name: Filter name
        """
        self.active_filters.pop(filter_name, None)
    
    def clear_filters(self) -> None:
        """Clear all filters."""
        self.active_filters = {}
    
    def get_summary(self) -> dict[str, Any]:
        """Get context summary.
        
        Returns:
            Dictionary with context summary
        """
        return {
            "current_entity": self.current_entity,
            "selected_node": self.selected_node,
            "last_command": self.last_command,
            "last_tool": self.last_tool,
            "current_view": self.current_view,
            "pending_confirmation": self.confirmation_required,
            "active_filters": len(self.active_filters),
        }


class ContextManager:
    """Manages agent context across conversation turns."""
    
    def __init__(self):
        """Initialize context manager."""
        self.context = AgentContext()
        self._history: list[dict[str, Any]] = []
    
    def get_context(self) -> AgentContext:
        """Get current context.
        
        Returns:
            AgentContext instance
        """
        return self.context
    
    def update_context(self, **kwargs: Any) -> None:
        """Update context fields.
        
        Args:
            **kwargs: Fields to update
        """
        for key, value in kwargs.items():
            if hasattr(self.context, key):
                setattr(self.context, key, value)
        
        # Save to history
        self._history.append({
            "timestamp": self._get_timestamp(),
            "update": kwargs,
        })
    
    def reset_context(self) -> None:
        """Reset context to default state."""
        self.context = AgentContext()
        self._history = []
    
    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get context update history.
        
        Args:
            limit: Maximum number of entries
            
        Returns:
            List of history entries
        """
        return self._history[-limit:]
    
    def _get_timestamp(self) -> str:
        """Get current timestamp.
        
        Returns:
            ISO timestamp string
        """
        from datetime import datetime
        return datetime.now().isoformat()
