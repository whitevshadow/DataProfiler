import React from "react";

type Props = { enabled: boolean; tableCount: number };

export function DBMLMiniMap({ enabled, tableCount }: Props) {
  if (!enabled) return null;
  return <div className="dbml-minimap">MiniMap: {tableCount} nodes</div>;
}
