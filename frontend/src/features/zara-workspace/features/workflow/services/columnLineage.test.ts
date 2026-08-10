import { describe, expect, it } from "vitest";

import { outputColumnLineage } from "./columnLineage";
import type { DatasetSchema, WorkflowDefinition } from "../types";

const jira: DatasetSchema = { dataset: { id: "jira", name: "Jira Issues", description: "", schema_name: "enp", table_name: "issues", relation_type: "table", column_count: 2, approximate_rows: null }, columns: [
  { name: "status", label: "Status", data_type: "text", nullable: false, numeric: false, date_like: false },
  { name: "dcpsquad", label: "Squad", data_type: "text", nullable: false, numeric: false, date_like: false },
] };
const squads: DatasetSchema = { dataset: { id: "squads", name: "Squad Information", description: "", schema_name: "enp", table_name: "squads", relation_type: "table", column_count: 2, approximate_rows: null }, columns: [
  { name: "dcpsquad", label: "Squad", data_type: "text", nullable: false, numeric: false, date_like: false },
  { name: "squad_lead", label: "Squad Lead", data_type: "text", nullable: false, numeric: false, date_like: false },
] };
const schemas = { jira, squads };
const datasets = [jira.dataset, squads.dataset];

function workflow(nodes: WorkflowDefinition["nodes"]): WorkflowDefinition { return { name: "Lineage", nodes, edges: nodes.slice(1).map((node, index) => ({ id: `edge-${index}`, source: nodes[index].id, target: node.id })) }; }

describe("outputColumnLineage", () => {
  it("marks only the surviving filtered field", () => {
    const result = outputColumnLineage(workflow([
      { id: "input", type: "dataset", config: { dataset: "jira" }, position: { x: 0, y: 0 } },
      { id: "filter", type: "filter", config: { rules: [{ id: "status", column: "status", operator: "equals", value: "Closed" }] }, position: { x: 1, y: 0 } },
      { id: "output", type: "output", config: {}, position: { x: 2, y: 0 } },
    ]), schemas, datasets);
    expect(result.get("status")?.transformations).toEqual([{ type: "filter", description: "status = Closed" }]);
    expect(result.get("dcpsquad")?.transformations).toEqual([]);
  });

  it("describes grouped and joined output fields without keeping removed filter markers", () => {
    const result = outputColumnLineage(workflow([
      { id: "input", type: "dataset", config: { dataset: "jira" }, position: { x: 0, y: 0 } },
      { id: "filter", type: "filter", config: { rules: [{ id: "status", column: "status", operator: "equals", value: "Closed" }] }, position: { x: 1, y: 0 } },
      { id: "group", type: "group", config: { group_by: "dcpsquad", calculation: "count", result_name: "issue_count" }, position: { x: 2, y: 0 } },
      { id: "join", type: "join", config: { dataset: "squads", left_column: "dcpsquad", right_column: "dcpsquad" }, position: { x: 3, y: 0 } },
      { id: "output", type: "output", config: {}, position: { x: 4, y: 0 } },
    ]), schemas, datasets);
    expect(result.get("status")).toBeUndefined();
    expect(result.get("dcpsquad")?.transformations.at(-1)).toEqual({ type: "group", description: "Grouped by dcpsquad" });
    expect(result.get("issue_count")?.transformations).toEqual([{ type: "group", description: "Calculated by Group: Count of records" }]);
    expect(result.get("squad_lead")).toMatchObject({ sourceDataset: "Squad Information", transformations: [{ type: "join", description: "Added from Squad Information via Join" }] });
  });
});