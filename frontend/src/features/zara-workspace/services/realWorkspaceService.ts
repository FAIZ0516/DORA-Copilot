import type { DatasetSchema, DatasetSummary, PreviewResult, WorkflowDefinition } from "../features/workflow/types";
import type { WorkspaceService } from "./workspaceService";

const apiBase = (import.meta.env.VITE_ZARA_WORKSPACE_API_BASE_URL || "").replace(/\/$/, "");

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${url}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Workspace API request failed (${response.status})`);
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export class RealWorkspaceService implements WorkspaceService {
  datasets() { return request<DatasetSummary[]>("/api/datasets"); }
  schema(dataset: string) { return request<DatasetSchema>(`/api/datasets/${dataset}/schema`); }
  values(dataset: string, column: string) { return request<{ values: unknown[] }>(`/api/datasets/${dataset}/values/${encodeURIComponent(column)}`); }
  run(workflow: WorkflowDefinition) { return request<PreviewResult>("/api/workflows/run", { method: "POST", body: JSON.stringify({ workflow, limit: 100 }) }); }
  save(workflow: WorkflowDefinition) { return request<WorkflowDefinition>(workflow.id ? `/api/workflows/${workflow.id}` : "/api/workflows", { method: workflow.id ? "PUT" : "POST", body: JSON.stringify(workflow) }); }
}
