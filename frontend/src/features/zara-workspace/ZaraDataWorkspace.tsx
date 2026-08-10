import { AlertCircle, X } from "lucide-react";
import { useState } from "react";

import "./zara-workspace.css";
import "./integration.css";

import { OperationSidebar } from "./components/layout/OperationSidebar";
import { PreviewDrawer } from "./components/layout/PreviewDrawer";
import { TopNavigation, type AppPage } from "./components/layout/TopNavigation";
import { AssistantWorkspace } from "./features/assistant/components/AssistantWorkspace";
import { SavedViewsPage } from "./features/saved-views/components/SavedViewsPage";
import { VisualizationWorkspace } from "./features/visualize/components/VisualizationWorkspace";
import type { VisualizationDashboard } from "./features/visualize/types/visualization";
import { NodeConfigPanel } from "./features/workflow/components/NodeConfigPanel";
import { WorkflowCanvas } from "./features/workflow/components/WorkflowCanvas";
import { useWorkspace } from "./features/workflow/hooks/useWorkspace";

function App() {
  const workspace = useWorkspace();
  const [page, setPage] = useState<AppPage>("prepare");
  const [saveRequest, setSaveRequest] = useState(0);
  const [initialView, setInitialView] = useState<VisualizationDashboard | null>(null);

  const goVisualize = async () => {
    setInitialView(null);
    setPage("visualize");
    if (!workspace.preview) await workspace.run();
  };
  const save = () => {
    if (page === "visualize") setSaveRequest((value) => value + 1);
    else void workspace.save();
  };
  return <div className="zara-app">
    <TopNavigation active={page} name={workspace.workflow.name} running={workspace.running} dirty={workspace.dirty} onNameChange={workspace.setName} onNavigate={(next) => next === "visualize" ? void goVisualize() : setPage(next)} onRun={() => void workspace.run()} onSave={save} />
    {page === "prepare" && <>
    <div className="workspace-shell">
      <OperationSidebar onAdd={workspace.addNode} />
      <WorkflowCanvas workflow={workspace.workflow} selectedId={workspace.selectedId} dataset={workspace.dataset} schema={workspace.schema} preview={workspace.preview} overviewPosition={workspace.overviewPosition} onMoveOverview={workspace.moveOverview} nodeIssues={workspace.nodeIssues} panelOpen={Boolean(workspace.selectedNode)}
        onSelect={workspace.setSelectedId} onMove={workspace.moveNode} onAdd={workspace.addNode} onDelete={workspace.deleteNode} onConnect={workspace.connect} onDisconnect={workspace.disconnect} />
      <NodeConfigPanel node={workspace.selectedNode} workflow={workspace.workflow} datasets={workspace.datasets} schema={workspace.schema} schemas={workspace.schemas} nodeSchemas={workspace.nodeSchemas} nodeIssue={workspace.selectedNode ? workspace.nodeIssues[workspace.selectedNode.id] : undefined} onClose={() => workspace.setSelectedId(null)} onUpdate={(config) => workspace.selectedNode && workspace.updateNode(workspace.selectedNode.id, config)} onVisualize={() => void goVisualize()} />
      {workspace.catalogLoading && <div className="catalog-loading"><span /><p>Discovering approved DoraDB datasets…</p></div>}
      {workspace.error && <div className="toast-error"><AlertCircle size={17} /><span><strong>Something needs attention</strong>{workspace.error}</span><button onClick={() => workspace.setError(null)}><X size={15} /></button></div>}
    </div>
    <PreviewDrawer result={workspace.preview} workflow={workspace.workflow} datasets={workspace.datasets} schemas={workspace.schemas} open={workspace.previewOpen} onClose={() => workspace.setPreviewOpen(false)} onRun={() => void workspace.run()} />
    </>}
    {page === "visualize" && <VisualizationWorkspace workflow={initialView?.workflow ?? workspace.workflow} preview={workspace.preview} datasetName={workspace.dataset?.name ?? "Prepared output"} saveRequest={saveRequest} initialView={initialView} onPrepare={() => setPage("prepare")} onNeedOutput={workspace.run} />}
    {page === "assistant" && <AssistantWorkspace workflow={workspace.workflow} preview={workspace.preview} datasetName={workspace.dataset?.name ?? "Prepared output"} onPrepare={() => setPage("prepare")} onVisualize={() => void goVisualize()} />}
    {page === "saved" && <SavedViewsPage onVisualize={() => void goVisualize()} onOpen={(view) => { setInitialView(view); setPage("visualize"); if (!workspace.preview) void workspace.run(); }} />}
  </div>;
}

export default App;
