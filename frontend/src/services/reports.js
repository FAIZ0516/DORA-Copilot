import { getDevelopmentSession } from "./conversations";

/**
 * Report Studio API client.
 *
 * Mirrors services/conversations.js: same base URL handling and the same
 * X-Development-Session identity header, so reports are scoped to the caller
 * exactly as conversations are.
 */

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/$/, "");

// Identity is owned by the conversations client -- reports must resolve to the
// same user as the conversations they draw evidence from, so this reuses it
// rather than keeping a second copy of the rule.
function headers() {
  return {
    "Content-Type": "application/json",
    "X-Development-Session": getDevelopmentSession(),
  };
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, { headers: headers(), ...options });
  if (!response.ok) {
    // The backend returns actionable messages; surface them rather than a
    // generic failure, but never invent one when the body is empty.
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      /* keep the status-based message */
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return null;
  return response.json();
}

export const listTemplates = () => request("/api/reports/templates");
export const listReports = () => request("/api/reports");
export const getReport = (id) => request(`/api/reports/${id}`);

export const createReport = (payload) =>
  request("/api/reports", { method: "POST", body: JSON.stringify(payload) });

export const updateReport = (id, payload) =>
  request(`/api/reports/${id}`, { method: "PATCH", body: JSON.stringify(payload) });

export const applyReportTemplate = (id, template) =>
  request(`/api/reports/${id}/template`, {
    method: "POST",
    body: JSON.stringify({ template }),
  });

export const archiveReport = (id) => request(`/api/reports/${id}`, { method: "DELETE" });

export const duplicateReport = (id, title) =>
  request(`/api/reports/${id}/duplicate`, { method: "POST", body: JSON.stringify({ title }) });

export const addSection = (id, payload) =>
  request(`/api/reports/${id}/sections`, { method: "POST", body: JSON.stringify(payload) });

export const updateSection = (id, sectionId, payload) =>
  request(`/api/reports/${id}/sections/${sectionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const deleteSection = (id, sectionId) =>
  request(`/api/reports/${id}/sections/${sectionId}`, { method: "DELETE" });

export const reorderSections = (id, sectionIds) =>
  request(`/api/reports/${id}/sections/reorder`, {
    method: "POST",
    body: JSON.stringify({ section_ids: sectionIds }),
  });

export const addSource = (id, payload) =>
  request(`/api/reports/${id}/sources`, { method: "POST", body: JSON.stringify(payload) });

export const removeSource = (id, sourceId) =>
  request(`/api/reports/${id}/sources/${sourceId}`, { method: "DELETE" });

export const composeReport = (id, sectionIds = []) =>
  request(`/api/reports/${id}/compose`, {
    method: "POST",
    body: JSON.stringify({ section_ids: sectionIds }),
  });

export const refineReportSection = (id, sectionId, instruction) =>
  request(`/api/reports/${id}/refine`, {
    method: "POST",
    body: JSON.stringify({ section_id: sectionId, instruction }),
  });

export const generateReport = (id) => request(`/api/reports/${id}/generate`, { method: "POST" });

export const validateReport = (id) => request(`/api/reports/${id}/validate`, { method: "POST" });

/**
 * Download an export. The file is streamed from the backend and handed to the
 * browser as a blob, so there is no public URL and nothing is left on a server
 * for someone else to fetch.
 */
async function fetchReportExport(id, format = "pdf", sectionId = null, preview = false) {
  const response = await fetch(`${API_BASE}/api/reports/${id}/export`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ format, section_id: sectionId, preview }),
  });
  if (!response.ok) {
    let detail = `Export failed (${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep the status-based message */
    }
    throw new Error(detail);
  }
  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const blob = await response.blob();
  return { blob, filename: match ? match[1] : `report.${format}` };
}

export async function exportReport(id, format = "pdf", sectionId = null) {
  const { blob, filename } = await fetchReportExport(id, format, sectionId, false);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return link.download;
}

/** Return an in-memory PDF URL rendered by the same endpoint as PDF export. */
export async function previewReportPdf(id) {
  const { blob, filename } = await fetchReportExport(id, "pdf", null, true);
  return { url: URL.createObjectURL(blob), filename };
}

/** Where an unsaved "add this answer to a report" hand-off is parked. */
export const PENDING_SOURCE_KEY = "zara-pending-report-source";

export function stashPendingSource(payload) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(PENDING_SOURCE_KEY, JSON.stringify(payload));
}

export function takePendingSource() {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(PENDING_SOURCE_KEY);
  window.localStorage.removeItem(PENDING_SOURCE_KEY);
  try {
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
