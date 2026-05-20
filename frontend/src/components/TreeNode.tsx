/**
 * TreeNode
 * Collapsible tree node with expand/collapse and selection
 */
import React, { useState } from 'react';
import { TreeNode as TreeNodeType, expandEntity } from '../hooks/useTreeData';

interface TreeNodeProps {
  node: TreeNodeType;
  depth: number;
  visited: Set<string>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onExpand?: (nodeId: string) => void;
}

export function TreeNode({ node, depth, visited, selectedId, onSelect, onExpand }: TreeNodeProps) {
  const [expanded, setExpanded] = useState(node.expanded ?? false);
  const [children, setChildren] = useState<TreeNodeType[]>(node.children || []);
  const [loading, setLoading] = useState(false);

  const isSelected = selectedId === node.id;
  const hasChildren = node.has_children || children.length > 0;
  const isCycle = visited.has(node.id);

  const handleToggle = async () => {
    if (isCycle || !hasChildren) return;

    if (!expanded && children.length === 0) {
      // Lazy load children
      setLoading(true);
      try {
        const loaded = await expandEntity(node.id, Array.from(visited));
        setChildren(loaded);
        setExpanded(true);
        onExpand?.(node.id);
      } catch (err) {
        console.error('Failed to expand entity:', err);
      } finally {
        setLoading(false);
      }
    } else {
      setExpanded(!expanded);
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onSelect(node.id);
  };

  const newVisited = new Set(visited);
  newVisited.add(node.id);

  return (
    <div className="select-none">
      {/* Node row */}
      <div
        className={`
          flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer
          transition-colors group
          ${isSelected ? 'bg-blue-600/30 border border-blue-500/50' : 'hover:bg-gray-700/50'}
        `}
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
        onClick={handleClick}
      >
        {/* Expand/collapse icon */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            handleToggle();
          }}
          className={`
            flex-shrink-0 w-4 h-4 flex items-center justify-center
            text-gray-400 hover:text-white transition-colors
            ${!hasChildren || isCycle ? 'invisible' : ''}
          `}
          disabled={loading || !hasChildren || isCycle}
        >
          {loading ? (
            <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          ) : expanded ? (
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M19 9l-7 7-7-7" />
            </svg>
          ) : (
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M9 5l7 7-7 7" />
            </svg>
          )}
        </button>

        {/* Icon */}
        <div className={`flex-shrink-0 w-5 h-5 flex items-center justify-center ${isCycle ? 'text-yellow-400' : 'text-blue-400'}`}>
          {isCycle ? (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 10a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H4a1 1 0 01-1-1v-6zM14 9a1 1 0 00-1 1v6a1 1 0 001 1h2a1 1 0 001-1v-6a1 1 0 00-1-1h-2z" />
            </svg>
          )}
        </div>

        {/* Label */}
        <span className={`flex-1 text-sm font-medium ${isSelected ? 'text-white' : 'text-gray-300'}`}>
          {node.label}
        </span>

        {/* Edge badge */}
        {node.edge && (
          <div className="flex-shrink-0 group-hover:opacity-100 opacity-60 transition-opacity">
            <div className="px-2 py-0.5 bg-green-500/20 border border-green-500/30 rounded text-xs text-green-300 font-mono">
              {node.edge.fk_column} → {node.edge.pk_column}
            </div>
          </div>
        )}

        {/* Cycle badge */}
        {isCycle && (
          <div className="px-2 py-0.5 bg-yellow-500/20 border border-yellow-500/30 rounded text-xs text-yellow-300">
            cycle
          </div>
        )}

        {/* Truncated badge */}
        {node.truncated && (
          <div className="px-2 py-0.5 bg-gray-500/20 border border-gray-500/30 rounded text-xs text-gray-400">
            …
          </div>
        )}
      </div>

      {/* Children */}
      {expanded && children.length > 0 && (
        <div>
          {children.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              visited={newVisited}
              selectedId={selectedId}
              onSelect={onSelect}
              onExpand={onExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
}
