import { memo } from "react";
import { ColumnInsight, DiagramNode } from "../types";
import { Badge } from "./Badge";
import { ColumnTooltipList } from "./ColumnTooltipList";

type TableNodeProps = {
  data: DiagramNode & { expanded: boolean; columnInsights?: ColumnInsight[] };
};

export const TableNode = memo(({ data }: TableNodeProps) => {
  return (
    <div className="node-shadow rounded-xl border border-slate-700 bg-surface px-4 py-3 text-xs text-slate-200">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-white">{data.name}</div>
          <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-slate-400">{data.module}</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Badge label={`${data.row_count} rows`} />
          <Badge label={`Q ${data.quality.toFixed(2)}`} tone={data.quality < 0.7 ? "quality" : "neutral"} />
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-[10px] text-slate-400">
        <span>{data.column_count} columns</span>
        <span>{data.pk_columns.length} PK</span>
        <span>{data.fk_columns.length} FK</span>
      </div>
      {data.expanded && (
        <div className="mt-3 space-y-2">
          {data.columnInsights && data.columnInsights.length > 0 ? (
            <ColumnTooltipList columns={data.columnInsights} />
          ) : (
            data.columns.map((col) => (
              <div key={col.name} className="flex items-center justify-between rounded-lg border border-slate-800 bg-panel px-2 py-1">
                <div>
                  <div className="text-[11px] text-white">{col.name}</div>
                  <div className="text-[10px] text-slate-500">{col.type}</div>
                </div>
                <div className="flex gap-1">
                  {col.pk ? <Badge label="PK" tone="pk" /> : null}
                  {col.fk ? <Badge label="FK" tone="fk" /> : null}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
});
