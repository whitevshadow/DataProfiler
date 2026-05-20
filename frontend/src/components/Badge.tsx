type BadgeProps = {
  label: string;
  tone?: "neutral" | "pk" | "fk" | "quality" | "lcil";
};

const toneStyles: Record<NonNullable<BadgeProps["tone"]>, string> = {
  neutral: "border-slate-700 text-slate-300",
  pk: "border-pk text-pk",
  fk: "border-fk text-fk",
  quality: "border-danger text-danger",
  lcil: "border-lcil text-lcil",
};

export function Badge({ label, tone = "neutral" }: BadgeProps) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${toneStyles[tone]}`}>
      {label}
    </span>
  );
}
