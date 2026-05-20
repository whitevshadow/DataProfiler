import { TraceEvent } from "../types";

type ExecutionTraceProps = {
  events: TraceEvent[];
};

export function ExecutionTrace({ events }: ExecutionTraceProps) {
  if (!events.length) {
    return <div className="text-xs text-slate-500">Waiting for pipeline events...</div>;
  }
  return (
    <div className="grid grid-cols-4 gap-3">
      {events.map((event) => (
        <div key={event.id} className="rounded-lg border border-slate-700 bg-panel p-3 text-xs text-slate-200">
          <div className="font-semibold text-white">{event.layer}</div>
          {event.duration ? <div className="text-[11px] text-slate-400">{event.duration}</div> : null}
          {event.rows !== undefined ? <div className="text-[11px] text-slate-500">Rows: {event.rows}</div> : null}
          {event.columns !== undefined ? <div className="text-[11px] text-slate-500">Columns: {event.columns}</div> : null}
        </div>
      ))}
    </div>
  );
}
