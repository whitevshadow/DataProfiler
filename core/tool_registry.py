"""Tool registry for NeuLeap profiler MCP tools.

Central registry mapping tool names to implementations with metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolMetadata:
    """Metadata for a tool."""
    
    name: str
    description: str
    category: str  # PROFILE, QUALITY, PK, RELATIONSHIP, etc.
    parameters: dict[str, Any] = field(default_factory=dict)
    returns: str = "JSON response"
    requires_session: bool = False
    modifies_state: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.parameters,
            "returns": self.returns,
            "requires_session": self.requires_session,
            "modifies_state": self.modifies_state,
        }


class ToolRegistry:
    """Central registry for all profiler tools."""
    
    def __init__(self):
        """Initialize tool registry."""
        self.tools: dict[str, ToolMetadata] = {}
        self._register_standard_tools()
    
    def _register_standard_tools(self) -> None:
        """Register standard profiler tools."""
        
        # PROFILE category
        self.register(ToolMetadata(
            name="profile_file",
            description="Profile a single data file",
            category="PROFILE",
            parameters={"path": "str", "sample_size": "int", "output_base": "str"},
            modifies_state=True,
        ))
        
        self.register(ToolMetadata(
            name="profile_directory",
            description="Profile all files in a directory",
            category="PROFILE",
            parameters={"path": "str", "sample_size": "int", "output_base": "str"},
            modifies_state=True,
        ))
        
        self.register(ToolMetadata(
            name="list_profiles",
            description="List all profiled tables",
            category="PROFILE",
            requires_session=True,
        ))
        
        self.register(ToolMetadata(
            name="get_profile_summary",
            description="Get profile summary for a table",
            category="PROFILE",
            parameters={"table_name": "str"},
            requires_session=True,
        ))
        
        # QUALITY category
        self.register(ToolMetadata(
            name="get_quality",
            description="Get quality metrics for tables",
            category="QUALITY",
            parameters={"table_name": "str | None"},
            requires_session=True,
        ))
        
        self.register(ToolMetadata(
            name="show_quality_issues",
            description="Show data quality issues",
            category="QUALITY",
            requires_session=True,
        ))
        
        # PK category
        self.register(ToolMetadata(
            name="get_pk_summary",
            description="Get primary key candidates",
            category="PK",
            parameters={"table_name": "str | None"},
            requires_session=True,
        ))
        
        # RELATIONSHIP category
        self.register(ToolMetadata(
            name="detect_relationships",
            description="Detect relationships between tables",
            category="RELATIONSHIP",
            parameters={"output_base": "str"},
            modifies_state=True,
        ))
        
        self.register(ToolMetadata(
            name="get_table_relationships",
            description="Get relationships for a table",
            category="RELATIONSHIP",
            parameters={"table_name": "str | None", "relationship_class": "str | None"},
            requires_session=True,
        ))
        
        self.register(ToolMetadata(
            name="get_relationship_detail",
            description="Get detailed relationship information",
            category="RELATIONSHIP",
            parameters={"edge_id": "str"},
            requires_session=True,
        ))
        
        # ENRICHMENT category
        self.register(ToolMetadata(
            name="enrich_descriptions",
            description="Generate semantic descriptions for columns",
            category="ENRICHMENT",
            parameters={"output_base": "str", "max_workers": "int"},
            modifies_state=True,
        ))
        
        self.register(ToolMetadata(
            name="get_descriptions",
            description="Get column descriptions",
            category="ENRICHMENT",
            parameters={"table_name": "str | None"},
            requires_session=True,
        ))
        
        # LCIL category
        self.register(ToolMetadata(
            name="get_low_cardinality",
            description="Get low cardinality columns",
            category="LCIL",
            parameters={"table_name": "str | None"},
            requires_session=True,
        ))
        
        # VISUALIZATION category
        self.register(ToolMetadata(
            name="generate_erd",
            description="Generate ER diagram",
            category="VISUALIZATION",
            parameters={"output_base": "str"},
            modifies_state=True,
        ))
        
        self.register(ToolMetadata(
            name="generate_dbml_schema",
            description="Generate DBML schema",
            category="VISUALIZATION",
            parameters={"output_base": "str"},
            modifies_state=True,
        ))
        
        self.register(ToolMetadata(
            name="generate_er_visualizations",
            description="Generate ER charts and visualizations",
            category="VISUALIZATION",
            parameters={"output_base": "str"},
            modifies_state=True,
        ))
        
        # SESSION category
        self.register(ToolMetadata(
            name="get_session_status",
            description="Get current session status",
            category="SESSION",
            requires_session=True,
        ))
        
        self.register(ToolMetadata(
            name="list_sessions",
            description="List all sessions",
            category="SESSION",
        ))
        
        # SEARCH category
        self.register(ToolMetadata(
            name="search_tables",
            description="Search for tables by name",
            category="SEARCH",
            parameters={"query": "str"},
            requires_session=True,
        ))
        
        self.register(ToolMetadata(
            name="search_columns",
            description="Search for columns by name",
            category="SEARCH",
            parameters={"query": "str"},
            requires_session=True,
        ))
    
    def register(self, tool: ToolMetadata) -> None:
        """Register a tool.
        
        Args:
            tool: ToolMetadata to register
        """
        self.tools[tool.name] = tool
    
    def get(self, tool_name: str) -> ToolMetadata | None:
        """Get tool metadata.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            ToolMetadata or None if not found
        """
        return self.tools.get(tool_name)
    
    def list_by_category(self, category: str) -> list[ToolMetadata]:
        """List tools by category.
        
        Args:
            category: Tool category
            
        Returns:
            List of ToolMetadata
        """
        return [tool for tool in self.tools.values() if tool.category == category]
    
    def list_all(self) -> list[ToolMetadata]:
        """List all registered tools.
        
        Returns:
            List of all ToolMetadata
        """
        return list(self.tools.values())
    
    def get_categories(self) -> list[str]:
        """Get all tool categories.
        
        Returns:
            List of unique categories
        """
        return sorted(set(tool.category for tool in self.tools.values()))
    
    def search(self, query: str) -> list[ToolMetadata]:
        """Search tools by name or description.
        
        Args:
            query: Search query
            
        Returns:
            List of matching ToolMetadata
        """
        query_lower = query.lower()
        matches = []
        
        for tool in self.tools.values():
            if (query_lower in tool.name.lower() or 
                query_lower in tool.description.lower() or
                query_lower in tool.category.lower()):
                matches.append(tool)
        
        return matches
    
    def validate_parameters(
        self,
        tool_name: str,
        params: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Validate parameters for a tool.
        
        Args:
            tool_name: Name of the tool
            params: Parameters to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        tool = self.get(tool_name)
        
        if tool is None:
            return False, f"Tool not found: {tool_name}"
        
        # Check required parameters
        for param_name, param_type in tool.parameters.items():
            if param_name not in params:
                # Check if it's optional (has default)
                if " | None" in param_type or "Optional" in param_type:
                    continue
                return False, f"Missing required parameter: {param_name}"
        
        return True, None


# Global tool registry instance
_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance.
    
    Returns:
        ToolRegistry instance
    """
    return _registry
