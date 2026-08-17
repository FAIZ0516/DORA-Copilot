import { lazy, Suspense, useEffect, useState } from "react";
import { Database } from "lucide-react";
import Chat from "./components/Chat";
import { DashboardProvider } from "./dashboardContext";
import zaraWordmark from "./assets/zara-wordmark.png";

const ZaraDataWorkspace = lazy(() => import("./features/zara-workspace/ZaraDataWorkspace"));
<<<<<<< HEAD
=======
// Report Studio is a full workspace, not a drawer: reports are persistent
// objects that outlive the conversation, so they get their own route.
>>>>>>> d7a58633ffe37fc0be2f3b43ac9913145a90716f
const ReportStudio = lazy(() => import("./features/report-studio/ReportStudio"));

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const fallbackProjects = [{ key: "DCPM", label: "DCPM", detail: "DoraDB" }];
function LegacyDoraCopilot() {
  const [projects, setProjects] = useState(fallbackProjects);
  const [system, setSystem] = useState({
    dataSource: "connecting",
    database: "Checking data source",
    databaseConnected: false,
    llm: "AI provider",
  });

  useEffect(() => {
    let active = true;
    Promise.all([
      fetch(`${API_BASE}/api/health`).then((response) => {
        if (!response.ok) throw new Error("Health check failed");
        return response.json();
      }),
      fetch(`${API_BASE}/api/projects`).then((response) => {
        if (!response.ok) throw new Error("Project lookup failed");
        return response.json();
      }),
    ])
      .then(([health, projectPayload]) => {
        if (!active) return;
        const mapped = (projectPayload.projects || []).map((project) => ({
          key: project.key,
          label: project.name || project.key,
          detail: "Read-only DoraDB",
        }));
        if (mapped.length) setProjects(mapped);
        setSystem({
          dataSource: health.data_source,
          database: health.database,
          databaseConnected: health.database_connected,
          llm: health.llm_provider,
        });
      })
      .catch(() => {
        if (active) {
          setSystem({
            dataSource: "offline",
            database: "Backend unavailable",
            databaseConnected: false,
            llm: "AI provider unavailable",
          });
        }
      });
    return () => { active = false; };
  }, []);

  const statusLabel = system.dataSource === "offline"
    ? "Service offline"
    : system.databaseConnected
      ? "DoraDB connected"
      : system.dataSource === "doradb"
        ? "DoraDB setup required"
        : "Connecting";

  return (
    <main className="echo-chat-app zara-workspace-app">
      <header className="echo-chat-app-header zara-app-header">
        <div className="zara-app-brand"><img src={zaraWordmark} alt="ZARA" /><small>AI decision workspace</small></div>
        <div className="zara-app-context"><span className={`zara-system-status ${system.dataSource}`}><i aria-hidden="true" />{statusLabel}</span></div>
      </header>
      <section className="echo-chat-app-body" aria-label="Zara enterprise analytics workspace">
        <DashboardProvider project={projects[0]?.key || "DCPM"}>
          <Chat
            projects={projects}
            databaseConnected={system.databaseConnected}
          />
        </DashboardProvider>
      </section>
      <span className="sr-only"><Database />{system.database} · {system.llm}</span>
    </main>
  );
}

export default function App() {
  const path = typeof window === "undefined" ? "/" : window.location.pathname.replace(/\/+$/, "") || "/";
  if (path === "/reports" || path.startsWith("/reports/")) {
    return (
      <Suspense fallback={<main className="report-studio-loading">Loading Report Studio…</main>}>
        <ReportStudio />
      </Suspense>
    );
  }
  if (path === "/zara-workspace" || path.startsWith("/zara-workspace/")) {
    return (
      <Suspense fallback={<main className="zara-workspace-loading">Loading Zara Data Workspace…</main>}>
        <ZaraDataWorkspace />
      </Suspense>
    );
  }
  return <LegacyDoraCopilot />;
}
