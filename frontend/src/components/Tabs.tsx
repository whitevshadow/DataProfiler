type TabsProps = {
  tabs: string[];
  active: string;
  onChange: (tab: string) => void;
};

export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => onChange(tab)}
          className={`rounded-full border px-3 py-1 text-[11px] ${
            active === tab ? "border-accent text-accent" : "border-slate-700 text-slate-400"
          }`}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
