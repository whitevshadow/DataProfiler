type SearchBarProps = {
  value: string;
  onChange: (value: string) => void;
};

export function SearchBar({ value, onChange }: SearchBarProps) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-slate-700 bg-surface px-3 py-2">
      <span className="text-slate-500">⌕</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search tables, columns, semantics"
        className="w-full bg-transparent text-sm text-slate-100 focus:outline-none"
      />
    </div>
  );
}
