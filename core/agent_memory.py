"""Agent memory for persisting conversation history and learned patterns.

Maintains short-term and long-term memory for the agent.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class MemoryEntry:
    """Single memory entry."""
    
    timestamp: str
    entry_type: str  # user_query, tool_call, tool_result, agent_response
    content: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class AgentMemory:
    """Agent memory system with short-term and long-term storage."""
    
    def __init__(
        self,
        memory_dir: Path | None = None,
        short_term_limit: int = 100
    ):
        """Initialize agent memory.
        
        Args:
            memory_dir: Directory for persistent memory (default: output/memory/)
            short_term_limit: Maximum short-term memory entries
        """
        self.memory_dir = memory_dir or Path("output/memory")
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # Short-term memory (in-memory)
        self.short_term: deque[MemoryEntry] = deque(maxlen=short_term_limit)
        
        # Long-term memory file
        self.long_term_file = self.memory_dir / "long_term_memory.jsonl"
        
        # Learned patterns
        self.patterns: dict[str, int] = {}  # Pattern -> frequency
        self.patterns_file = self.memory_dir / "learned_patterns.json"
        self._load_patterns()
    
    def add(
        self,
        entry_type: str,
        content: dict[str, Any],
        metadata: dict[str, Any] | None = None
    ) -> MemoryEntry:
        """Add a memory entry.
        
        Args:
            entry_type: Type of entry
            content: Entry content
            metadata: Optional metadata
            
        Returns:
            Created MemoryEntry
        """
        entry = MemoryEntry(
            timestamp=datetime.now().isoformat(),
            entry_type=entry_type,
            content=content,
            metadata=metadata or {},
        )
        
        # Add to short-term memory
        self.short_term.append(entry)
        
        # Persist to long-term memory
        self._append_to_long_term(entry)
        
        return entry
    
    def add_user_query(self, query: str, intent: str | None = None) -> MemoryEntry:
        """Add a user query to memory.
        
        Args:
            query: User query text
            intent: Detected intent
            
        Returns:
            Created MemoryEntry
        """
        return self.add(
            entry_type="user_query",
            content={"query": query},
            metadata={"intent": intent} if intent else {}
        )
    
    def add_tool_call(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        result: dict[str, Any] | None = None
    ) -> MemoryEntry:
        """Add a tool call to memory.
        
        Args:
            tool_name: Name of the tool
            parameters: Tool parameters
            result: Tool result
            
        Returns:
            Created MemoryEntry
        """
        return self.add(
            entry_type="tool_call",
            content={
                "tool_name": tool_name,
                "parameters": parameters,
                "result": result,
            }
        )
    
    def add_agent_response(self, response: str, metadata: dict[str, Any] | None = None) -> MemoryEntry:
        """Add an agent response to memory.
        
        Args:
            response: Agent response text
            metadata: Optional metadata
            
        Returns:
            Created MemoryEntry
        """
        return self.add(
            entry_type="agent_response",
            content={"response": response},
            metadata=metadata or {}
        )
    
    def get_recent(self, limit: int = 10, entry_type: str | None = None) -> list[MemoryEntry]:
        """Get recent memory entries.
        
        Args:
            limit: Maximum number of entries
            entry_type: Optional filter by entry type
            
        Returns:
            List of recent MemoryEntry objects
        """
        entries = list(self.short_term)
        
        if entry_type:
            entries = [e for e in entries if e.entry_type == entry_type]
        
        return entries[-limit:]
    
    def get_conversation_context(self, turns: int = 5) -> list[dict[str, Any]]:
        """Get recent conversation context.
        
        Args:
            turns: Number of conversation turns
            
        Returns:
            List of conversation turns
        """
        recent = self.get_recent(limit=turns * 2)  # Assuming ~2 entries per turn
        
        context = []
        for entry in recent:
            if entry.entry_type in ("user_query", "agent_response"):
                context.append({
                    "role": "user" if entry.entry_type == "user_query" else "assistant",
                    "content": entry.content.get("query") or entry.content.get("response"),
                    "timestamp": entry.timestamp,
                })
        
        return context
    
    def learn_pattern(self, pattern: str) -> None:
        """Learn a user pattern.
        
        Args:
            pattern: Pattern to learn
        """
        self.patterns[pattern] = self.patterns.get(pattern, 0) + 1
        self._save_patterns()
    
    def get_pattern_frequency(self, pattern: str) -> int:
        """Get frequency of a learned pattern.
        
        Args:
            pattern: Pattern to check
            
        Returns:
            Frequency count
        """
        return self.patterns.get(pattern, 0)
    
    def get_top_patterns(self, limit: int = 10) -> list[tuple[str, int]]:
        """Get most frequent patterns.
        
        Args:
            limit: Maximum number of patterns
            
        Returns:
            List of (pattern, frequency) tuples
        """
        sorted_patterns = sorted(
            self.patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_patterns[:limit]
    
    def clear_short_term(self) -> None:
        """Clear short-term memory."""
        self.short_term.clear()
    
    def _append_to_long_term(self, entry: MemoryEntry) -> None:
        """Append entry to long-term memory file.
        
        Args:
            entry: MemoryEntry to append
        """
        with open(self.long_term_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry.to_dict()) + '\n')
    
    def _load_patterns(self) -> None:
        """Load learned patterns from disk."""
        if self.patterns_file.exists():
            try:
                self.patterns = json.loads(
                    self.patterns_file.read_text(encoding='utf-8')
                )
            except Exception:
                self.patterns = {}
    
    def _save_patterns(self) -> None:
        """Save learned patterns to disk."""
        self.patterns_file.write_text(
            json.dumps(self.patterns, indent=2),
            encoding='utf-8'
        )
    
    def search_memory(
        self,
        query: str,
        entry_type: str | None = None,
        limit: int = 20
    ) -> list[MemoryEntry]:
        """Search memory entries.
        
        Args:
            query: Search query
            entry_type: Optional filter by entry type
            limit: Maximum results
            
        Returns:
            List of matching MemoryEntry objects
        """
        query_lower = query.lower()
        matches = []
        
        for entry in self.short_term:
            if entry_type and entry.entry_type != entry_type:
                continue
            
            # Search in content
            content_str = json.dumps(entry.content).lower()
            if query_lower in content_str:
                matches.append(entry)
            
            if len(matches) >= limit:
                break
        
        return matches
    
    def get_statistics(self) -> dict[str, Any]:
        """Get memory statistics.
        
        Returns:
            Dictionary with memory statistics
        """
        entry_types = {}
        for entry in self.short_term:
            entry_types[entry.entry_type] = entry_types.get(entry.entry_type, 0) + 1
        
        return {
            "short_term_count": len(self.short_term),
            "short_term_capacity": self.short_term.maxlen,
            "entry_types": entry_types,
            "learned_patterns": len(self.patterns),
            "top_pattern": max(self.patterns.items(), key=lambda x: x[1]) if self.patterns else None,
        }
