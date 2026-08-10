import { useState } from "react";

export const PANEL_LAYOUT_STORAGE_KEY = "echo-three-panel-layout-v1";
export const DEFAULT_PANEL_LAYOUT = Object.freeze({ history: true, dashboard: true, chat: true });

export function normalizePanelLayout(value) {
  const normalized = {
    history: value?.history !== false,
    dashboard: value?.dashboard !== false,
    chat: value?.chat !== false,
  };
  if (!normalized.history && !normalized.dashboard && !normalized.chat) return { ...DEFAULT_PANEL_LAYOUT };
  return normalized;
}

export function loadPanelLayout(storage = globalThis.window?.localStorage) {
  try {
    const saved = storage?.getItem(PANEL_LAYOUT_STORAGE_KEY);
    return saved ? normalizePanelLayout(JSON.parse(saved)) : { ...DEFAULT_PANEL_LAYOUT };
  } catch {
    return { ...DEFAULT_PANEL_LAYOUT };
  }
}

export function usePanelLayout() {
  const [panels, setPanels] = useState(() => loadPanelLayout());
  const [mobilePanel, setMobilePanel] = useState("dashboard");

  function save(next) {
    const normalized = normalizePanelLayout(next);
    setPanels(normalized);
    try {
      window.localStorage.setItem(PANEL_LAYOUT_STORAGE_KEY, JSON.stringify(normalized));
    } catch {
      // Layout persistence is a progressive enhancement.
    }
    return normalized;
  }

  function togglePanel(panel) {
    save({ ...panels, [panel]: !panels[panel] });
  }

  function showPanel(panel) {
    if (!panels[panel]) save({ ...panels, [panel]: true });
    setMobilePanel(panel);
  }

  function restoreDefault() {
    save(DEFAULT_PANEL_LAYOUT);
    setMobilePanel("dashboard");
  }

  return { panels, mobilePanel, setMobilePanel, togglePanel, showPanel, restoreDefault };
}
