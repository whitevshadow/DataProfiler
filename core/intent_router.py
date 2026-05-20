"""Intent router for NeuLeap Data Profiler.

Routes user queries to appropriate tool calls with confidence scoring.
Prevents incorrect tool routing (e.g. "show profiles" -> relationship tools).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import re


class Intent(str, Enum):
    """Supported user intents."""
    
    # Data discovery
    LIST_FILES = "list_files"
    LIST_TABLES = "list_tables"
    
    # Profiling
    PROFILE_FILE = "profile_file"
    PROFILE_DIRECTORY = "profile_directory"
    GET_PROFILE = "get_profile"
    GET_PROFILE_SUMMARY = "get_profile_summary"
    
    # Quality
    GET_QUALITY = "get_quality"
    SHOW_QUALITY_ISSUES = "show_quality_issues"
    
    # Primary keys
    GET_PK = "get_pk"
    SHOW_PK_SUMMARY = "show_pk_summary"
    
    # Relationships
    DETECT_RELATIONSHIPS = "detect_relationships"
    GET_RELATIONSHIPS = "get_relationships"
    SHOW_RELATIONSHIPS = "show_relationships"
    GET_RELATIONSHIP_DETAIL = "get_relationship_detail"
    
    # LCIL (Low Cardinality)
    GET_LCIL = "get_lcil"
    SHOW_LCIL_SUMMARY = "show_lcil_summary"
    
    # Enrichment (semantic only)
    ENRICH_DESCRIPTIONS = "enrich_descriptions"
    GET_DESCRIPTIONS = "get_descriptions"
    
    # Visualization
    GENERATE_DBML = "generate_dbml"
    GENERATE_ERD = "generate_erd"
    GENERATE_CHARTS = "generate_charts"
    VIEW_DBML = "view_dbml"  # Display existing DBML without regeneration
    
    # Session management
    SHOW_STATUS = "show_status"
    SHOW_SESSION = "show_session"
    
    # Conversation
    CONVERSATION = "conversation"
    UNKNOWN = "unknown"


@dataclass
class IntentMatch:
    """Intent classification result with confidence."""
    
    intent: Intent
    confidence: float  # 0.0 to 1.0
    extracted_params: dict[str, Any]
    
    def needs_clarification(self, threshold: float = 0.7) -> bool:
        """Return True if confidence is below threshold."""
        return self.confidence < threshold


class IntentRouter:
    """Routes user input to appropriate tools based on intent classification."""
    
    # Intent patterns with keyword matching
    INTENT_PATTERNS = {
        # Profiling intents
        Intent.PROFILE_FILE: [
            r'\bprofile\s+(?:the\s+)?file\b',
            r'\bprofile\s+.*\.csv\b',
            r'\banalyze\s+(?:the\s+)?file\b',
        ],
        Intent.PROFILE_DIRECTORY: [
            r'\bprofile\s+(?:all\s+)?(?:files|directory|folder|data)\b',
            r'\bprofile\s+everything\b',
            r'\bscan\s+(?:all\s+)?(?:files|data)\b',
        ],
        Intent.GET_PROFILE: [
            r'\bshow\s+(?:me\s+)?(?:the\s+)?profiles?\b',
            r'\blist\s+profiles?\b',
            r'\bget\s+profiles?\b',
            r'\bview\s+profiles?\b',
        ],
        Intent.GET_PROFILE_SUMMARY: [
            r'\bprofile\s+summary\b',
            r'\bsummarize\s+profiles?\b',
        ],
        
        # Quality intents
        Intent.GET_QUALITY: [
            r'\bshow\s+(?:me\s+)?quality\b',
            r'\bget\s+quality\b',
            r'\bquality\s+(?:report|metrics|scores?)\b',
        ],
        Intent.SHOW_QUALITY_ISSUES: [
            r'\bshow\s+(?:me\s+)?(?:quality\s+)?issues\b',
            r'\bwhat(?:\'s|\s+is)\s+wrong\b',
            r'\bproblems?\b',
        ],
        
        # PK intents
        Intent.GET_PK: [
            r'\bshow\s+(?:me\s+)?(?:primary\s+)?keys?\b',
            r'\bget\s+(?:primary\s+)?keys?\b',
            r'\blist\s+(?:primary\s+)?keys?\b',
            r'\bpk\s+candidates?\b',
        ],
        Intent.SHOW_PK_SUMMARY: [
            r'\bpk\s+summary\b',
            r'\bprimary\s+key\s+summary\b',
        ],
        
        # Relationship intents
        Intent.DETECT_RELATIONSHIPS: [
            r'\bdetect\s+relationships?\b',
            r'\bfind\s+(?:foreign\s+)?keys?\b',
            r'\bdiscover\s+relationships?\b',
        ],
        Intent.GET_RELATIONSHIPS: [
            r'\bshow\s+(?:me\s+)?relationships?\b',
            r'\blist\s+relationships?\b',
            r'\bget\s+relationships?\b',
            r'\bview\s+relationships?\b',
        ],
        Intent.SHOW_RELATIONSHIPS: [
            r'\brelationship\s+(?:summary|overview)\b',
            r'\brelationships?\s+between\b',
        ],
        
        # LCIL intents
        Intent.GET_LCIL: [
            r'\bshow\s+(?:me\s+)?(?:low\s+)?cardinality\b',
            r'\bget\s+lcil\b',
            r'\blcil\s+data\b',
        ],
        
        # Enrichment intents
        Intent.ENRICH_DESCRIPTIONS: [
            r'\benrich\b',
            r'\badd\s+descriptions?\b',
            r'\bgenerate\s+descriptions?\b',
            r'\bdescribe\s+(?:the\s+)?(?:tables?|columns?)\b',
        ],
        Intent.GET_DESCRIPTIONS: [
            r'\bshow\s+(?:me\s+)?descriptions?\b',
            r'\bget\s+descriptions?\b',
        ],
        
        # Visualization intents
        Intent.GENERATE_DBML: [
            r'\bgenerate\s+dbml\b',
            r'\bdbml\s+schema\b',
            r'\bexport\s+dbml\b',
        ],
        Intent.VIEW_DBML: [
            r'\bdisplay\s+dbml\b',
            r'\bshow\s+(?:me\s+)?(?:the\s+)?dbml\b',
            r'\bview\s+dbml\b',
            r'\bopen\s+dbml\b',
            r'\brender\s+dbml\b',
            r'\bshow\s+(?:the\s+)?schema\b',
            r'\bdisplay\s+(?:the\s+)?schema\b',
            r'\bview\s+(?:the\s+)?schema\b',
        ],
        Intent.GENERATE_ERD: [
            r'\bgenerate\s+(?:er\s+)?diagram\b',
            r'\berd\b',
            r'\ber\s+diagram\b',
            r'\bvisualize\b',
        ],
        Intent.GENERATE_CHARTS: [
            r'\bgenerate\s+charts?\b',
            r'\bshow\s+(?:me\s+)?charts?\b',
            r'\bvisualization\b',
        ],
        
        # Session intents
        Intent.SHOW_STATUS: [
            r'\bstatus\b',
            r'\bwhat(?:\'s|\s+is)\s+(?:the\s+)?(?:current\s+)?state\b',
        ],
        Intent.SHOW_SESSION: [
            r'\bshow\s+(?:me\s+)?(?:the\s+)?session\b',
            r'\bsession\s+(?:info|state|status)\b',
        ],
    }
    
    # Tool mapping for each intent
    INTENT_TO_TOOL = {
        Intent.PROFILE_FILE: "profile_file",
        Intent.PROFILE_DIRECTORY: "profile_directory",
        Intent.GET_PROFILE: "list_profiles",
        Intent.GET_PROFILE_SUMMARY: "get_profile_summary",
        
        Intent.GET_QUALITY: "get_quality",
        Intent.SHOW_QUALITY_ISSUES: "show_quality_issues",
        
        Intent.GET_PK: "get_pk_summary",
        Intent.SHOW_PK_SUMMARY: "get_pk_summary",
        
        Intent.DETECT_RELATIONSHIPS: "detect_relationships",
        Intent.GET_RELATIONSHIPS: "get_table_relationships",
        Intent.SHOW_RELATIONSHIPS: "get_table_relationships",
        Intent.GET_RELATIONSHIP_DETAIL: "get_relationship_detail",
        
        Intent.GET_LCIL: "get_low_cardinality",
        Intent.SHOW_LCIL_SUMMARY: "get_low_cardinality",
        
        Intent.ENRICH_DESCRIPTIONS: "enrich_descriptions",  # NEW: separate from relationships
        Intent.GET_DESCRIPTIONS: "get_descriptions",
        
        Intent.GENERATE_DBML: "generate_dbml_schema",
        Intent.VIEW_DBML: "display_dbml",  # NEW: view without regenerating
        Intent.GENERATE_ERD: "generate_erd",
        Intent.GENERATE_CHARTS: "generate_er_visualizations",
        
        Intent.SHOW_STATUS: "get_session_status",
        Intent.SHOW_SESSION: "get_session_status",
    }
    
    def classify_intent(self, user_input: str) -> IntentMatch:
        """Classify user input to an intent with confidence score.
        
        Args:
            user_input: Raw user query
            
        Returns:
            IntentMatch with intent, confidence, and extracted parameters
        """
        user_input_lower = user_input.lower().strip()
        
        # Try pattern matching
        best_match: tuple[Intent, float] | None = None
        
        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, user_input_lower):
                    # Calculate confidence based on pattern specificity
                    confidence = self._calculate_confidence(user_input_lower, pattern)
                    if best_match is None or confidence > best_match[1]:
                        best_match = (intent, confidence)
        
        if best_match:
            intent, confidence = best_match
            params = self._extract_params(user_input, intent)
            return IntentMatch(intent=intent, confidence=confidence, extracted_params=params)
        
        # Fallback to conversation if no pattern matches
        return IntentMatch(
            intent=Intent.CONVERSATION,
            confidence=0.5,
            extracted_params={}
        )
    
    def _calculate_confidence(self, user_input: str, pattern: str) -> float:
        """Calculate confidence score based on pattern match quality.
        
        Args:
            user_input: Normalized user input
            pattern: Regex pattern that matched
            
        Returns:
            Confidence score 0.0-1.0
        """
        match = re.search(pattern, user_input)
        if not match:
            return 0.0
        
        # Base confidence from match
        base_confidence = 0.7
        
        # Boost if match covers significant portion of input
        match_length = len(match.group(0))
        input_length = len(user_input)
        coverage = match_length / input_length if input_length > 0 else 0
        
        # Boost for specific patterns (longer = more specific)
        specificity_boost = min(0.2, len(pattern) / 200)
        
        return min(1.0, base_confidence + (coverage * 0.2) + specificity_boost)
    
    def _extract_params(self, user_input: str, intent: Intent) -> dict[str, Any]:
        """Extract parameters from user input based on intent.
        
        Args:
            user_input: Raw user input
            intent: Classified intent
            
        Returns:
            Dictionary of extracted parameters
        """
        params: dict[str, Any] = {}
        
        # Extract file paths
        if intent in (Intent.PROFILE_FILE, Intent.GET_PROFILE):
            file_match = re.search(r'([a-zA-Z0-9_\-./\\]+\.(?:csv|parquet|json|xlsx))', user_input)
            if file_match:
                params['file_path'] = file_match.group(1)
        
        # Extract directory paths
        if intent == Intent.PROFILE_DIRECTORY:
            dir_match = re.search(r'(?:in|from)\s+([a-zA-Z0-9_\-./\\]+)', user_input)
            if dir_match:
                params['directory'] = dir_match.group(1)
        
        # Extract table names
        table_match = re.search(r'table\s+([a-zA-Z0-9_]+)', user_input, re.IGNORECASE)
        if table_match:
            params['table_name'] = table_match.group(1)
        
        return params
    
    def route(self, user_input: str) -> tuple[str | None, dict[str, Any], bool]:
        """Route user input to appropriate tool.
        
        Args:
            user_input: Raw user query
            
        Returns:
            Tuple of (tool_name, params, needs_clarification)
        """
        match = self.classify_intent(user_input)
        
        # Check if clarification is needed
        if match.needs_clarification():
            return (None, match.extracted_params, True)
        
        # Map intent to tool
        tool_name = self.INTENT_TO_TOOL.get(match.intent)
        
        if tool_name is None and match.intent == Intent.CONVERSATION:
            # Conversational query, let LLM handle it
            return (None, {}, False)
        
        return (tool_name, match.extracted_params, False)
