import { ColumnInsight } from "../types";
import { ColumnTooltip } from "./ColumnTooltip";
import { Badge } from "./Badge";

type ColumnTooltipListProps = {
  columns: ColumnInsight[];
};

export function ColumnTooltipList({ columns }: ColumnTooltipListProps) {
  return (
    <div className="space-y-2">
      {columns.map((col) => (
        <ColumnTooltip key={col.column} insight={col}>
          <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-surface px-3 py-2 text-xs text-slate-200">
            <div>
              <div className="text-sm text-white">{col.column}</div>
              <div className="text-[10px] text-slate-500">{col.type}</div>
            </div>
            <div className="flex gap-1">
              {col.pk_confidence > 0.8 ? <Badge label="PK" tone="pk" /> : null}
              {col.fk_confidence > 0.8 ? <Badge label="FK" tone="fk" /> : null}
            </div>
          </div>
        </ColumnTooltip>
      ))}
    </div>
  );
}
