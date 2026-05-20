import React from "react";

type Props = {
  zoom: number;
  minimap: boolean;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onToggleMiniMap: () => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  onFullscreen: () => void;
  onExportPng: () => void;
  onSearch: (value: string) => void;
};

export function DBMLToolbar(props: Props) {
  return (
    <div className="dbml-toolbar">
      <button onClick={props.onZoomIn}>Zoom +</button>
      <button onClick={props.onZoomOut}>Zoom -</button>
      <button onClick={props.onFit}>Fit</button>
      <button onClick={props.onToggleMiniMap}>MiniMap {props.minimap ? "On" : "Off"}</button>
      <button onClick={props.onExpandAll}>Expand</button>
      <button onClick={props.onCollapseAll}>Collapse</button>
      <button onClick={props.onFullscreen}>Fullscreen</button>
      <button onClick={props.onExportPng}>Export PNG</button>
      <input placeholder="Search" onChange={(e) => props.onSearch(e.target.value)} />
      <span>{Math.round(props.zoom * 100)}%</span>
    </div>
  );
}
