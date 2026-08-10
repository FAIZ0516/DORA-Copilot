import { Boxes, Database, Eye, Layers3, Table2 } from "lucide-react";

import type { DatasetSummary } from "../types";

function purposeFor(dataset: DatasetSummary) {
  const name = `${dataset.name} ${dataset.table_name}`.toLowerCase();
  if (name.includes("issuelink")) return "Dependencies and relationships between issues.";
  if (name.includes("jira issues")) return "Issue status, owners, squads, priorities, and delivery progress.";
  if (name.includes("release frequency")) return "Release cadence and delivery trends over time.";
  if (name.includes("release success")) return "Release outcomes and success indicators.";
  if (name.includes("release info") || name.includes("releases")) return "Release dates, owners, versions, and readiness.";
  if (name.includes("fixversion")) return "Version-to-release mapping for delivery tracking.";
  if (name.includes("sprint")) return "Sprint timing, scope, and issue progress.";
  if (name.includes("label")) return "Issue labels and classifications.";
  if (name.includes("link")) return "Dependencies and relationships between issues.";
  if (name.includes("subtask")) return "Child work items and completion detail.";
  return "Approved data ready for safe exploration.";
}

const relationMeta = {
  table: { label: "Base tables", help: "Source records you can prepare and analyze.", icon: Table2 },
  materialized_view: { label: "Materialized views", help: "Precomputed reporting data for faster analysis.", icon: Layers3 },
  view: { label: "Views", help: "Live derived data built from approved sources.", icon: Eye },
} as const;

function preferredSources(datasets: DatasetSummary[]) {
  const seen = new Map<string, DatasetSummary>();
  for (const dataset of datasets) {
    const existing = seen.get(dataset.table_name);
    if (!existing || (dataset.schema_name === "enp" && existing.schema_name !== "enp")) seen.set(dataset.table_name, dataset);
  }
  return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export function DoraDataMap({ datasets, selectedId, onChoose }: { datasets: DatasetSummary[]; selectedId: string; onChoose: (id: string) => void }) {
  const sources = preferredSources(datasets);
  const groups = (["table", "materialized_view", "view"] as const).map((type) => ({ type, items: sources.filter((dataset) => dataset.relation_type === type) })).filter((group) => group.items.length);
  return <details className="dora-data-map" open>
    <summary><span><Boxes size={15} /> DoraDB data map</span><small>{sources.length} unique approved sources</small></summary>
    <p className="dora-data-map__intro">A simple guide to what users can get from the approved DoraDB data. Choose a source to use it in this workflow.</p>
    <div className="dora-data-map__legend"><span><Database size={12} /> {groups.filter((group) => group.type === "table").reduce((total, group) => total + group.items.length, 0)} tables</span><span><Layers3 size={12} /> {groups.filter((group) => group.type === "materialized_view").reduce((total, group) => total + group.items.length, 0)} materialized views</span><span><Eye size={12} /> {groups.filter((group) => group.type === "view").reduce((total, group) => total + group.items.length, 0)} views</span></div>
    <div className="dora-data-map__groups">{groups.map((group) => {
      const meta = relationMeta[group.type]; const Icon = meta.icon;
      return <section key={group.type}><header><span><Icon size={13} /></span><div><strong>{meta.label}</strong><small>{meta.help}</small></div></header><div>{group.items.map((dataset) => <button key={dataset.id} className={dataset.id === selectedId ? "selected" : ""} onClick={() => onChoose(dataset.id)}><span><strong>{dataset.name}</strong><small>{dataset.column_count} fields · {dataset.schema_name}</small></span><em>{purposeFor(dataset)}</em></button>)}</div></section>;
    })}</div>
  </details>;
}