import React from "react";
import { useApp } from "./store";

export function BottomTrace() {
  const { state } = useApp();

  return (
    <div className="fkrte-bottom">
      <div className="trace-hdr">
        <span>▶</span>
        <span>Execution Trace</span>
        <span className="badge" style={{ marginLeft: 8 }}>{state.trace.length}</span>
      </div>
      <div className="trace-body">
        {state.trace.length === 0 && (
          <div style={{ color: "var(--text3)", fontSize: 11, padding: "6px 0" }}>
            No activity yet — interact with the tree to see trace entries
          </div>
        )}
        {state.trace.map((entry, i) => (
          <div key={i} className="trace-entry">
            <span className="trace-ts">{entry.ts}</span>
            <span className="trace-action">{entry.action}</span>
            <span className="trace-detail">{entry.detail}</span>
            <span className={`trace-badge ${entry.kind}`}>{entry.kind.toUpperCase()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
