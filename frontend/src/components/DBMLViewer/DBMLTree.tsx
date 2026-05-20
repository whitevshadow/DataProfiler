import React from 'react';
import { DBGraph, DBNode, getNodeEdges } from './DBMLParser';

interface DBMLTreeProps {
  graph: DBGraph;
  expandedNodes: Set<string>;
  selectedNode: string | null;
  onNodeSelect: (nodeId: string) => void;
  onNodeExpand: (nodeId: string) => void;
  searchQuery: string;
}

const DBMLTree: React.FC<DBMLTreeProps> = ({
  graph,
  expandedNodes,
  selectedNode,
  onNodeSelect,
  onNodeExpand,
  searchQuery
}) => {
  const filteredNodes = searchQuery
    ? graph.nodes.filter(node =>
        node.name.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : graph.nodes;

  const renderNode = (node: DBNode) => {
    const isExpanded = expandedNodes.has(node.id);
    const isSelected = selectedNode === node.id;
    const edges = getNodeEdges(graph, node.id);
    const hasRelationships = edges.length > 0;
    
    return (
      <div key={node.id} className={`tree-node ${isSelected ? 'selected' : ''}`}>
        <div
          className="tree-node-header"
          onClick={() => onNodeSelect(node.id)}
        >
          {hasRelationships && (
            <span
              className="expand-icon"
              onClick={(e) => {
                e.stopPropagation();
                onNodeExpand(node.id);
              }}
            >
              {isExpanded ? '▼' : '▶'}
            </span>
          )}
          <span className="table-icon">◈</span>
          <span className="node-name">{node.name}</span>
          <span className="column-count">{node.columns.length}</span>
        </div>
        
        {isExpanded && (
          <div className="tree-node-columns">
            {node.columns.map(col => (
              <div key={col.name} className="column-item">
                <span className="column-icon">
                  {col.pk ? '🔑' : col.fk ? '🔗' : '·'}
                </span>
                <span className="column-name">{col.name}</span>
                <span className="column-type">{col.type}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="dbml-tree">
      <div className="tree-header">
        <h3>Tables</h3>
        <span className="table-count">{filteredNodes.length}</span>
      </div>
      
      <div className="tree-nodes">
        {filteredNodes.map(renderNode)}
      </div>
      
      <style jsx>{`
        .dbml-tree {
          width: 280px;
          background: white;
          border-right: 1px solid #e0e0e0;
          display: flex;
          flex-direction: column;
          overflow-y: auto;
        }
        
        .tree-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px;
          border-bottom: 1px solid #e0e0e0;
        }
        
        .tree-header h3 {
          margin: 0;
          font-size: 16px;
          font-weight: 600;
        }
        
        .table-count {
          background: #e0e0e0;
          padding: 2px 8px;
          border-radius: 12px;
          font-size: 12px;
        }
        
        .tree-nodes {
          flex: 1;
          overflow-y: auto;
        }
        
        .tree-node {
          border-bottom: 1px solid #f0f0f0;
        }
        
        .tree-node-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px 16px;
          cursor: pointer;
          transition: background 0.2s;
        }
        
        .tree-node-header:hover {
          background: #f5f5f5;
        }
        
        .tree-node.selected .tree-node-header {
          background: #e3f2fd;
        }
        
        .expand-icon {
          font-size: 10px;
          width: 16px;
          text-align: center;
          cursor: pointer;
        }
        
        .table-icon {
          color: #2196f3;
        }
        
        .node-name {
          flex: 1;
          font-weight: 500;
        }
        
        .column-count {
          font-size: 12px;
          color: #666;
        }
        
        .tree-node-columns {
          padding-left: 40px;
          padding-right: 16px;
          padding-bottom: 8px;
        }
        
        .column-item {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 4px 0;
          font-size: 13px;
        }
        
        .column-icon {
          width: 16px;
          text-align: center;
        }
        
        .column-name {
          flex: 1;
        }
        
        .column-type {
          font-size: 11px;
          color: #888;
        }
      `}</style>
    </div>
  );
};

export default DBMLTree;
