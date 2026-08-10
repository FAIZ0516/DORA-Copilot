import { useEffect, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  BriefcaseBusiness,
  Code2,
  Database,
  Gauge,
  GitBranch,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import Chat from "./components/Chat";
import { DashboardProvider } from "./dashboardContext";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const fallbackProjects = [{ key: "DCPM", label: "DCPM", detail: "DoraDB" }];
const ROLE_STORAGE_KEY = "echo-selected-role";
const OPERATIONAL_ROLE_STORAGE_KEY = "echo-operational-role";

const ROLE_EXPERIENCES = [
  {
    role: "scrum_master",
    workspace: "technical",
    title: "Scrum Master",
    eyebrow: "Squad delivery workspace",
    description: "Monitor sprint health, investigate delivery risk, ask Zara, and create management-ready reports.",
    icon: Code2,
    features: [
      ["Live squad context", Code2],
      ["Sprint and release scope", GitBranch],
      ["Delivery risk signals", Activity],
      ["AI-assisted reporting", Gauge],
    ],
  },
  {
    role: "head_of_department",
    workspace: "business",
    title: "Head of Department",
    eyebrow: "Portfolio decision workspace",
    description: "Compare squads, focus management attention, and turn portfolio evidence into clear actions.",
    icon: BriefcaseBusiness,
    features: [
      ["All-squads overview", BriefcaseBusiness],
      ["Squad comparison", TrendingUp],
      ["Transparent attention rules", ShieldCheck],
      ["Executive reporting", Gauge],
    ],
  },
];

function storedOperationalRole() {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(OPERATIONAL_ROLE_STORAGE_KEY);
  return value === "scrum_master" || value === "head_of_department" ? value : null;
}

export default function App() {
  const initialRole = storedOperationalRole();
  const [screen, setScreen] = useState(initialRole ? "workspace" : "role-selection");
  const [selectedRole, setSelectedRole] = useState(initialRole === "head_of_department" ? "business" : "technical");
  const [operationalRole, setOperationalRole] = useState(initialRole || "scrum_master");
  const [projects, setProjects] = useState(fallbackProjects);
  const [system, setSystem] = useState({
    dataSource: "connecting",
    database: "Checking data source",
    databaseConnected: false,
    llm: "AI provider",
  });

  function changeWorkspace(workspace) {
    const next = workspace === "business" ? "business" : "technical";
    window.localStorage.setItem(ROLE_STORAGE_KEY, next);
    setSelectedRole(next);
  }

  function changeOperationalRole(role) {
    const nextRole = role === "head_of_department" ? "head_of_department" : "scrum_master";
    const workspace = nextRole === "head_of_department" ? "business" : "technical";
    window.localStorage.setItem(OPERATIONAL_ROLE_STORAGE_KEY, nextRole);
    window.localStorage.setItem(ROLE_STORAGE_KEY, workspace);
    setOperationalRole(nextRole);
    setSelectedRole(workspace);
  }

  function selectRole(role) {
    changeOperationalRole(role);
    setScreen("workspace");
  }

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

  if (screen === "role-selection") {
    return (
      <main className="zara-role-screen">
        <section className="zara-role-shell" aria-labelledby="role-heading">
          <header className="zara-role-heading">
            <span className="zara-text-brand">Zara</span>
            <p>Enterprise delivery intelligence</p>
            <h1 id="role-heading">Choose your workspace</h1>
            <span>Go directly to the evidence, risks, reports, and AI guidance relevant to your role.</span>
          </header>
          <div className="zara-role-grid">
            {ROLE_EXPERIENCES.map((experience) => {
              const RoleIcon = experience.icon;
              return (
                <article key={experience.role} className="zara-role-card">
                  <div className="zara-role-card-top"><span><RoleIcon aria-hidden="true" /></span><p>{experience.eyebrow}</p></div>
                  <h2>{experience.title}</h2>
                  <p>{experience.description}</p>
                  <ul>{experience.features.map(([label, Icon]) => <li key={label}><Icon aria-hidden="true" />{label}</li>)}</ul>
                  <button type="button" onClick={() => selectRole(experience.role)}>Open {experience.title} workspace <ArrowRight aria-hidden="true" /></button>
                </article>
              );
            })}
          </div>
          <footer><ShieldCheck aria-hidden="true" /> Governed read-only analysis · Evidence before recommendations</footer>
        </section>
      </main>
    );
  }

  return (
    <main className="echo-chat-app zara-workspace-app">
      <header className="echo-chat-app-header zara-app-header">
        <div className="zara-app-brand"><span className="zara-text-brand">Zara</span><small>AI decision workspace</small></div>
        <div className="zara-app-context"><span>{operationalRole === "head_of_department" ? "Head of Department" : "Scrum Master"}</span><span className={`zara-system-status ${system.dataSource}`}><i aria-hidden="true" />{statusLabel}</span></div>
        <button type="button" onClick={() => setScreen("role-selection")}><ArrowLeft aria-hidden="true" /> Change role</button>
      </header>
      <section className="echo-chat-app-body" aria-label="Zara enterprise analytics workspace">
        <DashboardProvider role={operationalRole} project={projects[0]?.key || "DCPM"}>
          <Chat
            projects={projects}
            databaseConnected={system.databaseConnected}
            selectedRole={selectedRole}
            operationalRole={operationalRole}
            onWorkspaceChange={changeWorkspace}
            onRoleChange={changeOperationalRole}
          />
        </DashboardProvider>
      </section>
      <span className="sr-only"><Database />{system.database} · {system.llm}</span>
    </main>
  );
}
