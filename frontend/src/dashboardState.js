export function defaultDashboardView(role) {
  return role === "head_of_department" ? "portfolio" : "squad_detail";
}

export function buildDashboardContext(state, overrides = {}) {
  return {
    role: overrides.role ?? state.selectedRole,
    active_view: overrides.active_view ?? state.activeView,
    project: overrides.project ?? state.selectedProject,
    squad: (overrides.squad ?? state.selectedSquad) || undefined,
    release: (overrides.release ?? state.selectedRelease) || undefined,
    sprint: (overrides.sprint ?? state.selectedSprint) || undefined,
    date_from: (overrides.date_from ?? state.dateRange?.from) || undefined,
    date_to: (overrides.date_to ?? state.dateRange?.to) || undefined,
    selected_metric: (overrides.selected_metric ?? state.selectedMetric) || undefined,
    selected_squad_row: (overrides.selected_squad_row ?? state.selectedSquadRow) || undefined,
    current_metric_value: overrides.current_metric_value ?? state.currentMetricValue ?? undefined,
  };
}

