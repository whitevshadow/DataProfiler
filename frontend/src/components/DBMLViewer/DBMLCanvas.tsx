import React, { useRef, useEffect } from 'react';
import { DBGraph, getNode, getNodeEdges } from './DBMLParser';

interface DBMLCanvasProps {
  graph: DBGraph;
  expandedNodes: Set<string>;
  selectedNode: string | null;
  zoom: number;
  searchQuery: string;
  onNodeSelect: (nodeId: string) => void;
  onNodeExpand: (nodeId: string) => void;
}

const DBMLCanvas: React.FC<DBMLCanvasProps> = ({
  graph,
  expandedNodes,
  selectedNode,
  zoom,
  searchQuery,
  onNodeSelect,
  onNodeExpand
}) => {
  const canvasRef = useRef<HTMLDivElement>(null);
  
  // Filter nodes based on search
  const visibleNodes = searchQuery
    ? graph.nodes.filter(node =>
        node.name.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : graph.nodes;

  // Simple layout: arrange nodes in a grid
  const layout = visibleNodes.map((node, index) => {
    const cols = Math.ceil(Math.sqrt(visibleNodes.length));
    const row = Math.floor(index / cols);
    const col = index % cols;
    
    return {
      node,
      x: col * 300 + 50,
      y: row * 200 + 50
    };
  });

  const renderNode = (nodeId: string, x: number, y: number) => {
    const node = getNode(graph, nodeId);
    if (!node) return null;
    
    const isExpanded = expandedNodes.has(nodeId);
    const isSelected = selectedNode === nodeId;
    const edges = getNodeEdges(graph, nodeId);
    
    return (
      <div
        key={nodeId}
        className={`canvas-node ${isSelected ? 'selected' : ''} ${searchQuery && node.name.toLowerCase().includes(searchQuery.toLowerCase()) ? 'highlighted' : ''}`}
        style={{
          left: x,
          top: y,
          transform: `scale(${zoom})`
        }}
        onClick={() => onNodeSelect(nodeId)}
        onDoubleClick={() => onNodeExpand(nodeId)}
      >
        <div className="node-header">
          <span className="table-icon">◈</span>
          <span className="node-title">{node.name}</span>
          {edges.length > 0 && (
            <span className="edge-count">{edges.length}</span>
          )}
        </div>
        
        {isExpanded && (
          <div className="node-columns">
            {node.columns.map(col => (
              <div key={col.name} className="column-row">
                <span className="col-icon">
                  {col.pk ? '🔑' : col.fk ? '🔗' : '·'}
                </span>
                <span className="col-name">{col.name}</span>
                <span className="col-type">{col.type}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="dbml-canvas" ref={canvasRef}>
      <svg className="connections-layer">
        {/* Render edges/relationships */}
        {graph.edges.map(edge => {
          const fromLayout = layout.find(l => l.node.id === edge.from);
          const toLayout = layout.find(l => l.node.id === edge.to);
          
          if (!fromLayout || !toLayout) return null;
          
          const x1 = fromLayout.x + 140;
          const y1 = fromLayout.y + 40;
          const x2 = toLayout.x + 140;
          const y2 = toLayout.y + 40;
          
          return (
            <line
              key={edge.id}
              x1={x1 * zoom}
              y1={y1 * zoom}
              x2={x2 * zoom}
              y2={y2 * zoom}
              stroke="#2196f3"
              strokeWidth="2"
              strokeDasharray="5,5"
              opacity="0.6"
            />
          );
        })}
      </svg>
      
      <div className="nodes-layer">
        {layout.map(({ node, x, y }) => renderNode(node.id, x, y))}
      </div>
      
      <style jsx>{`
        .dbml-canvas {
          flex: 1;
          position: relative;
          overflow: auto;
          background: #fafafa;
        }
        
        .connections-layer {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
        }
        
        .nodes-layer {
          position: relative;
          min-width: 100%;
          min-height: 100%;
        }
        
        .canvas-node {
          position: absolute;
          width: 280px;
          background: white;
          border: 2px solid #e0e0e0;
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s;
          transform-origin: top left;
        }
        
        .canvas-node:hover {
          border-color: #2196f3;
          box-shadow: 0 4px 12px rgba(33, 150, 243, 0.2);
        }
        
        .canvas-node.selected {
          border-color: #2196f3;
          box-shadow: 0 4px 12px rgba(33, 150, 243, 0.3);
        }
        
        .canvas-node.highlighted {
          border-color: #ff9800;
          box-shadow: 0 4px 12px rgba(255, 152, 0, 0.3);
        }
        
        .node-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 12px;
          background: #f5f5f5;
          border-bottom: 1px solid #e0e0e0;
          border-radius: 6px 6px 0 0;
        }
        
        .table-icon {
          color: #2196f3;
          font-size: 18px;
        }
        
        .node-title {
          flex: 1;
          font-weight: 600;
          font-size: 14px;
        }
        
        .edge-count {
          background: #2196f3;
          color: white;
          padding: 2px 6px;
          border-radius: 10px;
          font-size: 11px;
        }
        
        .node-columns {
          padding: 8px;
          max-height: 300px;
          overflow-y: auto;
        }
        
        .column-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 4px;
          font-size: 13px;
          border-bottom: 1px solid #f5f5f5;
        }
        
        .column-row:last-child {
          border-bottom: none;
        }
        
        .col-icon {
          width: 16px;
          text-align: center;
        }
        
        .col-name {
          flex: 1;
        }
        
        .col-type {
          font-size: 11px;
          color: #888;
        }
      `}</style>
    </div>
  );
};

export default DBMLCanvas;
