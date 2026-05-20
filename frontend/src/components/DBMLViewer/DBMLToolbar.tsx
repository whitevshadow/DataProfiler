import React from 'react';

interface DBMLToolbarProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  onSearch: (query: string) => void;
  onClose?: () => void;
  zoom: number;
}

const DBMLToolbar: React.FC<DBMLToolbarProps> = ({
  onZoomIn,
  onZoomOut,
  onFit,
  onExpandAll,
  onCollapseAll,
  onSearch,
  onClose,
  zoom
}) => {
  return (
    <div className="dbml-toolbar">
      <div className="toolbar-group">
        <button onClick={onZoomIn} title="Zoom In">
          <span>+</span>
        </button>
        <span className="zoom-indicator">{Math.round(zoom * 100)}%</span>
        <button onClick={onZoomOut} title="Zoom Out">
          <span>−</span>
        </button>
        <button onClick={onFit} title="Fit to Screen">
          <span>⊡</span>
        </button>
      </div>
      
      <div className="toolbar-group">
        <button onClick={onExpandAll} title="Expand All">
          <span>▼</span> Expand
        </button>
        <button onClick={onCollapseAll} title="Collapse All">
          <span>▶</span> Collapse
        </button>
      </div>
      
      <div className="toolbar-group search-group">
        <input
          type="text"
          placeholder="Search tables..."
          onChange={(e) => onSearch(e.target.value)}
          className="search-input"
        />
      </div>
      
      {onClose && (
        <div className="toolbar-group">
          <button onClick={onClose} className="close-btn" title="Close">
            <span>✕</span>
          </button>
        </div>
      )}
      
      <style jsx>{`
        .dbml-toolbar {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 16px;
          background: white;
          border-bottom: 1px solid #e0e0e0;
        }
        
        .toolbar-group {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        
        .toolbar-group button {
          padding: 6px 12px;
          background: #f0f0f0;
          border: 1px solid #d0d0d0;
          border-radius: 4px;
          cursor: pointer;
          font-size: 14px;
          transition: all 0.2s;
        }
        
        .toolbar-group button:hover {
          background: #e0e0e0;
        }
        
        .zoom-indicator {
          font-size: 12px;
          color: #666;
          min-width: 45px;
          text-align: center;
        }
        
        .search-group {
          flex: 1;
          justify-content: center;
        }
        
        .search-input {
          padding: 6px 12px;
          border: 1px solid #d0d0d0;
          border-radius: 4px;
          font-size: 14px;
          width: 300px;
        }
        
        .close-btn {
          background: #ff4444 !important;
          color: white;
          border-color: #cc0000 !important;
        }
        
        .close-btn:hover {
          background: #cc0000 !important;
        }
      `}</style>
    </div>
  );
};

export default DBMLToolbar;
