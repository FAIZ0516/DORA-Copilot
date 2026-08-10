import type { NodeType } from "../types";

export const operationTheme: Record<NodeType, { accent: string; label: string }> = {
  dataset: { accent: "#2563eb", label: "Data" },
  filter: { accent: "#7c3aed", label: "Filter" },
  select: { accent: "#059669", label: "Selection" },
  calculate: { accent: "#d97706", label: "Calculation" },
  group: { accent: "#0f9488", label: "Summary" },
  join: { accent: "#e11d48", label: "Combination" },
  output: { accent: "#4f46e5", label: "Result" },
};