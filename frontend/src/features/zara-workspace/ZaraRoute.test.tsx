import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// App remains JavaScript so the existing DORA-Copilot frontend does not need a TypeScript migration.
// @ts-expect-error JavaScript module is intentionally outside the Zara-only TypeScript project.
import App from "../../App";

describe("Zara route integration", () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        clear: () => values.clear(),
        getItem: (key: string) => values.get(key) ?? null,
        removeItem: (key: string) => values.delete(key),
        setItem: (key: string, value: string) => values.set(key, String(value)),
      },
    });
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
    window.localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 404, json: async () => ({ detail: "Not available" }) })));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("loads the modular data workspace and falls back to its isolated prototype service", async () => {
    window.history.replaceState({}, "", "/zara-workspace");
    render(<App />);

    expect(
      await screen.findByText("Data Workspace", {}, { timeout: 15_000 }),
    ).toBeTruthy();
    expect(await screen.findByText("WORKFLOW CANVAS")).toBeTruthy();
    expect((await screen.findAllByText("Jira Issues")).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Ask Zara/i })).toBeTruthy();
  }, 20_000);

  it("opens the operational dashboard directly at the root route", async () => {
    window.history.replaceState({}, "", "/");
    render(<App />);

    expect(screen.getByLabelText("Zara enterprise analytics workspace")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Switch to Head of Department/i })).toBeNull();
    expect(screen.getByText("All Squads")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Choose your workspace" })).toBeNull();
  });
});
