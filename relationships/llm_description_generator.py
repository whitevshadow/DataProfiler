"""
LLM-Powered Semantic Column Description Generator

Uses NVIDIA's model via LiteLLM for automatic load balancing across multiple API keys.
Features intelligent rate limiting, parallel processing, and robust error recovery.
"""

import os
import json
import time
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import random

# Use litellm for API calls
try:
    from litellm import completion
except ImportError:
    print("[WARNING] LiteLLM not available, using openai directly")
    from openai import OpenAI
    completion = None

load_dotenv()


@dataclass
class LLMColumnDescription:
    """LLM-generated semantic description for a column."""
    table_name: str
    column_name: str
    semantic_description: str
    business_purpose: str
    data_domain: str
    likely_relationships: List[str]
    
    def to_embedding_text(self) -> str:
        """Generate text representation for embedding."""
        # Handle relationships that might be dicts or non-strings
        if self.likely_relationships:
            rel_strings = []
            for r in self.likely_relationships:
                if isinstance(r, str):
                    rel_strings.append(r)
                elif isinstance(r, dict):
                    # If it's a dict, try to extract useful string
                    rel_strings.append(str(r.get('target', r.get('table', str(r)))))
                else:
                    rel_strings.append(str(r))
            relationships_text = ", ".join(rel_strings)
        else:
            relationships_text = "none"
        return (
            f"{self.table_name}.{self.column_name}: {self.semantic_description}. "
            f"Purpose: {self.business_purpose}. Domain: {self.data_domain}. "
            f"Relationships: {relationships_text}"
        )


class NVIDIADescriptionGenerator:
    """
    Generate semantic descriptions using NVIDIA LLM via LiteLLM Router.
    Automatic load balancing, rate limiting, and retry logic with robust error handling.
    """
    
    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        model: str = "mistralai/ministral-14b-instruct-2512",
        max_workers: int = 5,  # Reduced to 5 for stability
        rpm_per_key: int = 15,  # 15 req/min per key
    ):
        """
        Initialize generator with LiteLLM Router.
        
        Args:
            api_keys: List of NVIDIA API keys
            model: Model name
            max_workers: Max parallel workers  
            rpm_per_key: Requests per minute per API key
        """
        self.model = model
        self.max_workers = max_workers
        self.rpm_per_key = rpm_per_key
        self.api_base = "https://integrate.api.nvidia.com/v1"
        
        # Load API keys
        if api_keys:
            self.api_keys = api_keys
        else:
            self.api_keys = self._load_api_keys_from_env()
        
        if not self.api_keys:
            raise ValueError("No API keys found")
        
        # Round-robin key selection
        self._key_index = 0
        self._key_lock = threading.Lock()
        
        # Rate limiting per key
        self._request_times = {i: [] for i in range(len(self.api_keys))}
        self._rate_lock = threading.Lock()
        
        total_rpm = rpm_per_key * len(self.api_keys)
        print(f"[LLM Generator] {len(self.api_keys)} keys, {max_workers} workers, {total_rpm} req/min")
    
    def _load_api_keys_from_env(self) -> List[str]:
        """Load API keys from environment."""
        keys = []
        
        # Try single key
        single = os.getenv("NVIDIA_API_KEY")
        if single:
            keys.append(single)
            return keys
        
        # Try numbered keys
        i = 1
        while True:
            key = os.getenv(f"NVIDIA_API_KEY_{i}")
            if not key:
                break
            keys.append(key)
            i += 1
        
        return keys
    
    def _get_next_key(self) -> tuple[str, int]:
        """Get next API key using round-robin."""
        with self._key_lock:
            idx = self._key_index
            key = self.api_keys[idx]
            self._key_index = (self._key_index + 1) % len(self.api_keys)
            return key, idx
    
    def _rate_limit(self, key_idx: int):
        """Enforce rate limiting for specific key."""
        with self._rate_lock:
            now = time.time()
            # Keep only recent requests for this key
            self._request_times[key_idx] = [
                t for t in self._request_times[key_idx] if now - t < 60
            ]
            
            # Wait if at limit
            if len(self._request_times[key_idx]) >= self.rpm_per_key:
                sleep_time = 61 - (now - self._request_times[key_idx][0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.time()
                    self._request_times[key_idx] = [
                        t for t in self._request_times[key_idx] if now - t < 60
                    ]
            
            self._request_times[key_idx].append(now)
    
    def generate_description(
        self,
        table_name: str,
        column_name: str,
        physical_type: str,
        sample_values: List[Any],
        statistics: Optional[Dict[str, Any]] = None,
    ) -> Optional[LLMColumnDescription]:
        """
        Generate semantic description for a column.
        """
        prompt = self._build_prompt(
            table_name, column_name, physical_type, sample_values, statistics
        )
        
        # Get key and enforce rate limit
        api_key, key_idx = self._get_next_key()
        self._rate_limit(key_idx)
        
        try:
            # Call LiteLLM with specific key
            if completion is None:
                raise RuntimeError("LiteLLM is not available. Please install litellm.")
            response = completion(
                model=self.model,
                api_key=api_key,
                api_base=self.api_base,
                messages=[
                    {
                        "role": "system",
                        "content": """You are a deterministic structured metadata generation engine.

Your output MUST be EXACTLY ONE valid JSON object that parses with json.loads() WITHOUT preprocessing.

CRITICAL RULES:
- Return ONLY JSON
- NO markdown
- NO code fences
- NO explanations
- NO trailing commas
- CLOSE ALL QUOTES
- CLOSE ALL BRACES

Mandatory schema:
{
  "semantic_description": "<concise sentence about entity ownership and relational role>",
  "business_purpose": "<why this column exists>",
  "data_domain": "<PRIMARY_KEY|FOREIGN_KEY|IDENTIFIER|MEASURE|DIMENSION|TEMPORAL|GEOSPATIAL|AUDIT>",
  "likely_relationships": []
}

Semantic rules:
- For PK-like columns: emphasize stable identity, entity anchoring
- For FK-like columns: emphasize referenced entity, relational linkage
- For attributes: emphasize descriptive meaning
- For measures: emphasize quantitative interpretation
- For temporal: emphasize audit/validity semantics
- Use consistent terminology: "stable identifier", "foreign reference identifier", etc."""
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.05,
                max_tokens=120,
                top_p=0.85,
                frequency_penalty=0.15,
                presence_penalty=0.0,
                timeout=60,
            )
            # Handle response for LiteLLM and OpenAI
            content = None
            if hasattr(response, "choices") and response.choices:
                # LiteLLM/OpenAI compatible
                content = response.choices[0].message.content.strip()
            elif hasattr(response, "content"):
                # Some OpenAI clients
                content = response.content.strip()
            elif isinstance(response, str):
                content = response.strip()
            if not content:
                raise RuntimeError("No content returned from LLM completion.")
            content = self._extract_json(content)
            content = self._fix_json(content)
            desc_dict = json.loads(content)
            
            # Ensure likely_relationships is a list of strings
            raw_relationships = desc_dict.get("likely_relationships", [])
            clean_relationships = []
            if isinstance(raw_relationships, list):
                for item in raw_relationships[:5]:
                    if isinstance(item, str):
                        clean_relationships.append(item)
                    elif isinstance(item, dict):
                        # Extract string from dict if possible
                        clean_relationships.append(str(item.get('target', item.get('table', ''))))
                    else:
                        clean_relationships.append(str(item))
            
            return LLMColumnDescription(
                table_name=table_name,
                column_name=column_name,
                semantic_description=desc_dict.get("semantic_description", "")[:500],
                business_purpose=desc_dict.get("business_purpose", "")[:500],
                data_domain=desc_dict.get("data_domain", "UNKNOWN"),
                likely_relationships=clean_relationships,
            )
            
        except Exception as e:
            print(f"[WARNING] LLM generation failed for {table_name}.{column_name}: {str(e)[:120]}")
            return self._fallback_description(
                table_name, column_name, physical_type, sample_values
            )
    
    def _extract_json(self, content: str) -> str:
        """Extract JSON from markdown or other formatting."""
        content = content.strip()
        
        # Remove markdown code fences
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            parts = content.split("```")
            if len(parts) >= 3:
                content = parts[1].strip()
        
        # Remove any leading/trailing non-JSON text
        # Find first { and last }
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1 and end > start:
            content = content[start:end+1]
        
        return content
    
    def _fix_json(self, content: str) -> str:
        """Fix common JSON issues including unterminated strings and trailing commas."""
        # First, remove any trailing commas before closing braces/brackets
        content = re.sub(r',\s*([}\]])', r'\1', content)
    def _fix_json(self, content: str) -> str:
        """Fix common JSON issues including unterminated strings and trailing commas."""
        # First, remove any trailing commas before closing braces/brackets
        content = re.sub(r',\s*([}\]])', r'\1', content)
        
        # Try to parse - if it works, return as-is
        try:
            json.loads(content)
            return content
        except json.JSONDecodeError as e:
            error_msg = str(e)
            
            # Fix unterminated strings and other common issues
            if 'Unterminated string' in error_msg or 'Expecting' in error_msg or 'Illegal trailing comma' in error_msg:
                # Split into lines and fix line by line
                lines = content.split('\n')
                fixed_lines = []
                
                for line in lines:
                    stripped = line.strip()
                    
                    # Skip empty lines
                    if not stripped:
                        fixed_lines.append(line)
                        continue
                    
                    # Count quotes - if odd, we have unterminated string
                    # Don't count escaped quotes
                    quote_count = 0
                    escaped = False
                    for char in line:
                        if char == '\\' and not escaped:
                            escaped = True
                            continue
                        if char == '"' and not escaped:
                            quote_count += 1
                        escaped = False
                    
                    if quote_count % 2 == 1:
                        # Find where to add closing quote
                        if stripped.endswith(','):
                            line = line.rstrip()[:-1] + '",'
                        elif stripped.endswith(':'):
                            line = line + '"'
                        elif stripped.endswith('{') or stripped.endswith('['):
                            line = line.rstrip() + '"'
                        elif stripped.endswith('}') or stripped.endswith(']'):
                            # Insert quote before closing brace
                            idx = line.rfind(stripped[-1])
                            line = line[:idx] + '"' + line[idx:]
                        else:
                            line = line.rstrip() + '"'
                    
                    fixed_lines.append(line)
                
                content = '\n'.join(fixed_lines)
                
                # Remove trailing commas again after fixes
                content = re.sub(r',\s*([}\]])', r'\1', content)
        
        # Balance braces
        open_b = content.count('{')
        close_b = content.count('}')
        if open_b > close_b:
            content += '}' * (open_b - close_b)
        
        # Balance brackets  
        open_br = content.count('[')
        close_br = content.count(']')
        if open_br > close_br:
            content += ']' * (open_br - close_br)
        
        return content
    
    def _build_prompt(
        self,
        table_name: str,
        column_name: str,
        physical_type: str,
        sample_values: List[Any],
        statistics: Optional[Dict[str, Any]],
    ) -> str:
        """Build prompt for LLM with embedding optimization context."""
        # Limit samples to avoid huge prompts
        samples = [str(v)[:50] for v in sample_values[:8] if v is not None]
        
        stats_text = ""
        if statistics:
            distinct = statistics.get("distinct_count", 0)
            null_ratio = statistics.get("null_ratio", 0)
            uniqueness = statistics.get("uniqueness_ratio", 0)
            stats_text = f"\nStatistics: {distinct} distinct values, {null_ratio:.1%} nulls, {uniqueness:.1%} unique"
        
        return f"""Table: {table_name}
Column: {column_name}
Type: {physical_type}{stats_text}
Samples: {', '.join(samples) if samples else 'None'}

Return ONLY valid JSON (no markdown, no explanations):
{{
  "semantic_description": "<1-2 sentences: entity ownership, relational role, identifier behavior>",
  "business_purpose": "<why this column exists>",
  "data_domain": "<PRIMARY_KEY|FOREIGN_KEY|IDENTIFIER|MEASURE|DIMENSION|TEMPORAL|GEOSPATIAL>",
  "likely_relationships": ["<table.column if FK>"]
}}"""
    
    def _fallback_description(
        self,
        table_name: str,
        column_name: str,
        physical_type: str,
        sample_values: List[Any],
    ) -> LLMColumnDescription:
        """Create rule-based fallback description."""
        col_lower = column_name.lower()
        
        if 'id' in col_lower:
            domain = "IDENTIFIER"
            desc = f"Identifier column in {table_name}"
            purpose = "Uniquely identify records or reference other tables"
        elif any(x in col_lower for x in ['date', 'time', 'when']):
            domain = "TEMPORAL"
            desc = f"Temporal information for {table_name}"
            purpose = "Track timing of events or records"
        elif any(x in col_lower for x in ['name', 'description']):
            domain = "DIMENSION"
            desc = f"Descriptive attribute in {table_name}"
            purpose = "Provide human-readable labels"
        elif any(x in col_lower for x in ['amount', 'price', 'quantity', 'count']):
            domain = "MEASURE"
            desc = f"Numeric measure in {table_name}"
            purpose = "Track quantitative metrics"
        else:
            domain = "DIMENSION"
            desc = f"Attribute in {table_name}"
            purpose = "Store related information"
        
        return LLMColumnDescription(
            table_name=table_name,
            column_name=column_name,
            semantic_description=desc,
            business_purpose=purpose,
            data_domain=domain,
            likely_relationships=[],
        )
    
    def generate_descriptions_for_tables(
        self,
        table_profiles: Dict[str, Dict[str, Any]]
    ) -> List[LLMColumnDescription]:
        """
        Generate descriptions for all columns (parallel with rate limiting).
        """
        all_descriptions = []
        total = sum(len((p or {}).get("columns") or []) for p in table_profiles.values())
        
        print(f"\n[LLM] Processing {total} columns across {len(table_profiles)} tables...")
        
        start = time.time()
        
        # Collect tasks
        tasks = []
        for table_name, profile in table_profiles.items():
            for col in (profile or {}).get("columns") or []:
                sample_values = (col or {}).get("sample_values") or []
                statistics = (col or {}).get("statistics") or {}
                tasks.append({
                    "table_name": table_name,
                    "column_name": (col or {}).get("column_name", "unknown"),
                    "physical_type": (col or {}).get("physical_type", "UNKNOWN"),
                    "sample_values": sample_values[:10] if isinstance(sample_values, list) else [],
                    "statistics": statistics if isinstance(statistics, dict) else {},
                })
        
        # Process in parallel
        completed = 0
        failed = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {
                executor.submit(
                    self.generate_description,
                    t["table_name"],
                    t["column_name"],
                    t["physical_type"],
                    t["sample_values"],
                    t["statistics"],
                ): t
                for t in tasks
            }
            
            for future in as_completed(future_to_task):
                desc = future.result()
                if desc:
                    all_descriptions.append(desc)
                else:
                    failed += 1
                
                completed += 1
                if completed % 25 == 0 or completed == total:
                    elapsed = time.time() - start
                    rate = completed / elapsed if elapsed > 0 else 0
                    success = len(all_descriptions) / completed * 100 if completed > 0 else 0
                    eta = (total - completed) / rate if rate > 0 else 0
                    print(f"  [{completed}/{total}] {rate:.1f}/s | Success: {success:.0f}% | ETA: {eta:.0f}s")
        
        elapsed = time.time() - start
        rate = len(all_descriptions) / elapsed if elapsed > 0 else 0
        
        print(f"\n[LLM] Done: {len(all_descriptions)} generated, {failed} failed ({elapsed:.1f}s, {rate:.1f}/s)\n")
        
        return all_descriptions


def save_descriptions_to_json(
    descriptions: List[LLMColumnDescription],
    output_path: str
):
    """Save descriptions to JSON file."""
    data = [asdict(d) for d in descriptions]
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"[Descriptions saved to: {output_path}]")


def load_descriptions_from_json(json_path: str) -> List[LLMColumnDescription]:
    """Load descriptions from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [LLMColumnDescription(**d) for d in data]
