"""
Semantic Embedding & ANN Retrieval Engine

Generates semantic embeddings for columns and performs ANN-based candidate retrieval.

Core Principles:
    - Embeddings are for CANDIDATE GENERATION only
    - ANN similarity is NOT authoritative truth
    - Maximize recall, not precision
    - All candidates must undergo deterministic validation

Embedding Strategy:
    - NVIDIA llama-nemotron-embed-1b-v2 via LiteLLM
    - Cosine similarity for semantic matching
    - Configurable similarity threshold
    - Load balanced across NVIDIA API keys
"""

from typing import List, Dict, Tuple, Any, Optional
from dataclasses import dataclass
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
try:
    from relationships.semantic_column_descriptor import ColumnDescription
except ImportError:
    # Fallback: ColumnDescription might not exist in simplified pipeline
    ColumnDescription = None
import os
from litellm import embedding
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class SemanticCandidate:
    """A semantically similar column pair."""
    fk_table: str
    fk_column: str
    pk_table: str
    pk_column: str
    semantic_similarity: float
    fk_description: str
    pk_description: str
    similarity_reasoning: List[str]


class SemanticEmbeddingEngine:
    """
    Generates embeddings for column descriptions using NVIDIA llama-nemotron-embed-1b-v2.
    
    Uses LiteLLM with load balancing across multiple NVIDIA API keys.
    """
    
    def __init__(self):
        """Initialize embedding engine with NVIDIA model and API keys."""
        # For NVIDIA's endpoint, use model name without nvidia/ prefix
        self.model = "nvidia/llama-nemotron-embed-1b-v2"
        self.encoding_format = "float"
        self.api_base = "https://integrate.api.nvidia.com/v1"
        self.custom_llm_provider = "nvidia"
        self.is_fitted = False
        self.embeddings_cache = {}
        self.embedding_dim = None
        
        # Load NVIDIA API keys for load balancing
        self.api_keys = []
        for i in range(1, 10):  # Check for up to 9 keys
            key = os.getenv(f"NVIDIA_API_KEY_{i}")
            if key:
                self.api_keys.append(key)
        
        if not self.api_keys:
            # Fallback to single key
            key = os.getenv("NVIDIA_API_KEY")
            if key:
                self.api_keys.append(key)
            else:
                raise ValueError("No NVIDIA_API_KEY found in environment")
        
        self.current_key_idx = 0
        print(f"[EMBEDDING] Initialized with {len(self.api_keys)} NVIDIA API keys")
    
    def _get_next_api_key(self) -> str:
        """Get next API key for load balancing (round-robin)."""
        key = self.api_keys[self.current_key_idx]
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        return key
    
    def _generate_embeddings_batch(self, texts: List[str], batch_size: int = 20) -> np.ndarray:
        """Generate embeddings for a batch of texts using NVIDIA model."""
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            api_key = self._get_next_api_key()
            
            try:
                response = embedding(
                    model=self.model,
                    input=batch,
                    encoding_format=self.encoding_format,
                    api_key=api_key,
                    api_base=self.api_base,
                    custom_llm_provider=self.custom_llm_provider,
                    input_type="passage",  # Required for asymmetric models
                )
                
                # Extract embeddings from response
                batch_embeddings = [item['embedding'] for item in response.data]
                all_embeddings.extend(batch_embeddings)
                
            except Exception as e:
                print(f"[WARNING] Embedding batch {i//batch_size + 1} failed: {str(e)[:100]}")
                # Retry with different key
                api_key = self._get_next_api_key()
                try:
                    response = embedding(
                        model=self.model,
                        input=batch,
                        encoding_format=self.encoding_format,
                        api_key=api_key,
                        api_base=self.api_base,
                        custom_llm_provider=self.custom_llm_provider,
                        input_type="passage",  # Required for asymmetric models
                    )
                    batch_embeddings = [item['embedding'] for item in response.data]
                    all_embeddings.extend(batch_embeddings)
                except Exception as e2:
                    print(f"[ERROR] Embedding retry failed: {str(e2)[:100]}")
                    raise
        
        return np.array(all_embeddings)
    
    def fit_and_transform(
        self,
        descriptions: List[Any],  # Accept any column description type with to_embedding_text()
    ) -> np.ndarray:
        """
        Generate embeddings for descriptions using NVIDIA model.
        
        Args:
            descriptions: List of description objects (must have to_embedding_text() method)
        
        Returns:
            Embedding matrix (n_columns × embedding_dim)
        """
        print(f"[EMBEDDING] Generating embeddings for {len(descriptions)} columns...")
        
        # Extract embedding texts
        texts = [desc.to_embedding_text() for desc in descriptions]
        
        # Generate embeddings using NVIDIA model
        embeddings = self._generate_embeddings_batch(texts)
        self.is_fitted = True
        self.embedding_dim = embeddings.shape[1]
        
        print(f"[EMBEDDING] Generated {len(embeddings)} embeddings with {self.embedding_dim} dimensions")
        
        # Cache embeddings
        for i, desc in enumerate(descriptions):
            key = (desc.table_name, desc.column_name)
            self.embeddings_cache[key] = embeddings[i]
        
        return embeddings
    
    def transform(
        self,
        descriptions: List[ColumnDescription],
    ) -> np.ndarray:
        """
        Transform descriptions to embeddings using NVIDIA model.
        
        Args:
            descriptions: List of ColumnDescription objects
        
        Returns:
            Embedding matrix
        """
        if not self.is_fitted:
            raise ValueError("Engine not fitted. Call fit_and_transform first.")
        
        texts = [desc.to_embedding_text() for desc in descriptions]
        return self._generate_embeddings_batch(texts)
    
    def get_embedding(
        self,
        table: str,
        column: str,
    ) -> Optional[np.ndarray]:
        """Get cached embedding for a column."""
        return self.embeddings_cache.get((table, column))


class ANNCandidateRetriever:
    """
    Retrieves semantically similar column pairs using ANN search.
    
    Purpose: CANDIDATE GENERATION ONLY
    
    Maximizes recall by using a low similarity threshold.
    All candidates must be validated deterministically.
    """
    
    def __init__(
        self,
        min_similarity: float = 0.30,  # Low threshold for high recall
        max_candidates_per_column: int = 20,
    ):
        """
        Initialize ANN retriever.
        
        Args:
            min_similarity: Minimum cosine similarity for candidates
            max_candidates_per_column: Max candidates to retrieve per column
        """
        self.min_similarity = min_similarity
        self.max_candidates_per_column = max_candidates_per_column
    
    def retrieve_candidates(
        self,
        fk_descriptions: List[Any],  # Accept any column description type
        pk_descriptions: List[Any],
        fk_embeddings: np.ndarray,
        pk_embeddings: np.ndarray,
    ) -> List[SemanticCandidate]:
        """
        Retrieve semantically similar FK->PK candidate pairs.
        
        Args:
            fk_descriptions: FK column descriptions (LLMColumnDescription or ColumnDescription)
            pk_descriptions: PK column descriptions (LLMColumnDescription or ColumnDescription)
            fk_embeddings: FK embeddings matrix
            pk_embeddings: PK embeddings matrix
        
        Returns:
            List of SemanticCandidate objects
        """
        candidates = []
        
        # Compute similarity matrix
        similarity_matrix = cosine_similarity(fk_embeddings, pk_embeddings)
        
        # For each FK column
        for i, fk_desc in enumerate(fk_descriptions):
            # Get similarities to all PK columns
            similarities = similarity_matrix[i]
            
            # Find top-k similar PKs
            top_indices = np.argsort(similarities)[::-1][:self.max_candidates_per_column]
            
            for pk_idx in top_indices:
                similarity = similarities[pk_idx]
                
                # Filter by threshold
                if similarity < self.min_similarity:
                    continue
                
                pk_desc = pk_descriptions[pk_idx]
                
                # Skip same table/same column (self-loop)
                if fk_desc.table_name == pk_desc.table_name and fk_desc.column_name == pk_desc.column_name:
                    continue
                
                # Generate reasoning
                reasoning = self._generate_similarity_reasoning(
                    fk_desc, pk_desc, similarity
                )
                
                candidate = SemanticCandidate(
                    fk_table=fk_desc.table_name,
                    fk_column=fk_desc.column_name,
                    pk_table=pk_desc.table_name,
                    pk_column=pk_desc.column_name,
                    semantic_similarity=float(similarity),
                    fk_description=fk_desc.to_embedding_text(),
                    pk_description=pk_desc.to_embedding_text(),
                    similarity_reasoning=reasoning,
                )
                
                candidates.append(candidate)
        
        # Sort by similarity (descending)
        candidates.sort(key=lambda c: c.semantic_similarity, reverse=True)
        
        return candidates
    
    def _generate_similarity_reasoning(
        self,
        fk_desc: Any,  # Accept any column description type
        pk_desc: Any,
        similarity: float,
    ) -> List[str]:
        """Generate reasoning for semantic similarity."""
        
        reasons = []
        
        # Similarity level
        if similarity >= 0.80:
            reasons.append("Very high semantic similarity")
        elif similarity >= 0.60:
            reasons.append("High semantic similarity")
        elif similarity >= 0.40:
            reasons.append("Moderate semantic similarity")
        else:
            reasons.append("Low semantic similarity")
        
        # Column name similarity
        fk_lower = fk_desc.column_name.lower()
        pk_lower = pk_desc.column_name.lower()
        
        if fk_lower == pk_lower:
            reasons.append("Exact column name match")
        elif pk_lower in fk_lower or fk_lower in pk_lower:
            reasons.append("Column name substring match")
        
        # Optional entity reference match (if available)
        if hasattr(fk_desc, 'entity_reference') and hasattr(pk_desc, 'entity_reference'):
            if fk_desc.entity_reference and pk_desc.entity_reference:
                if fk_desc.entity_reference == pk_desc.entity_reference:
                    reasons.append(f"Both reference '{fk_desc.entity_reference}' entity")
        
        # Identifier type match (if available)
        if hasattr(fk_desc, 'identifier_type') and hasattr(pk_desc, 'identifier_type'):
            if fk_desc.identifier_type == "foreign_reference" and \
               pk_desc.identifier_type and "primary" in pk_desc.identifier_type:
                reasons.append("FK→PK identifier type alignment")
        
        # Semantic role match (if available)
        if hasattr(fk_desc, 'semantic_role') and hasattr(pk_desc, 'semantic_role'):
            if fk_desc.semantic_role == pk_desc.semantic_role == "identifier":
                reasons.append("Both are identifier fields")
        
        # Relationship hints (if available)
        if hasattr(fk_desc, 'relationship_hints') and hasattr(pk_desc, 'relationship_hints'):
            if fk_desc.relationship_hints and pk_desc.relationship_hints:
                fk_hints = set(fk_desc.relationship_hints)
                pk_hints = set(pk_desc.relationship_hints)
                common_hints = fk_hints & pk_hints
                if common_hints:
                    reasons.append(f"Shared hints: {', '.join(list(common_hints)[:2])}")
        
        return reasons
    
    def filter_by_suppression(
        self,
        candidates: List[SemanticCandidate],
        fk_descriptions: Dict[Tuple[str, str], ColumnDescription],
    ) -> List[SemanticCandidate]:
        """
        Filter out candidates with suppressed semantic roles.
        
        Args:
            candidates: List of semantic candidates
            fk_descriptions: Dict mapping (table, column) -> ColumnDescription
        
        Returns:
            Filtered candidates
        """
        filtered = []
        
        for candidate in candidates:
            fk_key = (candidate.fk_table, candidate.fk_column)
            fk_desc = fk_descriptions.get(fk_key)
            
            if not fk_desc:
                continue
            
            # Suppress temporal, audit, measure fields (if semantic_role available)
            if hasattr(fk_desc, 'semantic_role'):
                suppressed_roles = {"temporal", "audit", "measure"}
                if fk_desc.semantic_role in suppressed_roles:
                    continue
            
            # Suppress if hints indicate unsuitability (if relationship_hints available)
            if hasattr(fk_desc, 'relationship_hints') and fk_desc.relationship_hints:
                unsuitable_hints = [
                    h for h in fk_desc.relationship_hints
                    if "not_suitable" in h
                ]
                if unsuitable_hints:
                    continue
            
            filtered.append(candidate)
        
        return filtered


class SemanticCandidateManager:
    """
    Manages semantic candidate generation end-to-end.
    
    Coordinates:
    - Embedding generation
    - ANN retrieval
    - Filtering
    """
    
    def __init__(
        self,
        min_similarity: float = 0.30,
        max_candidates_per_column: int = 20,
    ):
        """Initialize semantic candidate manager."""
        self.embedding_engine = SemanticEmbeddingEngine()
        self.ann_retriever = ANNCandidateRetriever(
            min_similarity=min_similarity,
            max_candidates_per_column=max_candidates_per_column,
        )
    
    def generate_semantic_candidates(
        self,
        all_descriptions: List[ColumnDescription],
        pk_candidate_columns: List[Tuple[str, str]],  # (table, column) pairs
    ) -> List[SemanticCandidate]:
        """
        Generate semantic FK candidates using ANN retrieval.
        
        Args:
            all_descriptions: All column descriptions
            pk_candidate_columns: List of (table, column) tuples for PK candidates
        
        Returns:
            List of SemanticCandidate objects for deterministic validation
        """
        # Separate FK and PK descriptions
        pk_candidate_set = set(pk_candidate_columns)
        
        fk_descriptions = [
            desc for desc in all_descriptions
            if (desc.table_name, desc.column_name) not in pk_candidate_set
        ]
        
        pk_descriptions = [
            desc for desc in all_descriptions
            if (desc.table_name, desc.column_name) in pk_candidate_set
        ]
        
        if not fk_descriptions or not pk_descriptions:
            return []
        
        # Generate embeddings
        all_descs_for_fitting = fk_descriptions + pk_descriptions
        all_embeddings = self.embedding_engine.fit_and_transform(all_descs_for_fitting)
        
        fk_embeddings = all_embeddings[:len(fk_descriptions)]
        pk_embeddings = all_embeddings[len(fk_descriptions):]
        
        # Retrieve candidates
        candidates = self.ann_retriever.retrieve_candidates(
            fk_descriptions, pk_descriptions,
            fk_embeddings, pk_embeddings,
        )
        
        # Filter by suppression
        fk_desc_dict = {
            (desc.table_name, desc.column_name): desc
            for desc in fk_descriptions
        }
        candidates = self.ann_retriever.filter_by_suppression(
            candidates, fk_desc_dict
        )
        
        return candidates


# Convenience functions

def generate_semantic_candidates(
    all_descriptions: List[ColumnDescription],
    pk_candidate_columns: List[Tuple[str, str]],
    min_similarity: float = 0.30,
) -> List[SemanticCandidate]:
    """
    Convenience function to generate semantic candidates.
    
    Args:
        all_descriptions: All column descriptions
        pk_candidate_columns: PK candidate (table, column) pairs
        min_similarity: Minimum cosine similarity
    
    Returns:
        List of SemanticCandidate objects
    """
    manager = SemanticCandidateManager(min_similarity=min_similarity)
    return manager.generate_semantic_candidates(
        all_descriptions, pk_candidate_columns
    )
