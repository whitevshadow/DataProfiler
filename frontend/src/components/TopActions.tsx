type TopActionsProps = {
  onExport: () => void;
};

export function TopActions({ onExport }: TopActionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      <button className="rounded-lg border border-slate-700 bg-panel px-3 py-2 text-xs">Upload Files</button>
      <button className="rounded-lg border border-slate-700 bg-panel px-3 py-2 text-xs">Profile Directory</button>
      <button className="rounded-lg border border-slate-700 bg-panel px-3 py-2 text-xs">Database Connect</button>
      <button onClick={onExport} className="rounded-lg bg-accent px-3 py-2 text-xs font-semibold text-slate-900">Export DBML</button>
    </div>
  );
}
