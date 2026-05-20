type PipelineStatusProps = {
  steps: string[];
};

export function PipelineStatus({ steps }: PipelineStatusProps) {
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {steps.map((step) => (
        <span key={step} className="rounded-full border border-slate-700 px-3 py-1 text-[11px] text-slate-400">
          {step}
        </span>
      ))}
    </div>
  );
}
