const LEGEND = [
  { label: "TRUE_FK", color: "#22c55e" },
  { label: "SEMANTIC", color: "#60a5fa" },
  { label: "DOMAIN", color: "#a855f7" },
];

export function RelationshipLegend() {
  return (
    <div className="flex flex-wrap gap-3 text-[11px] text-slate-400">
      {LEGEND.map((item) => (
        <div key={item.label} className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
          {item.label}
        </div>
      ))}
    </div>
  );
}
