import { Braces, Calculator, Columns3, Database, Filter, GitMerge, Group, TableProperties, type LucideIcon } from "lucide-react";
import type { NodeType } from "../../features/workflow/types";

const sections: { label: string; operations: { type: NodeType; title: string; hint: string; icon: LucideIcon; disabled?: boolean }[] }[] = [
  { label: "Data", operations: [{ type: "dataset", title: "Input Dataset", hint: "Start with an approved DoraDB dataset.", icon: Database }] },
  { label: "Transform", operations: [
    { type: "select", title: "Select Columns", hint: "Keep only the fields you need.", icon: Columns3 },
    { type: "filter", title: "Filter", hint: "Keep rows that match a condition.", icon: Filter },
    { type: "calculate", title: "Calculate", hint: "Create a value from existing data.", icon: Calculator, disabled: true },
    { type: "group", title: "Group", hint: "Summarize records by a category.", icon: Group },
    { type: "join", title: "Join", hint: "Combine two approved datasets.", icon: GitMerge },
  ] },
  { label: "Output", operations: [{ type: "output", title: "Output Dataset", hint: "Preview and visualize the result.", icon: TableProperties }] },
];

export function OperationSidebar({ onAdd }: { onAdd: (type: NodeType) => void }) {
  return <aside className="operation-sidebar">
    <div className="sidebar-heading"><Braces size={17} /><div><strong>Operations</strong><span>Drag a step to the canvas</span></div></div>
    <div className="operation-scroll">{sections.map((section) => <section key={section.label}>
      <h2>{section.label}</h2>
      {section.operations.map(({ type, title, hint, icon: Icon, disabled }) => <button key={type} className="operation-card" draggable={!disabled}
        disabled={disabled} title={disabled ? `${title} is planned for the next phase.` : hint}
        onClick={() => onAdd(type)} onDragStart={(event) => event.dataTransfer.setData("application/zara-node", type)}>
        <span className={`operation-icon operation-icon--${type}`}><Icon size={17} /></span><span><strong>{title}</strong><small>{hint}</small></span>{disabled && <em>Soon</em>}
      </button>)}
    </section>)}</div>
    <div className="sidebar-tip"><SparkleGlyph /><p><strong>Build like blocks</strong>Connect data to operations, then run to see your result.</p></div>
  </aside>;
}

function SparkleGlyph() { return <span className="tip-glyph">✦</span>; }
