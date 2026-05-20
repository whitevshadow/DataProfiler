import React, { useState, useEffect } from "react";
import type { ColumnInfo, EntityProperties, RelationshipEdge } from "./types";
import { useApp } from "./store";
import { fetchEntity, fetchRelationship } from "./api";

// ── Shared helpers ────────────────────────────────────────────
function QBar({ val }: { val: number }) {
  const cls = val >= 0.9 ? "quality-good" : val >= 0.7 ? "quality-mid" : "quality-bad";
  return (
    <div className="quality-bar-wrap">
      <div className="quality-bar" style={{ flex: 1 }}>
        <div className={`quality-bar-fill ${cls}`} style={{ width: `${val * 100}%` }} />
      </div>
      <span className="quality-val">{(val * 100).toFixed(1)}%</span>
    </div>
  );
}

function ConfRow({ label, val }: { label: string; val: number }) {
  return (
    <div className="conf-row">
      <span className="conf-label">{label}</span>
      <div className="conf-bar"><div className="conf-fill" style={{ width: `${val * 100}%` }} /></div>
      <span className="conf-val">{val.toFixed(3)}</span>
    </div>
  );
}

function PropCard({ label, val, colorClass = "" }: { label: string; val: React.ReactNode; colorClass?: string }) {
  return (
    <div className="prop-card">
      <div className="prop-card-label">{label}</div>
      <div className={`prop-card-val ${colorClass}`}>{val ?? "—"}</div>
    </div>
  );
}

// ── Column row with hover tooltip ─────────────────────────────
function ColumnRow({ col, isSelected, onClick }: { col: ColumnInfo; isSelected: boolean; onClick: () => void }) {
  const [showTip, setShowTip] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });

  return (
    <div
      className={`col-row${isSelected ? " selected" : ""}`}
      onClick={onClick}
      onMouseEnter={e => { setShowTip(true); setPos({ x: e.clientX, y: e.clientY }); }}
      onMouseLeave={() => setShowTip(false)}
    >
      <span className="col-name">{col.name}</span>
      {col.is_pk && <span className="col-pk">PK</span>}
      {col.is_fk && <span className="col-fk">FK</span>}
      <span className="col-type">{col.type}</span>
      <span style={{ fontSize: 10, color: col.null_ratio === 0 ? "var(--green)" : "var(--amber)", fontFamily: "var(--mono)" }}>
        {(col.null_ratio * 100).toFixed(0)}% null
      </span>

      {showTip && (
        <div
          className="fkrte-tooltip"
          style={{ left: Math.min(pos.x + 12, window.innerWidth - 300), top: pos.y - 10 }}
        >
          <div className="col-tt-header">{col.name}</div>
          <div className="col-tt-row"><span className="col-tt-label">Type</span><span className="col-tt-val">{col.type}</span></div>
          <div className="col-tt-row"><span className="col-tt-label">Semantic</span><span className="col-tt-val">{col.semantic_type || col.logical_type || "—"}</span></div>
          <div className="col-tt-row"><span className="col-tt-label">Cardinality</span><span className="col-tt-val">{col.cardinality || "—"}</span></div>
          <div className="col-tt-row"><span className="col-tt-label">Null Ratio</span><span className="col-tt-val">{(col.null_ratio * 100).toFixed(1)}%</span></div>
          <div className="col-tt-row"><span className="col-tt-label">Quality</span><span className="col-tt-val">{col.quality.toFixed(3)}</span></div>
          {col.top_values.length > 0 && (
            <div className="col-top-values">
              <div className="col-tt-label" style={{ marginBottom: 4, marginTop: 6 }}>Top Values</div>
              {col.top_values.slice(0, 5).map((v, i) => (
                <div key={i} className="col-top-val-item">· {v}</div>
              ))}
            </div>
          )}
          {col.quality_flags.length > 0 && (
            <div style={{ marginTop: 6 }}>
              {col.quality_flags.map(f => <span key={f} className="tag red" style={{ fontSize: 9, marginRight: 3 }}>{f}</span>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Entity Panel ──────────────────────────────────────────────
function EntityPanel({ entityId }: { entityId: string }) {
  const { state, dispatch, log } = useApp();
  const [loading, setLoading] = useState(false);
  const [showColumns, setShowColumns] = useState(false);

  const entity: EntityProperties | undefined = state.entityCache[entityId];

  useEffect(() => {
    if (!entity) {
      setLoading(true);
      fetchEntity(entityId)
        .then(d => { dispatch({ type: "CACHE_ENTITY", id: entityId, data: d }); setLoading(false); })
        .catch(() => setLoading(false));
    }
  }, [entityId]);

  if (loading || !entity) {
    return (
      <div style={{ padding: 20, textAlign: "center", color: "var(--text3)" }}>
        <span className="loading-pulse">Loading {entityId}…</span>
      </div>
    );
  }

  const related = [...(entity.related_children || []), ...(entity.related_parents || [])];

  return (
    <div className="panel-body scroll">
      {/* Title */}
      <div className="entity-title">
        <span>⬡</span>
        <span>{entity.label}</span>
        {entity.is_orphan && <span className="tag red" style={{ fontSize: 10 }}>ORPHAN</span>}
      </div>
      <div className="entity-subtitle">{entityId}</div>

      {/* Key metrics */}
      <div className="prop-section">
        <div className="prop-section-title">Overview</div>
        <div className="prop-grid">
          <PropCard label="Rows" val={entity.row_count?.toLocaleString() ?? "—"} colorClass="cyan" />
          <PropCard label="Columns" val={entity.column_count} />
          <PropCard label="FK Count" val={entity.fk_count} colorClass="cyan" />
          <PropCard label="Quality Flags" val={entity.quality_flags} colorClass={entity.quality_flags > 0 ? "amber" : "green"} />
          <div className="prop-card full">
            <div className="prop-card-label">Primary Key</div>
            <div className="prop-card-val amber">{entity.pk ?? "—"}</div>
          </div>
          <div className="prop-card full">
            <div className="prop-card-label">Quality Score</div>
            <div style={{ marginTop: 6 }}><QBar val={entity.quality_score} /></div>
          </div>
          <div className="prop-card full">
            <div className="prop-card-label">Completeness</div>
            <div style={{ marginTop: 6 }}><QBar val={entity.completeness} /></div>
          </div>
        </div>
      </div>

      {/* LCIL */}
      {entity.lcil_domains.length > 0 && (
        <div className="prop-section">
          <div className="prop-section-title">LCIL Domains</div>
          <div className="tag-list">
            {entity.lcil_domains.map(d => <span key={d} className="tag purple">{d}</span>)}
          </div>
        </div>
      )}

      {/* FK candidates */}
      {entity.fk_candidates.length > 0 && (
        <div className="prop-section">
          <div className="prop-section-title">FK Columns</div>
          <div className="tag-list">
            {entity.fk_candidates.map(c => <span key={c} className="tag cyan">{c}</span>)}
          </div>
        </div>
      )}

      {/* Related entities */}
      {related.length > 0 && (
        <div className="prop-section">
          <div className="prop-section-title">Related ({related.length})</div>
          <div className="tag-list">
            {entity.related_children.map(r => (
              <span key={r} className="tag cyan" style={{ cursor: "pointer" }}
                onClick={() => dispatch({ type: "SELECT_ENTITY", id: r })}>↘ {r}</span>
            ))}
            {entity.related_parents.map(r => (
              <span key={r} className="tag green" style={{ cursor: "pointer" }}
                onClick={() => dispatch({ type: "SELECT_ENTITY", id: r })}>↗ {r}</span>
            ))}
          </div>
        </div>
      )}

      {/* Columns */}
      <div className="prop-section">
        <div className="prop-section-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span>Columns ({entity.column_count})</span>
          <button
            className="collapse-btn"
            style={{ marginLeft: "auto", fontSize: 10 }}
            onClick={() => setShowColumns(v => !v)}
          >{showColumns ? "Hide" : "Expand"}</button>
        </div>
        {showColumns && (
          <div className="col-list">
            {entity.columns.map(col => (
              <ColumnRow
                key={col.key}
                col={col}
                isSelected={state.selectedColumnKey === col.key}
                onClick={() => dispatch({ type: "SELECT_COLUMN", key: col.key })}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Column detail panel ────────────────────────────────────────
function ColumnDetailPanel({ entityId, colKey }: { entityId: string; colKey: string }) {
  const { state } = useApp();
  const entity = state.entityCache[entityId];
  const col = entity?.columns.find(c => c.key === colKey);

  if (!col) return (
    <div className="panel-body">
      <div className="no-entity"><div className="icon">◈</div><p>Column not found</p></div>
    </div>
  );

  return (
    <div className="panel-body scroll">
      <div className="entity-title" style={{ fontSize: 15 }}>
        <span>◈</span><span style={{ fontFamily: "var(--mono)" }}>{col.name}</span>
        {col.is_pk && <span className="col-pk">PK</span>}
        {col.is_fk && <span className="col-fk">FK</span>}
      </div>
      <div className="entity-subtitle">in {entity?.label}</div>

      <div className="prop-section">
        <div className="prop-grid">
          <PropCard label="Type" val={col.type} />
          <PropCard label="Cardinality" val={col.cardinality || "—"} />
          <PropCard label="Null Ratio" val={`${(col.null_ratio * 100).toFixed(1)}%`}
            colorClass={col.null_ratio === 0 ? "green" : "amber"} />
          <PropCard label="Quality" val={col.quality.toFixed(3)} colorClass={col.quality >= 0.9 ? "green" : "amber"} />
          <div className="prop-card full">
            <div className="prop-card-label">Semantic / Logical Type</div>
            <div className="prop-card-val">{col.semantic_type || col.logical_type || "—"}</div>
          </div>
          <div className="prop-card full">
            <div className="prop-card-label">Relational Role</div>
            <div className="prop-card-val cyan">{col.relational_role || "—"}</div>
          </div>
        </div>
      </div>

      {col.top_values.length > 0 && (
        <div className="prop-section">
          <div className="prop-section-title">Top Values</div>
          <div className="tag-list">
            {col.top_values.map((v, i) => <span key={i} className="tag">{v}</span>)}
          </div>
        </div>
      )}

      {col.quality_flags.length > 0 && (
        <div className="prop-section">
          <div className="prop-section-title">Quality Flags</div>
          <div className="tag-list">
            {col.quality_flags.map(f => <span key={f} className="tag red">{f}</span>)}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Relationship Edge Panel ───────────────────────────────────
function EdgePanel({ edgeId }: { edgeId: string }) {
  const { state, dispatch } = useApp();
  const [loading, setLoading] = useState(false);
  const edge: RelationshipEdge | undefined = state.edgeCache[edgeId];

  useEffect(() => {
    if (!edge) {
      setLoading(true);
      fetchRelationship(edgeId)
        .then(d => { dispatch({ type: "CACHE_EDGE", id: edgeId, data: d }); setLoading(false); })
        .catch(() => setLoading(false));
    }
  }, [edgeId]);

  if (loading || !edge) return (
    <div className="panel-body"><div className="no-entity"><div className="icon">⟶</div><p className="loading-pulse">Loading relationship…</p></div></div>
  );

  // Parse evidence from reasoning
  const evidence = (edge.reasoning || []).filter(r =>
    !r.toLowerCase().includes("validated") &&
    !r.toLowerCase().includes("semantically related")
  );

  return (
    <div className="panel-body scroll">
      <div className="entity-title" style={{ fontSize: 14 }}>⟶ FK Relationship</div>
      <div className="edge-path" style={{ marginBottom: 14 }}>
        <span className="from">{edge.fk_table_label}.{edge.fk_column}</span>
        <span className="arrow">→</span>
        <span className="to">{edge.pk_table_label}.{edge.pk_column}</span>
      </div>

      <div className="prop-section">
        <div className="prop-section-title">Classification</div>
        <div className="tag-list">
          <span className="tag cyan">{edge.relationship_class}</span>
        </div>
      </div>

      <div className="prop-section">
        <div className="prop-section-title">Confidence Metrics</div>
        <ConfRow label="Confidence" val={edge.confidence} />
        <ConfRow label="Containment" val={edge.containment} />
        <ConfRow label="Semantic Sim." val={edge.semantic_similarity} />
      </div>

      {evidence.length > 0 && (
        <div className="prop-section">
          <div className="prop-section-title">Evidence</div>
          <div className="evidence-list">
            {evidence.map((r, i) => (
              <div key={i} className="evidence-item">{r}</div>
            ))}
          </div>
        </div>
      )}

      <div className="prop-section">
        <div className="prop-section-title">Tables</div>
        <div className="prop-grid">
          <div className="prop-card">
            <div className="prop-card-label">FK Table</div>
            <div className="prop-card-val cyan" style={{ fontSize: 12, cursor: "pointer", fontFamily: "var(--mono)" }}
              onClick={() => dispatch({ type: "SELECT_ENTITY", id: edge.fk_table })}>
              {edge.fk_table}
            </div>
            <div style={{ fontSize: 10, color: "var(--text3)", fontFamily: "var(--mono)", marginTop: 3 }}>.{edge.fk_column}</div>
          </div>
          <div className="prop-card">
            <div className="prop-card-label">PK Table</div>
            <div className="prop-card-val green" style={{ fontSize: 12, cursor: "pointer", fontFamily: "var(--mono)" }}
              onClick={() => dispatch({ type: "SELECT_ENTITY", id: edge.pk_table })}>
              {edge.pk_table}
            </div>
            <div style={{ fontSize: 10, color: "var(--text3)", fontFamily: "var(--mono)", marginTop: 3 }}>.{edge.pk_column}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Right Panel (property inspector) ─────────────────────────
export function RightPanel() {
  const { state } = useApp();
  const { activePanel } = state;

  const title = activePanel.mode === "entity" ? "Entity Inspector"
    : activePanel.mode === "relationship" ? "Relationship"
    : activePanel.mode === "column" ? "Column Detail"
    : "Property Inspector";

  return (
    <div className="fkrte-right">
      <div className="panel-hdr">
        <span style={{ color: "var(--cyan)", fontSize: 13 }}>
          {activePanel.mode === "relationship" ? "⟶" : activePanel.mode === "column" ? "◈" : "⊟"}
        </span>
        <h3>{title}</h3>
      </div>

      {activePanel.mode === "none" && (
        <div className="no-entity">
          <div className="icon">⊟</div>
          <p>Select a table or relationship to inspect its properties</p>
        </div>
      )}
      {activePanel.mode === "entity" && activePanel.entityId && (
        <EntityPanel entityId={activePanel.entityId} />
      )}
      {activePanel.mode === "relationship" && activePanel.edgeId && (
        <EdgePanel edgeId={activePanel.edgeId} />
      )}
      {activePanel.mode === "column" && activePanel.entityId && activePanel.columnKey && (
        <ColumnDetailPanel entityId={activePanel.entityId} colKey={activePanel.columnKey} />
      )}
    </div>
  );
}
