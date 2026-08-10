import { Download, X } from "lucide-react";
import type { PreviewResult } from "../../workflow/types";

export function DataDrawer({ preview, groupBy, category, onClose }: { preview: PreviewResult; groupBy?: string | null; category?: string; onClose: () => void }) {
  const rows = groupBy && category ? preview.rows.filter((row) => String(row[groupBy] ?? "Not set") === category).slice(0, 100) : preview.rows;
  return <section className="data-drawer"><header><div><strong>Underlying records</strong><small>{category ? `${groupBy?.replaceAll("_", " ")} = ${category}` : "Rows from the prepared output"} · {rows.length} shown</small></div><div><button><Download size={13} /> Export</button><button onClick={onClose} aria-label="Close data drawer"><X size={16} /></button></div></header><div><table><thead><tr><th>#</th>{preview.columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}><td>{index + 1}</td>{preview.columns.map((column) => <td key={column}>{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table></div></section>;
}
