/**
 * FKRTreeExplorer
 * Main FK Relationship Tree Explorer component
 * Interactive database navigation via TRUE_FK relationships
 */
import React, { useState } from 'react';
import { useTreeData } from '../hooks/useTreeData';
import { TreeNode } from './TreeNode';
import { EntityPanel } from './EntityPanel';

export function FKRTreeExplorer() {
  const { tree, stats, loading, error, reload } = useTreeData();
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const handleRefresh = () => {
    reload(true);
    setSelectedEntity(null);
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-950">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <div className="text-gray-400">Loading FK relationship tree...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-950">
        <div className="max-w-md">
          <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-6">
            <h3 className="text-red-400 font-semibold text-lg mb-2">Error Loading Tree</h3>
            <p className="text-red-300 text-sm mb-4">{error}</p>
            <button
              onClick={() => reload()}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex overflow-hidden bg-gray-950">
      {/* Left: Tree Navigation */}
      <div className="flex-1 flex flex-col overflow-hidden border-r border-gray-700">
        {/* Header */}
        <div className="border-b border-gray-700 bg-gray-900 p-4">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-xl font-bold text-white mb-1">FK Relationship Explorer</h1>
              <p className="text-sm text-gray-400">Navigate your database using foreign key relationships</p>
            </div>
            <button
              onClick={handleRefresh}
              className="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors text-sm flex items-center gap-2"
              title="Rebuild tree from source files"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Rebuild
            </button>
          </div>

          {/* Stats */}
          {stats && (
            <div className="flex gap-4 text-xs">
              <div className="flex items-center gap-1.5">
                <span className="text-gray-500">Tables:</span>
                <span className="text-white font-semibold">{stats.total_tables}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-gray-500">TRUE_FK:</span>
                <span className="text-white font-semibold">{stats.true_fk_count}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-gray-500">Roots:</span>
                <span className="text-white font-semibold">{stats.root_nodes}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-gray-500">Orphans:</span>
                <span className="text-yellow-400 font-semibold">{stats.orphan_tables}</span>
              </div>
            </div>
          )}

          {/* Search */}
          <div className="mt-4">
            <div className="relative">
              <input
                type="text"
                placeholder="Search tables, columns, PKs..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full px-3 py-2 pl-9 bg-gray-800 border border-gray-700 rounded text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
              />
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>
        </div>

        {/* Tree Content */}
        <div className="flex-1 overflow-y-auto p-4 bg-gray-950">
          {tree.length === 0 ? (
            <div className="text-center py-12">
              <svg className="w-16 h-16 mx-auto mb-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
              </svg>
              <h3 className="text-lg font-semibold text-gray-400 mb-2">No Tables Found</h3>
              <p className="text-sm text-gray-500 mb-4">
                Run the profiling pipeline first to generate relationship data.
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {tree.map((node) => (
                <TreeNode
                  key={node.id}
                  node={node}
                  depth={0}
                  visited={new Set()}
                  selectedId={selectedEntity}
                  onSelect={setSelectedEntity}
                />
              ))}
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="border-t border-gray-700 bg-gray-900 p-3">
          <div className="flex items-center gap-4 text-xs text-gray-400">
            <div className="flex items-center gap-1.5">
              <svg className="w-4 h-4 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z" />
              </svg>
              <span>Table</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="px-2 py-0.5 bg-green-500/20 border border-green-500/30 rounded text-xs text-green-300 font-mono">
                FK → PK
              </div>
              <span>TRUE_FK</span>
            </div>
            <div className="flex items-center gap-1.5">
              <svg className="w-4 h-4 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span>Cycle Detected</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right: Entity Properties */}
      <EntityPanel
        entityId={selectedEntity}
        onClose={() => setSelectedEntity(null)}
      />
    </div>
  );
}
