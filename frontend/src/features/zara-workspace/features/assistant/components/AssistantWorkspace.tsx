import { BarChart3, Database, WandSparkles } from "lucide-react";
import { useMemo, useState } from "react";

import type { PreviewResult, WorkflowDefinition } from "../../workflow/types";
import type { DashboardContext } from "../types/assistant";
import { ZaraPanel } from "./ZaraPanel";

interface Props {
  workflow: WorkflowDefinition;
  preview: PreviewResult | null;
  datasetName: string;
  onPrepare: () => void;
  onVisualize: () => void;
}

export function AssistantWorkspace({ workflow, preview, datasetName, onPrepare, onVisualize }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const context = useMemo<DashboardContext>(() => ({
    dataset: datasetName,
    workflowName: workflow.name,
    charts: [],
    filters: [],
  }), [datasetName, workflow.name]);

  return (
    <main className={`assistant-workspace ${collapsed ? "assistant-workspace--collapsed" : ""}`}>
      <section className="assistant-workspace__context">
        <header><small>ASK ZARA</small><h1>Explore the prepared data with context</h1><p>The assistant boundary is ready for the existing AI provider. Until it is connected, responses are clearly marked as prototype insights.</p></header>
        <div className="assistant-context-cards">
          <article><Database size={18} /><div><span>Prepared dataset</span><strong>{datasetName}</strong></div></article>
          <article><WandSparkles size={18} /><div><span>Workflow</span><strong>{workflow.nodes.length} connected steps</strong></div></article>
          <article><BarChart3 size={18} /><div><span>Output</span><strong>{preview ? `${preview.row_count} preview rows` : "Run Prepare first"}</strong></div></article>
        </div>
        <div className="assistant-workspace__actions"><button onClick={onPrepare}><WandSparkles size={15} /> Return to Prepare</button><button onClick={onVisualize} disabled={!preview}><BarChart3 size={15} /> Open Visualize</button></div>
      </section>
      <ZaraPanel context={context} collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} onCreateChart={onVisualize} onShowBlockers={onVisualize} onViewData={onVisualize} />
    </main>
  );
}
