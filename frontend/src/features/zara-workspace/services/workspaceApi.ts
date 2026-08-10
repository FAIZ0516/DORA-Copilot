import type { WorkflowDefinition } from "../features/workflow/types";
import { MockWorkspaceService } from "./mockWorkspaceService";
import { RealWorkspaceService } from "./realWorkspaceService";

const configuredMode = import.meta.env.VITE_ZARA_WORKSPACE_DATA_MODE ?? "auto";
const mock = new MockWorkspaceService();
const real = new RealWorkspaceService();
let fallbackActive = configuredMode === "mock";

async function useService<T>(realCall: () => Promise<T>, mockCall: () => Promise<T>): Promise<T> {
  if (fallbackActive) return mockCall();
  try { return await realCall(); }
  catch (error) {
    if (configuredMode === "live") throw error;
    fallbackActive = true;
    return mockCall();
  }
}

export const workspaceApi = {
  datasets: () => useService(() => real.datasets(), () => mock.datasets()),
  schema: (dataset: string) => useService(() => real.schema(dataset), () => mock.schema(dataset)),
  values: (dataset: string, column: string) => useService(() => real.values(dataset, column), () => mock.values(dataset, column)),
  run: (workflow: WorkflowDefinition) => useService(() => real.run(workflow), () => mock.run(workflow)),
  save: (workflow: WorkflowDefinition) => useService(() => real.save(workflow), () => mock.save(workflow)),
};
