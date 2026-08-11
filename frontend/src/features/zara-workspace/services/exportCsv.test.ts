import { afterEach, describe, expect, it, vi } from "vitest";

import { safeFilename, toCsv } from "./exportCsv";
import { RealZaraAssistantService } from "../features/assistant/services/realZaraAssistantService";
import previewDrawerSource from "../components/layout/PreviewDrawer.tsx?raw";
import topNavigationSource from "../components/layout/TopNavigation.tsx?raw";
import zaraPanelSource from "../features/assistant/components/ZaraPanel.tsx?raw";
import chartCardSource from "../features/visualize/components/ChartCard.tsx?raw";
import dataDrawerSource from "../features/visualize/components/DataDrawer.tsx?raw";
import visualizationWorkspaceSource from "../features/visualize/components/VisualizationWorkspace.tsx?raw";

describe("toCsv", () => {
  it("writes a header row followed by one row per record", () => {
    const csv = toCsv(["squad", "open_bugs"], [
      { squad: "MBK", open_bugs: 1434 },
      { squad: "SRE", open_bugs: 58 },
    ]);
    expect(csv.split("\r\n")).toEqual(["squad,open_bugs", "MBK,1434", "SRE,58"]);
  });

  it("quotes values that would otherwise break the row or column structure", () => {
    const csv = toCsv(["summary"], [
      { summary: 'Fix "login" page, urgently' },
      { summary: "line one\nline two" },
    ]);
    expect(csv).toContain('"Fix ""login"" page, urgently"');
    expect(csv).toContain('"line one\nline two"');
  });

  it("renders missing values as empty cells rather than the text null", () => {
    expect(toCsv(["a", "b"], [{ a: null, b: undefined }])).toBe("a,b\r\n,");
  });

  it("keeps a cell for every column even when a record omits it", () => {
    expect(toCsv(["a", "b", "c"], [{ b: 2 }])).toBe("a,b,c\r\n,2,");
  });

  it("neutralises spreadsheet formulas in text while preserving real numbers", () => {
    expect(toCsv(["summary", "delta"], [{ summary: "=HYPERLINK(\"bad\")", delta: -4 }]))
      .toBe('summary,delta\r\n"\'=HYPERLINK(""bad"")",-4');
  });
});

describe("safeFilename", () => {
  it("strips characters that are not safe in a download name", () => {
    expect(safeFilename("Squad / Q3 report *2026*")).toBe("Squad-Q3-report-2026");
  });

  it("falls back when nothing usable survives", () => {
    expect(safeFilename("///")).toBe("zara-export");
  });
});

describe("workspace controls", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("has no button rendered without a handler", () => {
    // Regression: Export (twice), workspace settings, chart "more actions",
    // the dataset label and the assistant voice button were all rendered as
    // buttons with no onClick -- visible, clickable, and inert.
    const sources = [
      ["PreviewDrawer.tsx", previewDrawerSource],
      ["TopNavigation.tsx", topNavigationSource],
      ["ChartCard.tsx", chartCardSource],
      ["DataDrawer.tsx", dataDrawerSource],
      ["VisualizationWorkspace.tsx", visualizationWorkspaceSource],
      ["ZaraPanel.tsx", zaraPanelSource],
    ];
    for (const [path, source] of sources) {
      for (const tag of source.match(/<button(?:[^>{]|\{[^}]*\})*>/g) ?? []) {
        expect(tag, `${path}: ${tag}`).toMatch(/onClick=|type="submit"/);
      }
    }
  });

  it("sends live assistant questions to the real chat API and continues the conversation", async () => {
    // The live service used to POST to /api/assistant/ask, which no backend
    // router ever defined, so every question failed with an unavailable error.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ answer: "Grounded answer", metadata: { conversation_id: "conversation-1" } }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const service = new RealZaraAssistantService();
    const context = {
      dataset: "Jira Issues",
      workflowName: "Risk review",
      filters: [],
      charts: [],
    };

    await service.ask("What stands out?", context);
    await service.ask("What should I check next?", context);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/chat$/);
    const firstRequest = JSON.parse(fetchMock.mock.calls[0][1].body);
    const secondRequest = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(firstRequest.message).toContain("What stands out?");
    expect(firstRequest.conversation_id).toBeNull();
    expect(secondRequest.conversation_id).toBe("conversation-1");
  });
});
