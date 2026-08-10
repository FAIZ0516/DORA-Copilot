import { BarChart3, Calendar, FolderOpen, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { savedViewService } from "../services/savedViewService";
import type { VisualizationDashboard } from "../../visualize/types/visualization";

export function SavedViewsPage({ onOpen, onVisualize }: { onOpen: (view: VisualizationDashboard) => void; onVisualize: () => void }) {
  const [views, setViews] = useState(savedViewService.list());
  return <main className="saved-views-page"><header><div><small>SAVED ANALYTICS</small><h1>Saved Views</h1><p>Reusable dashboards preserve chart setup, filters, layout, and workflow context.</p></div><button onClick={onVisualize}><Plus size={15} /> New View</button></header>{!views.length ? <div className="saved-empty"><span><FolderOpen size={27} /></span><h2>No saved views yet</h2><p>Create a visualization, then save it for your next review.</p><button onClick={onVisualize}>Create a dashboard</button></div> : <div className="saved-grid">{views.map((view) => <article key={view.id}><span><BarChart3 size={20} /></span><div><h2>{view.name}</h2><p>{view.charts.length} charts · {view.filters.length} active filters</p><small><Calendar size={12} /> Saved {new Date(view.savedAt).toLocaleString()}</small></div><footer><button onClick={() => onOpen(view)}>Open View</button><button onClick={() => setViews(savedViewService.remove(view.id))} title="Delete saved view"><Trash2 size={14} /></button></footer></article>)}</div>}</main>;
}
