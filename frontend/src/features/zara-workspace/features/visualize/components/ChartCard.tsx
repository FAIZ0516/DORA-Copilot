import { Copy, HelpCircle, Pencil, Rows3, Sparkles, Trash2 } from "lucide-react";

import type { PreviewResult } from "../../workflow/types";
import { ChartRenderer } from "../charts/ChartRenderer";
import type { ChartConfig, ChartResult } from "../types/visualization";

const chartTypeLabels = { bar: "Bar chart", line: "Trend", donut: "Composition", kpi: "KPI", table: "Ranked table" } as const;

export function ChartCard({ chart, result, preview, loading, onAskWhy, onEdit, onDelete, onDuplicate, onViewData, onSelectCategory }: { chart: ChartConfig; result?: ChartResult; preview: PreviewResult; loading: boolean; onAskWhy: () => void; onEdit: () => void; onDelete: () => void; onDuplicate: () => void; onViewData: () => void; onSelectCategory: (label: string) => void }) {
  return (
    <article className={`chart-card chart-card--${chart.type}`}>
      <header>
        <div>
          <span className="chart-type-badge">{chartTypeLabels[chart.type]}</span>
          <div><h3>{chart.title}</h3><p>{chart.subtitle ?? (chart.group_by ? `Grouped by ${chart.group_by.replaceAll("_", " ")}` : "Prepared workflow output")}</p></div>
        </div>
        <div className="chart-card__meta">
          {result && <small>{result.data.length} points · {Math.round(result.execution_time_ms)} ms</small>}
          <span title="Built from the processed workflow output"><HelpCircle size={13} /></span>
        </div>
      </header>
      <div className="chart-card__canvas">{loading ? <div className="chart-loading"><i /><span>Building a fresh view</span></div> : <ChartRenderer chart={chart} result={result} preview={preview} onSelect={onSelectCategory} />}</div>
      <footer>
        <button className="ask-why" onClick={onAskWhy}><Sparkles size={12} /> Ask Zara why</button>
        <div>
          <button onClick={onEdit} title="Edit chart" aria-label={`Edit ${chart.title}`}><Pencil size={13} /></button>
          <button onClick={onViewData} title="View underlying data" aria-label={`View data for ${chart.title}`}><Rows3 size={13} /></button>
          <button onClick={onDuplicate} title="Duplicate chart" aria-label={`Duplicate ${chart.title}`}><Copy size={13} /></button>
          <button className="chart-delete-action" onClick={onDelete} title="Delete chart" aria-label={`Delete ${chart.title}`}><Trash2 size={13} /></button>
        </div>
      </footer>
    </article>
  );
}
