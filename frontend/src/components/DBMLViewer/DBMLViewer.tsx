import React, { useState, useEffect } from 'react';
import { DBGraph, parseDBML } from './DBMLParser';
import DBMLCanvas from './DBMLCanvas';
import DBMLToolbar from './DBMLToolbar';
import DBMLTree from './DBMLTree';
import DBMLInspector from './DBMLInspector';

interface DBMLViewerProps {
  dbmlContent?: string;
  onClose?: () => void;
}

const DBMLViewer: React.FC<DBMLViewerProps> = ({ dbmlContent, onClose }) => {
  const [graph, setGraph] = useState<DBGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [zoom, setZoom] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');

  // Load DBML content
  useEffect(() => {
    const loadDBML = async () => {
      try {
        setLoading(true);
        
        let content = dbmlContent;
        
        // If no content provided, fetch from API
        if (!content) {
          const response = await fetch('/api/dbml');
          if (!response.ok) {
            throw new Error('Failed to load DBML');
          }
          content = await response.text();
        }
        
        // Parse DBML
        const parsedGraph = parseDBML(content);
        setGraph(parsedGraph);
        
        // Save to cache
        await fetch('/api/dbml/render', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(parsedGraph)
        });
        
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load DBML');
      } finally {
        setLoading(false);
      }
    };
    
    loadDBML();
  }, [dbmlContent]);

  const handleNodeSelect = (nodeId: string) => {
    setSelectedNodeId(nodeId);
  };

  const handleNodeExpand = (nodeId: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  const handleExpandAll = () => {
    if (graph) {
      setExpandedNodes(new Set(graph.nodes.map(n => n.id)));
    }
  };

  const handleCollapseAll = () => {
    setExpandedNodes(new Set());
  };

  const handleZoomIn = () => {
    setZoom(prev => Math.min(prev + 0.2, 3));
  };

  const handleZoomOut = () => {
    setZoom(prev => Math.max(prev - 0.2, 0.5));
  };

  const handleFit = () => {
    setZoom(1);
  };

  if (loading) {
    return (
      <div className="dbml-viewer-loading">
        <div className="spinner" />
        <p>Loading schema...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dbml-viewer-error">
        <p>Error: {error}</p>
        <button onClick={onClose}>Close</button>
      </div>
    );
  }

  if (!graph) {
    return <div>No schema available</div>;
  }

  return (
    <div className="dbml-viewer">
      <DBMLToolbar
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        onFit={handleFit}
        onExpandAll={handleExpandAll}
        onCollapseAll={handleCollapseAll}
        onSearch={setSearchQuery}
        onClose={onClose}
        zoom={zoom}
      />
      
      <div className="dbml-viewer-content">
        <DBMLTree
          graph={graph}
          expandedNodes={expandedNodes}
          selectedNode={selectedNodeId}
          onNodeSelect={handleNodeSelect}
          onNodeExpand={handleNodeExpand}
          searchQuery={searchQuery}
        />
        
        <DBMLCanvas
          graph={graph}
          expandedNodes={expandedNodes}
          selectedNode={selectedNodeId}
          zoom={zoom}
          searchQuery={searchQuery}
          onNodeSelect={handleNodeSelect}
          onNodeExpand={handleNodeExpand}
        />
        
        {selectedNodeId && (
          <DBMLInspector
            graph={graph}
            nodeId={selectedNodeId}
            onClose={() => setSelectedNodeId(null)}
          />
        )}
      </div>
      
      <style jsx>{`
        .dbml-viewer {
          display: flex;
          flex-direction: column;
          height: 600px;
          background: #f5f5f5;
          border-radius: 8px;
          overflow: hidden;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .dbml-viewer-content {
          display: flex;
          flex: 1;
          overflow: hidden;
        }
        
        .dbml-viewer-loading,
        .dbml-viewer-error {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 400px;
          padding: 20px;
        }
        
        .spinner {
          border: 3px solid #f3f3f3;
          border-top: 3px solid #3498db;
          border-radius: 50%;
          width: 40px;
          height: 40px;
          animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default DBMLViewer;
