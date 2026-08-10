import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// App remains JavaScript so the existing DORA-Copilot frontend does not need a TypeScript migration.
// @ts-expect-error JavaScript module is intentionally outside the Zara-only TypeScript project.
import App from "../../App";

describe("Zara route integration", () => {
  beforeEach(() => {
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

    expect(await screen.findByText("Data Workspace")).toBeTruthy();
    expect(await screen.findByText("WORKFLOW CANVAS")).toBeTruthy();
    expect(await screen.findByText("Jira Issues")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Ask Zara/i })).toBeTruthy();
  });

  it("keeps the existing role-selection UI available at the root route", async () => {
    window.history.replaceState({}, "", "/");
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Choose your workspace" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open Zara Data Workspace/i }).getAttribute("href")).toBe("/zara-workspace");
  });
});
