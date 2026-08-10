import type { VisualizationDashboard } from "../../visualize/types/visualization";

const STORAGE_KEY = "zara-saved-views";

function read(): VisualizationDashboard[] {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as VisualizationDashboard[]; }
  catch { return []; }
}

export const savedViewService = {
  list: read,
  save(view: VisualizationDashboard) {
    const items = read();
    const next = [view, ...items.filter((item) => item.id !== view.id)];
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    return next;
  },
  remove(id: string) {
    const next = read().filter((item) => item.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    return next;
  },
};
