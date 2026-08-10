import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { NodeType, WorkflowNode } from "../types";
import { NODE_LABELS } from "../types";
import { WorkflowNodeCard } from "./WorkflowNodeCard";


describe("WorkflowNodeCard", () => {
  it.each(["dataset", "filter", "select", "output"] as NodeType[])(
    "keeps the %s configuration selected when its node is clicked",
    (type) => {
      const onSelect = vi.fn();
      const onCanvasClick = vi.fn();
      const node: WorkflowNode = {
        id: `${type}-1`,
        type,
        config: type === "dataset" ? { dataset: "public.issues" } : {},
        position: { x: 0, y: 0 },
      };

      render(
        <div onClick={onCanvasClick}>
          <WorkflowNodeCard
            node={node}
            selected={false}
            onSelect={onSelect}
            onMove={vi.fn()}
            onDelete={vi.fn()}
            onStartConnection={vi.fn()}
            onFinishConnection={vi.fn()}
          />
        </div>,
      );

      fireEvent.click(screen.getByRole("heading", { name: NODE_LABELS[type] }));

      expect(onSelect).toHaveBeenCalledOnce();
      expect(onCanvasClick).not.toHaveBeenCalled();
    },
  );
});
