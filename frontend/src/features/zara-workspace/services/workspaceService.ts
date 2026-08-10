import type { DatasetSchema, DatasetSummary, PreviewResult, WorkflowDefinition } from "../features/workflow/types";

export interface WorkspaceService {
  datasets(): Promise<DatasetSummary[]>;
  schema(dataset: string): Promise<DatasetSchema>;
  values(dataset: string, column: string): Promise<{ values: unknown[] }>;
  run(workflow: WorkflowDefinition): Promise<PreviewResult>;
  save(workflow: WorkflowDefinition): Promise<WorkflowDefinition>;
}
