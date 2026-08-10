import { AlertTriangle, Check, Columns3, Database, Filter, GitMerge, Group, LoaderCircle, MoreHorizontal, Play, TableProperties, Trash2 } from "lucide-react";
import { useRef, type PointerEvent } from "react";
import type { DatasetSummary, Point, WorkflowNode } from "../types";
import { isConfigured, NODE_LABELS, nodeSummary } from "../types";

const icons = { dataset: Database, filter: Filter, select: Columns3, group: Group, join: GitMerge, output: TableProperties } as const;
interface Props { node: WorkflowNode; dataset?: DatasetSummary; selected: boolean; rowCount?: number; issue?: string; running?: boolean; onSelect: () => void; onMove: (point: Point) => void; onDelete: () => void; onStartConnection: () => void; onFinishConnection: () => void; }
export function WorkflowNodeCard({ node, dataset, selected, rowCount, issue, running, onSelect, onMove, onDelete, onStartConnection, onFinishConnection }: Props) {
  const Icon = icons[node.type as keyof typeof icons] ?? Play; const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const pointerDown = (event: PointerEvent<HTMLElement>) => { if ((event.target as HTMLElement).closest("button")) return; drag.current = { x: event.clientX, y: event.clientY, left: node.position.x, top: node.position.y }; event.currentTarget.setPointerCapture(event.pointerId); onSelect(); };
  const pointerMove = (event: PointerEvent<HTMLElement>) => { if (!drag.current) return; onMove({ x: Math.max(30, drag.current.left + event.clientX - drag.current.x), y: Math.max(40, drag.current.top + event.clientY - drag.current.y) }); };
  const applied = isConfigured(node) && !issue; const status = issue ? <span className="node-warning" title={issue}><AlertTriangle size={12} /> Needs attention</span> : running ? <span className="node-running"><LoaderCircle size={12} /> Running</span> : applied ? <span className="node-success"><Check size={12} /> {rowCount != null ? `${rowCount} rows` : node.type === "dataset" ? "Ready" : node.type === "output" ? "Complete" : "Applied"}</span> : <span className="node-warning"><AlertTriangle size={12} /> Needs setup</span>;
  return <article className={`workflow-node workflow-node--${node.type} ${selected ? "workflow-node--selected" : ""} ${issue ? "workflow-node--attention" : ""}`} style={{ transform: `translate(${node.position.x}px, ${node.position.y}px)` }} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={() => { drag.current = null; }} onClick={(event) => { event.stopPropagation(); onSelect(); }}>
    <button className="node-port node-port--in" onClick={(event) => { event.stopPropagation(); onFinishConnection(); }} aria-label={`Connect into ${NODE_LABELS[node.type]}`} />
    <div className="node-head"><span><Icon size={16} /></span><small>{node.type === "dataset" ? "DATA" : node.type === "output" ? "OUTPUT" : "TRANSFORM"}</small><button className="node-menu" aria-label="Delete step" onClick={(event) => { event.stopPropagation(); onDelete(); }}><Trash2 size={14} /></button></div>
    <div className="node-body"><h3>{NODE_LABELS[node.type]}</h3><p>{issue || nodeSummary(node, dataset)}</p></div><div className="node-foot">{status}<MoreHorizontal size={15} /></div>
    <button className="node-port node-port--out" onClick={(event) => { event.stopPropagation(); onStartConnection(); }} aria-label={`Connect from ${NODE_LABELS[node.type]}`} />
  </article>;
}