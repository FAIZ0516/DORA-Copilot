import { BarChart3, Plus, RefreshCw, Save, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { buildDashboardContext } from "../../assistant/context/dashboardContextBuilder";
import { ZaraPanel } from "../../assistant/components/ZaraPanel";
import { savedViewService } from "../../saved-views/services/savedViewService";
import type { PreviewResult, WorkflowDefinition } from "../../workflow/types";
import { chartDataService } from "../services/chartDataService";
import { visualizationRecommendationService } from "../services/visualizationRecommendationService";
import type { ChartConfig, ChartFilter, ChartResult, VisualizationDashboard } from "../types/visualization";
import { AddChartModal } from "./AddChartModal";
import { ChartCard } from "./ChartCard";
import { DataDrawer } from "./DataDrawer";

interface Props {
  workflow: WorkflowDefinition;
  preview: PreviewResult | null;
  datasetName: string;
  saveRequest: number;
  initialView?: VisualizationDashboard | null;
  onPrepare: () => void;
  onNeedOutput: () => Promise<PreviewResult | null>;
}

export function VisualizationWorkspace({ workflow, preview, datasetName, saveRequest, initialView, onPrepare, onNeedOutput }: Props) {
  const [charts, setCharts] = useState<ChartConfig[]>([]);
  const [results, setResults] = useState<Record<string, ChartResult>>({});
  const [loading, setLoading] = useState<Set<string>>(new Set());
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ChartConfig | null>(null);
  const [drawer, setDrawer] = useState<{ chart?: ChartConfig; category?: string } | null>(null);
  const [assistantCollapsed, setAssistantCollapsed] = useState(false);
  const [assistantPrompt, setAssistantPrompt] = useState<{ id: string; question: string } | null>(null);
  const [dashboardFilters, setDashboardFilters] = useState<ChartFilter[]>([]);
  const [title, setTitle] = useState(`${workflow.name} Overview`);
  const [notice, setNotice] = useState("");
  const handledSave = useRef(0);

  const loadChart = useCallback(async (chart: ChartConfig, filters = dashboardFilters) => {
    setLoading((current) => new Set(current).add(chart.id));
    try {
      const result = await chartDataService.query(workflow, { ...chart, filters: [...(chart.filters ?? []), ...filters] });
      setResults((current) => ({ ...current, [chart.id]: result }));
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "A chart could not be loaded."); }
    finally { setLoading((current) => { const next = new Set(current); next.delete(chart.id); return next; }); }
  }, [dashboardFilters, workflow]);

  const loadCharts = useCallback(async (next: ChartConfig[], filters = dashboardFilters) => { setCharts(next); await Promise.all(next.map((chart) => loadChart(chart, filters))); }, [dashboardFilters, loadChart]);

  useEffect(() => {
    if (initialView) { setTitle(initialView.name); setDashboardFilters(initialView.filters); void loadCharts(initialView.charts, initialView.filters); }
  }, [initialView?.id]);

  const autoVisualize = async () => {
    if (!preview) { const result = await onNeedOutput(); if (!result) return; }
    setNotice("Zara is selecting useful views…");
    try { const recommended = await visualizationRecommendationService.recommend(workflow); await loadCharts(recommended); setNotice(`${recommended.length} charts created from the prepared output.`); }
    catch (reason) { setNotice(reason instanceof Error ? reason.message : "Auto Visualize could not finish."); }
  };
  const saveView = useCallback(() => {
    if (!charts.length) { setNotice("Add at least one chart before saving this view."); return; }
    savedViewService.save({ id: initialView?.id ?? crypto.randomUUID(), name: title.trim() || "Untitled Zara view", sourceWorkflowId: workflow.id, workflow, charts, filters: dashboardFilters, savedAt: new Date().toISOString() });
    setNotice("View saved. You can reopen it from Saved Views.");
  }, [charts, dashboardFilters, initialView?.id, title, workflow]);
  useEffect(() => { if (saveRequest > handledSave.current) { handledSave.current = saveRequest; saveView(); } }, [saveRequest, saveView]);

  const upsertChart = async (chart: ChartConfig) => {
    const next = charts.some((item) => item.id === chart.id) ? charts.map((item) => item.id === chart.id ? chart : item) : [...charts, chart];
    setCharts(next); setModalOpen(false); setEditing(null); await loadChart(chart);
  };
  const showBlockers = async () => {
    const status = preview?.columns.find((column) => column.toLowerCase().includes("status"));
    if (!status) { setNotice("Add a status field in Prepare before filtering blockers."); return; }
    const filters: ChartFilter[] = [{ column: status, operator: "contains", value: "Blocked" }]; setDashboardFilters(filters); await Promise.all(charts.map((chart) => loadChart(chart, filters))); setNotice("Dashboard filtered to blocker-related records.");
  };
  const context = useMemo(() => buildDashboardContext({ workflow, dataset: datasetName, charts, chartData: Object.fromEntries(Object.entries(results).map(([id, result]) => [id, result.data])), filters: dashboardFilters, selectedChart: drawer?.chart, selectedCategory: drawer?.category }), [charts, dashboardFilters, datasetName, drawer, results, workflow]);

  if (!preview) return <section className="visualize-empty-page"><span><BarChart3 size={29} /></span><h1>Nothing to visualize yet</h1><p>Run the Prepare workflow first, then turn its output into a visual story.</p><div><button onClick={onPrepare}>Prepare Data</button><button className="primary" onClick={() => void onNeedOutput()}>Run Current Workflow</button></div></section>;
  return <div className={`visualization-layout ${assistantCollapsed ? "visualization-layout--assistant-collapsed" : ""}`}>
    <section className="visualization-workspace">
      {/* The dataset name was rendered as a button with a dropdown chevron but no
    handler -- there is no dataset switcher here; the source is whatever
    Prepare produced. It is a label, so it reads as one now. */}
<header className="visualization-toolbar"><div><small>USING PREPARED OUTPUT</small><strong className="visualization-source">{datasetName || workflow.name}</strong></div><label><small>DASHBOARD NAME</small><input value={title} onChange={(event) => setTitle(event.target.value)} /></label><div><button onClick={() => { setEditing(null); setModalOpen(true); }}><Plus size={14} /> Add Chart</button><button className="auto-visualize" onClick={() => void autoVisualize()}><Sparkles size={14} /> Auto Visualize</button><button onClick={() => void Promise.all(charts.map((chart) => loadChart(chart)))}><RefreshCw size={14} /> Refresh</button><button onClick={saveView}><Save size={14} /> Save View</button></div></header>
      {notice && <div className="visualization-notice"><Sparkles size={13} />{notice}<button onClick={() => setNotice("")}>×</button></div>}
      {dashboardFilters.length > 0 && <div className="dashboard-filter"><span>Filtered: {dashboardFilters.map((filter) => `${filter.column} ${filter.operator} ${String(filter.value)}`).join(", ")}</span><button onClick={() => { setDashboardFilters([]); void Promise.all(charts.map((chart) => loadChart(chart, []))); }}>Reset filter</button></div>}
      {!charts.length ? <div className="visualization-empty"><span><Sparkles size={26} /></span><h2>Turn your data into a story</h2><p>Create your first chart manually or let Zara suggest a useful view from the output fields.</p><div><button className="primary" onClick={() => void autoVisualize()}><Sparkles size={15} /> Auto Visualize</button><button onClick={() => setModalOpen(true)}><Plus size={15} /> Add Chart</button></div></div> : <div className="dashboard-grid-view">{charts.map((chart) => <ChartCard key={chart.id} chart={chart} result={results[chart.id]} preview={preview} loading={loading.has(chart.id)} onAskWhy={() => { setAssistantCollapsed(false); setAssistantPrompt({ id: crypto.randomUUID(), question: `Why does ${drawer?.category ?? "this pattern"} stand out in ${chart.title}?` }); }} onEdit={() => { setEditing(chart); setModalOpen(true); }} onDelete={() => setCharts((current) => current.filter((item) => item.id !== chart.id))} onDuplicate={() => { const copy = { ...chart, id: crypto.randomUUID(), title: `${chart.title} copy` }; setCharts((current) => [...current, copy]); void loadChart(copy); }} onViewData={() => setDrawer({ chart })} onSelectCategory={(category) => setDrawer({ chart, category })} />)}</div>}
    </section>
    <ZaraPanel context={context} collapsed={assistantCollapsed} promptRequest={assistantPrompt} onToggle={() => setAssistantCollapsed((value) => !value)} onCreateChart={() => { setEditing(null); setModalOpen(true); }} onShowBlockers={() => void showBlockers()} onViewData={() => setDrawer({})} />
    {modalOpen && <AddChartModal preview={preview} editing={editing} onClose={() => { setModalOpen(false); setEditing(null); }} onCreate={(chart) => void upsertChart(chart)} />}
    {drawer && <DataDrawer preview={preview} groupBy={drawer.chart?.group_by} category={drawer.category} onClose={() => setDrawer(null)} />}
  </div>;
}
