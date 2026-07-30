import { useEffect, useState } from "react";
import {
  BarChart3,
  BookOpen,
  Bot,
  Database,
  Headphones,
  Search,
  ShieldCheck,
} from "lucide-react";
import Chat from "./components/Chat";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const fallbackProjects = [{ key: "DCPM", label: "DCPM", detail: "DoraDB" }];

export default function App() {
  const [projects, setProjects] = useState(fallbackProjects);
  const [system, setSystem] = useState({
    dataSource: "connecting",
    database: "Checking data source",
    databaseConnected: false,
    llm: "Google AI Studio",
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
            llm: "Google AI Studio unavailable",
          });
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const statusLabel =
    system.dataSource === "offline"
      ? "Service offline"
      : system.databaseConnected
        ? "DoraDB connected"
        : system.dataSource === "doradb"
          ? "DoraDB setup required"
          : "Connecting";

  return (
    <div className="site-shell">
      <header className="site-header">
        <div className="utility-bar">
          <div className="header-width utility-inner">
            <nav aria-label="Workspace areas">
              <a href="#assistant">Engineering</a>
              <a href="#capabilities">Delivery</a>
              <a href="#governance">Governance</a>
            </nav>
            <div className="utility-actions">
              <span><Headphones size={14} /> Voice enabled</span>
              <span><BookOpen size={14} /> Metric guide</span>
            </div>
          </div>
        </div>

        <div className="primary-bar">
          <div className="header-width primary-inner">
            <a className="brand" href="#assistant" aria-label="DORA Intelligence home">
              <span className="brand-word">DORA</span>
              <span className="brand-diamond" aria-hidden="true" />
              <span className="brand-sub">Intelligence</span>
            </a>
            <nav className="primary-nav" aria-label="Main navigation">
              <a href="#assistant">AI Assistant</a>
              <a href="#capabilities">Metrics &amp; Insights</a>
              <a href="#governance">Trust Center</a>
            </nav>
            <div className="header-actions">
              <button className="icon-button" type="button" aria-label="Search">
                <Search size={22} />
              </button>
              <a className="header-cta" href="#assistant">Ask the agent</a>
              <span className={`system-pill ${system.dataSource}`}>
                <span />
                {statusLabel}
              </span>
            </div>
          </div>
        </div>
      </header>

      <main>
        <section className="hero" id="assistant">
          <div className="hero-decoration decoration-one" />
          <div className="hero-decoration decoration-two" />
          <div className="content-width hero-content">
            <div className="hero-copy">
              <p className="section-kicker">Conversational engineering intelligence</p>
              <h1>Turn delivery data into decisions.</h1>
              <p>
                Ask a real Gemini AI agent about DORA performance, release trends,
                anomalies, Jira references, and the evidence behind every answer.
              </p>
              <div className="hero-badges">
                <span><Bot size={17} /> {system.llm}</span>
                <span><Database size={17} /> {system.database}</span>
                <span><ShieldCheck size={17} /> Governed read-only</span>
              </div>
            </div>
            <div className="hero-proof" aria-label="Agent capability summary">
              <div>
                <strong>9</strong>
                <span>formal analysis skills</span>
              </div>
              <div>
                <strong>2</strong>
                <span>maximum tools per turn</span>
              </div>
              <div>
                <strong>1×</strong>
                <span>controlled repair loop</span>
              </div>
            </div>
          </div>
        </section>

        <section className="capability-strip content-width" id="capabilities">
          <div className="capability-card active">
            <Bot size={24} />
            <div><strong>Generative AI</strong><span>Google AI Studio conversation</span></div>
          </div>
          <div className="capability-card">
            <BarChart3 size={24} />
            <div><strong>Visual analysis</strong><span>Dynamic charts &amp; tables</span></div>
          </div>
          <div className="capability-card">
            <ShieldCheck size={24} />
            <div><strong>Validated results</strong><span>Evidence before answers</span></div>
          </div>
          <div className="capability-card">
            <Database size={24} />
            <div><strong>Controlled data</strong><span>Approved DoraDB queries</span></div>
          </div>
        </section>

        <section className="assistant-section content-width">
          <div className="section-heading">
            <div>
              <p className="section-kicker">DORA Copilot</p>
              <h2>Ask your delivery data</h2>
            </div>
            <p>
              No fixed question template. Ask naturally, continue with follow-ups,
              request a chart, or ask the agent to explain what changed.
            </p>
          </div>
          <Chat projects={projects} databaseConnected={system.databaseConnected} />
        </section>

        <section className="trust-section" id="governance">
          <div className="content-width trust-inner">
            <div>
              <p className="section-kicker light">Trust center</p>
              <h2>Generative where it helps.<br />Deterministic where it matters.</h2>
            </div>
            <div className="trust-grid">
              <article>
                <span>01</span>
                <h3>Plan</h3>
                <p>Gemini understands intent and proposes an approved data strategy.</p>
              </article>
              <article>
                <span>02</span>
                <h3>Control</h3>
                <p>Allowlisted tools, filters, row limits, and read-only access bound execution.</p>
              </article>
              <article>
                <span>03</span>
                <h3>Validate</h3>
                <p>Schema, numeric, date, duplicate, warning, and answer checks run automatically.</p>
              </article>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
