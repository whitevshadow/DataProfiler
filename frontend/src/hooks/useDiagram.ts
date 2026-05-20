import { useCallback, useEffect, useMemo, useState } from "react";
import { DiagramState } from "../types";
import { fetchDiagramState } from "../data/api";

export function useDiagram() {
  const [diagram, setDiagram] = useState<DiagramState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    minConfidence: 0.5,
    relationshipClasses: ["TRUE_FK", "SEMANTICALLY_RELATED", "SHARED_ENTITY_DOMAIN"],
    topK: undefined as number | undefined,
  });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchDiagramState({
        minConfidence: filters.minConfidence,
        relationshipClasses: filters.relationshipClasses,
        topK: filters.topK,
      });
      setDiagram(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load diagram");
    } finally {
      setLoading(false);
    }
  }, [filters.minConfidence, filters.relationshipClasses, filters.topK]);

  useEffect(() => {
    load();
  }, [load]);

  return {
    diagram,
    loading,
    error,
    filters,
    setFilters,
    reload: load,
  };
}
