import { getDevelopmentSession } from "./conversations.js";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/$/, "");

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
