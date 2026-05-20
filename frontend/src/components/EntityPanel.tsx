/**
 * EntityPanel
 * Right-side property inspector for selected entity
 */
import React from 'react';
import { useEntityDetail, EntityDetail } from '../hooks/useTreeData';

interface EntityPanelProps {
  entityId: string | null;
  onClose: () => void;
}

export function EntityPanel({ entityId, onClose }: EntityPanelProps) {
  const { entity, loading, error } = useEntityDetail(entityId);

  if (!entityId) {
    return (
      <div className="w-96 border-l border-gray-700 bg-gray-900 flex items-center justify-center text-gray-500">
        Select an entity to view properties
      </div>
    );
  }

  if (loading) {
    return (
      <div className="w-96 border-l border-gray-700 bg-gray-900 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-96 border-l border-gray-700 bg-gray-900 p-6">
        <div className="bg-red-900/20 border border-red-500/30 rounded p-4 text-red-400">
          Error: {error}
        </div>
      </div>
    );
  }

  if (!entity) return null;

  return (
    <div className="w-96 border-l border-gray-700 bg-gray-900 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b border-gray-700 p-4 flex justify-between items-start">
        <div>
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Entity</div>
          <h2 className="text-xl font-semibold text-white">{entity.label}</h2>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-white transition-colors"
          title="Close panel"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Core Metrics */}
        <section>
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Metrics</h3>
          <div className="grid grid-cols-2 gap-4">
            <MetricCard label="Rows" value={entity.row_count?.toLocaleString() ?? 'N/A'} />
            <MetricCard label="Columns" value={entity.column_count} />
            <MetricCard label="Quality" value={(entity.quality_score * 100).toFixed(1) + '%'} color={getQualityColor(entity.quality_score)} />
            <MetricCard label="FK Count" value={entity.fk_count} />
          </div>
        </section>

        {/* Primary Key */}
        {entity.pk && (
          <section>
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">Primary Key</h3>
            <div className="bg-gray-800 border border-gray-700 rounded p-3">
              <div className="text-white font-mono text-sm">{entity.pk}</div>
              <div className="text-xs text-gray-500 mt-1">
                Confidence: {(entity.pk_confidence * 100).toFixed(1)}%
              </div>
            </div>
          </section>
        )}

        {/* Relationships */}
        {(entity.related_children.length > 0 || entity.related_parents.length > 0) && (
          <section>
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">Relationships</h3>
            
            {entity.related_children.length > 0 && (
              <div className="mb-3">
                <div className="text-xs text-gray-500 mb-1">Children ({entity.related_children.length})</div>
                <div className="space-y-1">
                  {entity.related_children.map((child, idx) => (
                    <div key={idx} className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white font-mono">
                      {child}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {entity.related_parents.length > 0 && (
              <div>
                <div className="text-xs text-gray-500 mb-1">Parents ({entity.related_parents.length})</div>
                <div className="space-y-1">
                  {entity.related_parents.map((parent, idx) => (
                    <div key={idx} className="bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-white font-mono">
                      {parent}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        {/* LCIL Domains */}
        {entity.lcil_domains && entity.lcil_domains.length > 0 && (
          <section>
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">LCIL Domains</h3>
            <div className="flex flex-wrap gap-2">
              {entity.lcil_domains.map((domain, idx) => (
                <span
                  key={idx}
                  className="px-2 py-1 bg-purple-500/20 border border-purple-500/30 rounded text-xs text-purple-300"
                >
                  {domain}
                </span>
              ))}
            </div>
          </section>
        )}

        {/* Columns */}
        {entity.columns && entity.columns.length > 0 && (
          <section>
            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">
              Columns ({entity.columns.length})
            </h3>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {entity.columns.map((col, idx) => (
                <div key={idx} className="bg-gray-800 border border-gray-700 rounded p-3">
                  <div className="flex items-start justify-between mb-1">
                    <span className="text-white font-mono text-sm">{col.name}</span>
                    <div className="flex gap-1">
                      {col.is_pk && (
                        <span className="px-1.5 py-0.5 bg-yellow-500/20 border border-yellow-500/30 rounded text-xs text-yellow-300">
                          PK
                        </span>
                      )}
                      {col.is_fk && (
                        <span className="px-1.5 py-0.5 bg-blue-500/20 border border-blue-500/30 rounded text-xs text-blue-300">
                          FK
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-xs text-gray-400 space-y-0.5">
                    <div>Type: {col.type}</div>
                    {col.semantic_type && <div>Semantic: {col.semantic_type}</div>}
                    <div>Cardinality: {col.cardinality}</div>
                    <div>Null: {(col.null_ratio * 100).toFixed(1)}%</div>
                    <div>Quality: {(col.quality * 100).toFixed(1)}%</div>
                    {col.top_values && col.top_values.length > 0 && (
                      <div>
                        Top: {col.top_values.slice(0, 3).join(', ')}
                        {col.top_values.length > 3 && '...'}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Flags */}
        {entity.is_orphan && (
          <section>
            <div className="bg-yellow-900/20 border border-yellow-500/30 rounded p-3 text-yellow-300 text-sm">
              ⚠️ Orphan table (no FK relationships)
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function MetricCard({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded p-3">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-lg font-semibold ${color || 'text-white'}`}>
        {value}
      </div>
    </div>
  );
}

function getQualityColor(score: number): string {
  if (score >= 0.9) return 'text-green-400';
  if (score >= 0.7) return 'text-yellow-400';
  return 'text-red-400';
}
