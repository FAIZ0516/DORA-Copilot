import { getDevelopmentSession } from "./conversations.js";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/$/, "");

function queryString(values = {}) {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return query.toString();
}

async function dashboardRequest(path, { signal } = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "X-Development-Session": getDevelopmentSession() },
    signal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Dashboard request failed with status ${response.status}`);
  }
  return response.json();
}

export async function loadJiraDashboard(projectKey, { refresh = false, signal } = {}) {
  const query = new URLSearchParams({ project_key: projectKey });
  if (refresh) query.set("refresh", "true");
  const response = await fetch(`${API_BASE}/api/jira-dashboard?${query}`, {
    headers: { "X-Development-Session": getDevelopmentSession() },
    signal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Dashboard request failed with status ${response.status}`);
  }
  return response.json();
}

export function loadDashboardSquads(project, options) {
  return dashboardRequest(`/api/dashboard/squads?${queryString({ project })}`, options);
}

export function loadDashboardFilters({ project, squad } = {}, options) {
  return dashboardRequest(`/api/dashboard/filters?${queryString({ project, squad })}`, options);
}

export function loadPortfolioDashboard(filters = {}, options) {
  return dashboardRequest(`/api/dashboard/portfolio?${queryString(filters)}`, options);
}

export function loadSquadDashboard(squad, filters = {}, options) {
  return dashboardRequest(
    `/api/dashboard/squad/${encodeURIComponent(squad)}?${queryString(filters)}`,
    options,
  );
}

export function loadDashboardIssues(filters = {}, options) {
  return dashboardRequest(`/api/dashboard/issues?${queryString(filters)}`, options);
}
