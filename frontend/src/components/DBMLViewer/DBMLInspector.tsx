import React, { useState, useEffect } from 'react';
import { DBGraph, getNode, getNodeEdges } from './DBMLParser';

interface DBMLInspectorProps {
  graph: DBGraph;
  nodeId: string;
  onClose: () => void;
}

interface EntityDetails {
  profile?: any;
  quality?: any;
  pk?: any;
  lcil?: any;
}

const DBMLInspector: React.FC<DBMLInspectorProps> = ({ graph, nodeId, onClose }) => {
  const [details, setDetails] = useState<EntityDetails>({});
  const [loading, setLoading] = useState(false);
  
  const node = getNode(graph, nodeId);
  const edges = getNodeEdges(graph, nodeId);

  useEffect(() => {
    const loadDetails = async () => {
      setLoading(true);
      try {
        const response = await fetch(`/api/entity/${nodeId}`);
        if (response.ok) {
          const data = await response.json();
          setDetails(data);
        }
      } catch (err) {
        console.error('Failed to load entity details:', err);
      } finally {
        setLoading(false);
      }
    };
    
    loadDetails();
  }, [nodeId]);

  if (!node) return null;

  const pkColumns = node.columns.filter(col => col.pk);
  const fkColumns = node.columns.filter(col => col.fk);
  const regularColumns = node.columns.filter(col => !col.pk && !col.fk);
  
  const incomingEdges = edges.filter(e => e.to === nodeId);
  const outgoingEdges = edges.filter(e => e.from === nodeId);

  return (
    <div className="dbml-inspector">
      <div className="inspector-header">
        <h3>{node.name}</h3>
        <button onClick={onClose} className="close-btn">✕</button>
      </div>
      
      <div className="inspector-content">
        {loading && <div className="loading">Loading details...</div>}
        
        <section className="inspector-section">
          <h4>Overview</h4>
          <div className="info-row">
            <span className="label">Table:</span>
            <span className="value">{node.name}</span>
          </div>
          <div className="info-row">
            <span className="label">Columns:</span>
            <span className="value">{node.columns.length}</span>
          </div>
          <div className="info-row">
            <span className="label">Primary Keys:</span>
            <span className="value">{pkColumns.length}</span>
          </div>
          <div className="info-row">
            <span className="label">Foreign Keys:</span>
            <span className="value">{fkColumns.length}</span>
          </div>
          {details.profile && (
            <div className="info-row">
              <span className="label">Row Count:</span>
              <span className="value">{details.profile.row_count_estimate?.toLocaleString()}</span>
            </div>
          )}
          {details.quality && (
            <div className="info-row">
              <span className="label">Quality Score:</span>
              <span className="value quality-score">{(details.quality.overall_score * 100).toFixed(1)}%</span>
            </div>
          )}
        </section>
        
        {pkColumns.length > 0 && (
          <section className="inspector-section">
            <h4>Primary Keys</h4>
            {pkColumns.map(col => (
              <div key={col.name} className="column-detail">
                <div className="column-header">
                  <span className="icon">🔑</span>
                  <span className="col-name">{col.name}</span>
                  <span className="col-type">{col.type}</span>
                </div>
                {col.note && <div className="col-note">{col.note}</div>}
              </div>
            ))}
          </section>
        )}
        
        {fkColumns.length > 0 && (
          <section className="inspector-section">
            <h4>Foreign Keys</h4>
            {fkColumns.map(col => (
              <div key={col.name} className="column-detail">
                <div className="column-header">
                  <span className="icon">🔗</span>
                  <span className="col-name">{col.name}</span>
                  <span className="col-type">{col.type}</span>
                </div>
                {col.fk && <div className="col-note">References: {col.fk}</div>}
              </div>
            ))}
          </section>
        )}
        
        {edges.length > 0 && (
          <section className="inspector-section">
            <h4>Relationships</h4>
            {outgoingEdges.length > 0 && (
              <div>
                <div className="rel-section-title">References (→)</div>
                {outgoingEdges.map(edge => (
                  <div key={edge.id} className="relationship-item">
                    <span className="rel-icon">→</span>
                    <span>{edge.fromColumn} → {edge.to}.{edge.toColumn}</span>
                  </div>
                ))}
              </div>
            )}
            {incomingEdges.length > 0 && (
              <div>
                <div className="rel-section-title">Referenced By (←)</div>
                {incomingEdges.map(edge => (
                  <div key={edge.id} className="relationship-item">
                    <span className="rel-icon">←</span>
                    <span>{edge.from}.{edge.fromColumn} → {edge.toColumn}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
        
        {regularColumns.length > 0 && (
          <section className="inspector-section">
            <h4>Columns ({regularColumns.length})</h4>
            <div className="columns-list">
              {regularColumns.map(col => (
                <div key={col.name} className="column-detail">
                  <div className="column-header">
                    <span className="icon">·</span>
                    <span className="col-name">{col.name}</span>
                    <span className="col-type">{col.type}</span>
                  </div>
                  {col.note && <div className="col-note">{col.note}</div>}
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
      
      <style jsx>{`
        .dbml-inspector {
          width: 320px;
          background: white;
          border-left: 1px solid #e0e0e0;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        
        .inspector-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px;
          border-bottom: 1px solid #e0e0e0;
          background: #f5f5f5;
        }
        
        .inspector-header h3 {
          margin: 0;
          font-size: 16px;
          font-weight: 600;
        }
        
        .close-btn {
          background: none;
          border: none;
          font-size: 20px;
          cursor: pointer;
          padding: 4px 8px;
          color: #666;
        }
        
        .close-btn:hover {
          color: #000;
        }
        
        .inspector-content {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
        }
        
        .loading {
          padding: 20px;
          text-align: center;
          color: #666;
        }
        
        .inspector-section {
          margin-bottom: 20px;
        }
        
        .inspector-section h4 {
          margin: 0 0 12px 0;
          font-size: 14px;
          font-weight: 600;
          color: #333;
        }
        
        .info-row {
          display: flex;
          justify-content: space-between;
          padding: 6px 0;
          font-size: 13px;
          border-bottom: 1px solid #f5f5f5;
        }
        
        .label {
          color: #666;
        }
        
        .value {
          font-weight: 500;
        }
        
        .quality-score {
          color: #4caf50;
        }
        
        .column-detail {
          padding: 8px;
          background: #f9f9f9;
          border-radius: 4px;
          margin-bottom: 8px;
        }
        
        .column-header {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
        }
        
        .icon {
          width: 20px;
          text-align: center;
        }
        
        .col-name {
          flex: 1;
          font-weight: 500;
        }
        
        .col-type {
          color: #888;
          font-size: 11px;
        }
        
        .col-note {
          margin-top: 4px;
          padding-left: 28px;
          font-size: 12px;
          color: #666;
          font-style: italic;
        }
        
        .rel-section-title {
          font-size: 12px;
          font-weight: 600;
          color: #666;
          margin: 8px 0 4px 0;
        }
        
        .relationship-item {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 8px;
          background: #f9f9f9;
          border-radius: 4px;
          margin-bottom: 4px;
          font-size: 12px;
        }
        
        .rel-icon {
          color: #2196f3;
        }
        
        .columns-list {
          max-height: 300px;
          overflow-y: auto;
        }
      `}</style>
    </div>
  );
};

export default DBMLInspector;
