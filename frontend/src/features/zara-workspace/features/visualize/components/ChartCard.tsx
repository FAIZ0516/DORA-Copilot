import { Copy, HelpCircle, MoreHorizontal, Pencil, Rows3, Trash2 } from "lucide-react";

import type { PreviewResult } from "../../workflow/types";
import { ChartRenderer } from "../charts/ChartRenderer";
import type { ChartConfig, ChartResult } from "../types/visualization";

export function ChartCard({ chart, result, preview, loading, onAskWhy, onEdit, onDelete, onDuplicate, onViewData, onSelectCategory }: { chart: ChartConfig; result?: ChartResult; preview: PreviewResult; loading: boolean; onAskWhy: () => void; onEdit: () => void; onDelete: () => void; onDuplicate: () => void; onViewData: () => void; onSelectCategory: (label: string) => void }) {
  return <article className={`chart-card chart-card--${chart.type}`}>
    <header><div><div><h3>{chart.title}</h3><p>{chart.subtitle ?? (chart.group_by ? `Grouped by ${chart.group_by.replaceAll("_", " ")}` : "Prepared workflow output")}</p></div><span title="Built from the processed output"><HelpCircle size={13} /></span></div><button title="More chart actions"><MoreHorizontal size={16} /></button></header>
    <div className="chart-card__canvas">{loading ? <div className="chart-loading"><i /><span>Building chart</span></div> : <ChartRenderer chart={chart} result={result} preview={preview} onSelect={onSelectCategory} />}</div>
    <footer><button className="ask-why" onClick={onAskWhy}><span>✦</span> Ask Why</button><div><button onClick={onEdit} title="Edit chart"><Pencil size={13} /></button><button onClick={onViewData} title="View underlying data"><Rows3 size={13} /></button><button onClick={onDuplicate} title="Duplicate chart"><Copy size={13} /></button><button onClick={onDelete} title="Delete chart"><Trash2 size={13} /></button></div></footer>
  </article>;
}
