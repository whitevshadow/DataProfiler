"""
LCIL LLM Mapper

LLM-only semantic enrichment for low-cardinality columns (no deterministic rules).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from profiler.lcil.models import LCILCandidate, LCILInsight, GraphNode, GraphEdge

# Use litellm for API calls
try:
    from litellm import completion
except ImportError:
    completion = None
    logging.warning("LiteLLM not available - LCIL enrichment will fail")

# Load .env if available
try:
    from dotenv import load_dotenv
    project_root = Path(__file__).resolve().parent.parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
except ImportError:
    pass

log = logging.getLogger(__name__)


def batch_enrich_with_llm(
    candidates: list[LCILCandidate],
    batch_size: int = 10,
    provider: str = "nvidia",
    model: str | None = None,
    min_confidence: float = 0.6,
) -> list[LCILInsight]:
    """
    Enrich candidates using LLM in batches.
    
    Args:
        candidates: List of LCIL candidates
        batch_size: Number of columns per LLM request (reduce if hitting truncation)
        provider: LLM provider (nvidia, openai, etc.)
        model: Optional specific model name
        min_confidence: Minimum confidence threshold
        
    Returns:
        List of LCILInsight objects
    """
    insights = []
    
    # Reduce batch size to 3 for reliability (avoid JSON truncation)
    actual_batch_size = min(batch_size, 3)
    log.info(f"Using batch size: {actual_batch_size} (requested: {batch_size})")
    
    # Process in batches
    for i in range(0, len(candidates), actual_batch_size):
        batch = candidates[i:i + actual_batch_size]
        log.info(f"Processing batch {i // actual_batch_size + 1} ({len(batch)} columns)")
        
        try:
            batch_insights = _enrich_batch(batch, provider, model, min_confidence)
            insights.extend(batch_insights)
        except Exception as e:
            log.error(f"Batch enrichment failed: {e}")
            # Add fallback UNKNOWN insights
            for candidate in batch:
                insights.append(_create_fallback_insight(candidate))
    
    return insights


def _enrich_batch(
    batch: list[LCILCandidate],
    provider: str,
    model: str | None,
    min_confidence: float,
) -> list[LCILInsight]:
    """Enrich a single batch of candidates with LLM."""
    if completion is None:
        raise RuntimeError("LiteLLM not available - cannot enrich with LLM")
    
    # Get default model if not specified
    if not model:
        model = _get_default_model(provider)
    
    # Get API key
    api_key = _get_api_key(provider)
    if not api_key:
        raise ValueError(f"No API key found for provider: {provider}")
    
    # Build prompt
    prompt = _build_batch_prompt(batch)
    
    # Call LLM using litellm
    try:
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": _get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            api_key=api_key,
            api_base="https://integrate.api.nvidia.com/v1" if provider == "nvidia" else None,
            temperature=0.1,
            max_tokens=4000,
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        parsed = _parse_llm_response(response_text, batch)
        
        # Normalize and validate
        insights = []
        for item in parsed:
            insight = _normalize_insight(item, batch, min_confidence)
            if insight:
                insights.append(insight)
        
        return insights
        
    except Exception as e:
        log.error(f"LLM call failed: {e}")
        raise


def _get_api_key(provider: str) -> str | None:
    """Get API key for provider."""
    if provider == "nvidia":
        # Try single key first
        key = os.getenv("NVIDIA_API_KEY")
        if key:
            return key
        
        # Try numbered keys
        for i in range(1, 21):
            key = os.getenv(f"NVIDIA_API_KEY_{i}")
            if key:
                return key
        
        return None
    
    elif provider == "openai":
        return os.getenv("OPENAI_API_KEY")
    
    return None


def _build_batch_prompt(batch: list[LCILCandidate]) -> str:
    """Build LLM prompt for a batch of columns."""
    columns_data = []
    
    for candidate in batch:
        # Extract unique values from top_values and sample_values
        values_seen = set()
        for item in candidate.top_values[:20]:
            if isinstance(item, (list, tuple)) and len(item) >= 1:
                values_seen.add(str(item[0]))
            else:
                values_seen.add(str(item))
        
        for val in candidate.sample_values[:20]:
            values_seen.add(str(val))
        
        for val in candidate.canonical_samples[:20]:
            values_seen.add(str(val))
        
        unique_values = sorted(values_seen)[:30]  # Limit to 30 unique values
        
        col_info = {
            "table_name": candidate.table_name,
            "column_name": candidate.column_name,
            "distinct_count": candidate.distinct_count,
            "logical_type": candidate.logical_type,
            "physical_type": candidate.physical_type,
            "semantic_type": candidate.semantic_type,
            "sample_values": unique_values,
        }
        columns_data.append(col_info)
    
    prompt = f"""Analyze these {len(batch)} low-cardinality categorical columns and provide semantic enrichment.

For each column, return a JSON object with:
- semantic_domain: PascalCase domain (PaymentMethod, DeliveryMethod, Status, Priority, Color, etc.)
- business_meaning: Clear business description
- confidence: 0.0-1.0 confidence score
- is_ordered: boolean, true if values have natural ordering
- is_hierarchical: boolean, true if values form a hierarchy
- is_workflow: boolean, true if represents workflow/lifecycle states
- is_boolean: boolean, true if boolean-like (Yes/No, True/False, etc.)
- suggested_entity: PascalCase entity type or null
- ontology_tags: Array of lowercase ontology tags
- insights: Array of semantic insight strings
- evidence: Array of evidence strings supporting classification
- graph_nodes: Array of {{id, label, node_type, properties}} suggested graph nodes
- graph_edges: Array of {{source, target, relationship, properties}} suggested graph edges

CRITICAL: Only include graph nodes for observed values. Never hallucinate unobserved values.

Columns to analyze:
{json.dumps(columns_data, indent=2)}

Return a JSON array with one object per column in the same order."""
    
    return prompt


def _get_system_prompt() -> str:
    """Get system prompt for LCIL LLM."""
    return """You are a semantic data profiling expert. Analyze low-cardinality categorical columns and provide structured semantic enrichment.

Focus on:
1. Accurate semantic domain classification
2. Business-friendly descriptions
3. Detecting ordering, hierarchies, and workflows
4. Graph modeling suggestions (ONLY for observed values)
5. Ontology alignment

Return ONLY valid JSON. Never include markdown code blocks or explanations."""


def _get_default_model(provider: str) -> str:
    """Get default model for provider."""
    if provider == "nvidia":
        return "mistralai/ministral-14b-instruct-2512"  # Same as description generator
    elif provider == "openai":
        return "gpt-4o"
    else:
        return "mistralai/ministral-14b-instruct-2512"


def _parse_llm_response(response_text: str, batch: list[LCILCandidate]) -> list[dict[str, Any]]:
    """Parse LLM response, handling markdown code blocks."""
    # Strip markdown code blocks if present
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```), and last line (```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        else:
            log.warning(f"Expected JSON array, got {type(parsed)}")
            return []
    except json.JSONDecodeError as e:
        log.error(f"JSON decode failed: {e}")
        log.error(f"Response text: {text[:500]}")
        return []


def _normalize_insight(
    raw: dict[str, Any],
    batch: list[LCILCandidate],
    min_confidence: float,
) -> LCILInsight | None:
    """Normalize and validate LLM output."""
    try:
        table_name = raw.get("table_name", "unknown")
        column_name = raw.get("column_name", "unknown")
        
        # Find matching candidate for validation
        candidate = next((c for c in batch if c.table_name == table_name and c.column_name == column_name), None)
        if not candidate:
            log.warning(f"No matching candidate for {table_name}.{column_name}")
            return None
        
        # Extract fields
        semantic_domain = str(raw.get("semantic_domain", "Unknown")).strip()
        business_meaning = str(raw.get("business_meaning", "")).strip()
        confidence = float(raw.get("confidence", 0.5))
        
        # Clamp confidence
        confidence = max(0.0, min(1.0, confidence))
        
        # Apply min_confidence threshold
        if confidence < min_confidence:
            semantic_domain = "Unknown"
            business_meaning = business_meaning or "Low confidence classification"
        
        # Flags
        is_ordered = bool(raw.get("is_ordered", False))
        is_hierarchical = bool(raw.get("is_hierarchical", False))
        is_workflow = bool(raw.get("is_workflow", False))
        is_boolean = bool(raw.get("is_boolean", False))
        
        # Entity and tags
        suggested_entity = raw.get("suggested_entity")
        if suggested_entity:
            suggested_entity = str(suggested_entity).strip()
        
        ontology_tags = raw.get("ontology_tags", [])
        if not isinstance(ontology_tags, list):
            ontology_tags = []
        ontology_tags = [str(tag).lower().strip() for tag in ontology_tags]
        ontology_tags = list(dict.fromkeys(ontology_tags))  # Dedupe
        
        # Insights and evidence
        insights = raw.get("insights", [])
        if not isinstance(insights, list):
            insights = []
        insights = [str(i).strip() for i in insights if i]
        
        evidence = raw.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []
        evidence = [str(e).strip() for e in evidence if e]
        
        # Graph suggestions
        graph_nodes = []
        for node_data in raw.get("graph_nodes", []):
            if isinstance(node_data, dict):
                try:
                    node = GraphNode(
                        id=str(node_data.get("id", "")),
                        label=str(node_data.get("label", "")),
                        node_type=str(node_data.get("node_type", "Value")),
                        properties=node_data.get("properties", {}),
                    )
                    # Validate: do not include value nodes for unobserved values
                    if node.node_type.lower() == "value":
                        # Check if this value was actually observed
                        observed_values = _get_observed_values(candidate)
                        if node.label not in observed_values and node.id not in observed_values:
                            log.warning(f"Skipping hallucinated value node: {node.label}")
                            continue
                    graph_nodes.append(node)
                except Exception as e:
                    log.warning(f"Invalid graph node: {e}")
        
        graph_edges = []
        for edge_data in raw.get("graph_edges", []):
            if isinstance(edge_data, dict):
                try:
                    edge = GraphEdge(
                        source=str(edge_data.get("source", "")),
                        target=str(edge_data.get("target", "")),
                        relationship=str(edge_data.get("relationship", "RELATED_TO")),
                        properties=edge_data.get("properties", {}),
                    )
                    graph_edges.append(edge)
                except Exception as e:
                    log.warning(f"Invalid graph edge: {e}")
        
        insight = LCILInsight(
            table_name=table_name,
            column_name=column_name,
            semantic_domain=semantic_domain,
            business_meaning=business_meaning,
            confidence=confidence,
            is_ordered=is_ordered,
            is_hierarchical=is_hierarchical,
            is_workflow=is_workflow,
            is_boolean=is_boolean,
            suggested_entity=suggested_entity,
            ontology_tags=ontology_tags,
            insights=insights,
            evidence=evidence,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
        )
        
        return insight
        
    except Exception as e:
        log.error(f"Failed to normalize insight: {e}")
        return None


def _get_observed_values(candidate: LCILCandidate) -> set[str]:
    """Get all observed values from a candidate."""
    observed = set()
    
    for item in candidate.top_values:
        if isinstance(item, (list, tuple)) and len(item) >= 1:
            observed.add(str(item[0]))
        else:
            observed.add(str(item))
    
    for val in candidate.sample_values:
        observed.add(str(val))
    
    for val in candidate.canonical_samples:
        observed.add(str(val))
    
    return observed


def _create_fallback_insight(candidate: LCILCandidate) -> LCILInsight:
    """Create fallback insight when LLM fails."""
    return LCILInsight(
        table_name=candidate.table_name,
        column_name=candidate.column_name,
        semantic_domain="Unknown",
        business_meaning="LLM enrichment failed - fallback",
        confidence=0.0,
        is_ordered=False,
        is_hierarchical=False,
        is_workflow=False,
        is_boolean=False,
        suggested_entity=None,
        ontology_tags=[],
        insights=[],
        evidence=["LLM call failed"],
        graph_nodes=[],
        graph_edges=[],
    )
