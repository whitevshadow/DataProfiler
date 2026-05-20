import { useFloating, offset, flip, shift, autoUpdate } from "@floating-ui/react";
import { useEffect, useState } from "react";
import { ColumnInsight } from "../types";
import { Badge } from "./Badge";

type ColumnTooltipProps = {
  insight: ColumnInsight;
  children: React.ReactNode;
};

export function ColumnTooltip({ insight, children }: ColumnTooltipProps) {
  const { refs, floatingStyles, context } = useFloating({
    placement: "right-start",
    middleware: [offset(12), flip(), shift()],
    whileElementsMounted: autoUpdate,
  });
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    window.addEventListener("scroll", close, { passive: true });
    return () => window.removeEventListener("scroll", close);
  }, [open]);

  return (
    <div
      ref={refs.setReference}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      className="relative"
    >
      {children}
      {open ? (
        <div
          ref={refs.setFloating}
          style={floatingStyles}
          className="z-50 w-72 rounded-xl border border-slate-700 bg-panel p-4 text-xs text-slate-200 shadow-xl"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-white">{insight.column}</span>
            <Badge label={insight.cardinality} />
          </div>
          <div className="mt-2 space-y-1 text-[11px]">
            <div className="flex justify-between"><span>Type</span><span>{insight.type}</span></div>
            <div className="flex justify-between"><span>Semantic</span><span>{insight.semantic}</span></div>
            <div className="flex justify-between"><span>Null Ratio</span><span>{(insight.null_ratio * 100).toFixed(1)}%</span></div>
            <div className="flex justify-between"><span>Quality</span><span>{insight.quality.toFixed(2)}</span></div>
          </div>
          {insight.top_values.length > 0 && (
            <div className="mt-3">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-400">Top Values</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {insight.top_values.map((value) => (
                  <Badge key={value} label={value} />
                ))}
              </div>
            </div>
          )}
          {insight.business_meaning && (
            <p className="mt-3 text-[11px] text-slate-300">{insight.business_meaning}</p>
          )}
          {insight.relationships.length > 0 && (
            <div className="mt-3">
              <div className="text-[10px] uppercase tracking-[0.2em] text-slate-400">Relationships</div>
              <div className="mt-1 flex flex-wrap gap-1">
                {insight.relationships.slice(0, 4).map((item) => (
                  <Badge key={item} label={item} tone="fk" />
                ))}
              </div>
            </div>
          )}
          {insight.ontology_tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {insight.ontology_tags.map((tag) => (
                <Badge key={tag} label={tag} tone="lcil" />
              ))}
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
