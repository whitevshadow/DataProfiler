"""ANN Pruner.

Loads semantic column embeddings generated from descriptions and applies
similarity-based pruning after deterministic containment.

Design constraints:
- Missing embeddings must never crash the pipeline.
- Missing embeddings must never auto-reject candidates.
- Similarity is advisory; deterministic validation remains authoritative.
"""

import json
import math
from pathlib import Path
from typing import Tuple, Dict, List, Optional

DEFAULT_THRESHOLD = 0.75


class AnnPruner:
    def __init__(self, embeddings_path: str = "output/descriptions/description_embeddings.json", similarity_threshold: float = DEFAULT_THRESHOLD):
        """Load embeddings from the given JSON file.

        The file should contain a dictionary mapping ``"table.column"`` strings to
        embedding vectors (list of floats).  If the file cannot be read, the
        pruner falls back to returning a constant similarity of 0.9 so that the
        pipeline continues without failure.
        """
        self.embeddings: Dict[str, list] = {}
        self.threshold = similarity_threshold
        self.embeddings_path = embeddings_path
        try:
            raw = json.loads(Path(embeddings_path).read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "embeddings" in raw:
                # Structured format: {"embeddings": {"table.col": {"vector": [...]}}}
                for key, value in raw["embeddings"].items():
                    if isinstance(value, dict) and isinstance(value.get("vector"), list):
                        self.embeddings[key] = value["vector"]
            elif isinstance(raw, dict):
                # Backward compatible format: {"table.col": [..vector..]}
                for key, value in raw.items():
                    if isinstance(value, list):
                        self.embeddings[key] = value
        except Exception:
            # Fallback: empty store – callers will receive neutral similarity.
            self.embeddings = {}
        self._missing_pairs: List[Dict[str, str]] = []

    def _cosine(self, a: list, b: list) -> float:
        """Return cosine similarity between two vectors."""
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def prune_candidate(self, fk_id: str, pk_id: str) -> Tuple[float, bool]:
        """Compute similarity and decide whether to keep the candidate.

        Returns a tuple ``(similarity, keep)`` where ``keep`` is ``True`` if the
        similarity meets or exceeds the configured threshold.
        """
        fk_vec = self.embeddings.get(fk_id)
        pk_vec = self.embeddings.get(pk_id)
        # Missing embeddings are non-fatal and non-authoritative:
        # keep candidate and assign neutral similarity.
        if fk_vec is None or pk_vec is None:
            similarity = 0.0
            self._missing_pairs.append({"fk_id": fk_id, "pk_id": pk_id})
            keep = True
            return similarity, keep
        else:
            similarity = self._cosine(fk_vec, pk_vec)
        keep = similarity >= self.threshold
        return similarity, keep

    def rank_neighbors(self, fk_id: str, pk_ids: List[str], top_k: int = 5) -> List[Dict[str, float | str]]:
        """Rank PK candidates for one FK by semantic similarity."""
        fk_vec = self.embeddings.get(fk_id)
        if fk_vec is None:
            return []

        scored: List[Dict[str, float | str]] = []
        for pk_id in pk_ids:
            pk_vec = self.embeddings.get(pk_id)
            if pk_vec is None:
                continue
            scored.append({"pk_id": pk_id, "semantic_similarity": self._cosine(fk_vec, pk_vec)})

        scored.sort(key=lambda item: float(item["semantic_similarity"]), reverse=True)
        return scored[:top_k]

    def score_with_reason(self, fk_id: str, pk_id: str, candidate_pk_ids: Optional[List[str]] = None, top_k: int = 5) -> Dict[str, object]:
        """Return ANN decision with explicit keep/drop reason."""
        similarity, keep_by_threshold = self.prune_candidate(fk_id, pk_id)

        if candidate_pk_ids:
            neighbors = self.rank_neighbors(fk_id, candidate_pk_ids, top_k=top_k)
            neighbor_ids = [str(item["pk_id"]) for item in neighbors]
            in_top_k = pk_id in neighbor_ids
            keep = keep_by_threshold and in_top_k
            if not self.embeddings.get(fk_id) or not self.embeddings.get(pk_id):
                reason = "missing_embedding_keep"
                keep = True
            elif not in_top_k:
                reason = "not_in_top_k_neighbors"
            elif not keep_by_threshold:
                reason = "below_similarity_threshold"
            else:
                reason = "semantic_match"
            return {
                "fk_id": fk_id,
                "pk_id": pk_id,
                "semantic_similarity": similarity,
                "keep": keep,
                "reason": reason,
                "neighbors": neighbors,
            }

        if not self.embeddings.get(fk_id) or not self.embeddings.get(pk_id):
            reason = "missing_embedding_keep"
            keep = True
        elif keep_by_threshold:
            reason = "semantic_match"
            keep = True
        else:
            reason = "below_similarity_threshold"
            keep = False

        return {
            "fk_id": fk_id,
            "pk_id": pk_id,
            "semantic_similarity": similarity,
            "keep": keep,
            "reason": reason,
            "neighbors": [],
        }

    def get_missing_embeddings_report(self) -> List[Dict[str, str]]:
        """Return deduplicated missing embedding pairs for diagnostics."""
        unique = {(item["fk_id"], item["pk_id"]) for item in self._missing_pairs}
        return [
            {"fk_id": fk_id, "pk_id": pk_id}
            for fk_id, pk_id in sorted(unique)
        ]
