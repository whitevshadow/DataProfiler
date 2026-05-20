import React from "react";

type Props = { tables: number; relationships: number; zoom: number };

export function DBMLStatusBar({ tables, relationships, zoom }: Props) {
  return (
    <div className="dbml-statusbar">
      <span>Timeline / Status / Metrics</span>
      <span>{tables} tables</span>
      <span>{relationships} relationships</span>
      <span>zoom {(zoom * 100).toFixed(0)}%</span>
    </div>
  );
}
