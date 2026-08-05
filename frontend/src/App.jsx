import { useEffect, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BookOpen,
  Bot,
  BriefcaseBusiness,
  ChartNoAxesCombined,
  Code2,
  Database,
  Gauge,
  GitBranch,
  Headphones,
  Lightbulb,
  Search,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import Chat from "./components/Chat";
import Grainient from "./components/Grainient";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const fallbackProjects = [{ key: "DCPM", label: "DCPM", detail: "DoraDB" }];
const ROLE_STORAGE_KEY = "echo-selected-role";
const ROLE_EXPERIENCES = [
  {
    role: "technical",
    title: "Technical",
    eyebrow: "Engineering Intelligence",
    shortDescription: "Engineering insights and advanced delivery analytics.",
    expandedDescription:
      "Explore DORA metrics, sprint performance, delivery bottlenecks, deployment trends, and AI-generated engineering recommendations.",
    icon: Code2,
    buttonLabel: "Enter Technical Workspace",
    features: [
      { label: "DORA Metrics", icon: Code2 },
      { label: "Sprint Analysis", icon: GitBranch },
      { label: "Bottleneck Detection", icon: Activity },
      { label: "AI Recommendations", icon: Gauge },
    ],
  },
  {
    role: "business",
    title: "Business",
    eyebrow: "Executive Intelligence",
    shortDescription: "Executive summaries and business-focused insights.",
    expandedDescription:
      "View high-level delivery performance, productivity trends, executive summaries, KPI highlights, and clear business recommendations.",
    icon: BriefcaseBusiness,
    buttonLabel: "Enter Business Workspace",
    features: [
      { label: "Executive Summary", icon: BriefcaseBusiness },
      { label: "Productivity Trends", icon: TrendingUp },
      { label: "KPI Highlights", icon: ChartNoAxesCombined },
      { label: "Business Recommendations", icon: Lightbulb },
    ],
  },
];

export default function App() {
  const [screen, setScreen] = useState("splash");
  const [expandedRole, setExpandedRole] = useState(null);
  const [selectedRole, setSelectedRole] = useState(() =>
    typeof window !== "undefined" && window.localStorage.getItem(ROLE_STORAGE_KEY) === "business"
      ? "business"
      : "technical",
  );
  const [projects, setProjects] = useState(fallbackProjects);
  const [system, setSystem] = useState({
    dataSource: "connecting",
    database: "Checking data source",
    databaseConnected: false,
    llm: "Google AI Studio",
  });

  function changeWorkspace(workspace) {
    const next = workspace === "business" ? "business" : "technical";
    window.localStorage.setItem(ROLE_STORAGE_KEY, next);
    setSelectedRole(next);
  }

  useEffect(() => {
    if (screen !== "splash") return undefined;
    const timer = window.setTimeout(() => setScreen("role-selection"), 2000);
    return () => window.clearTimeout(timer);
  }, [screen]);

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

  function selectRole(role) {
    window.localStorage.setItem(ROLE_STORAGE_KEY, role);
    setSelectedRole(role);
    setScreen("welcome");
  }

  if (screen === "splash") {
    return (
      <main className="echo-screen echo-splash" aria-label="Echo loading screen">
        <EchoGrainientBackground />
        <div className="echo-splash-content">
          <EchoLogo />
          <h1>Turn Engineering Data into Decisions</h1>
        </div>
      </main>
    );
  }

  if (screen === "role-selection") {
    return (
      <main className="echo-screen echo-role-screen">
        <EchoGrainientBackground />
        <section className="echo-role-content" aria-labelledby="role-heading">
          <header className="echo-role-heading">
            <h1 id="role-heading">Choose Your Experience</h1>
            <p>Select the workspace that best fits your role.</p>
          </header>

          <div
            className={`echo-role-grid ${expandedRole ? `has-active active-${expandedRole}` : ""}`}
          >
            {ROLE_EXPERIENCES.map((experience) => (
              <RoleExperiencePanel
                key={experience.role}
                experience={experience}
                isActive={expandedRole === experience.role}
                isMuted={Boolean(expandedRole && expandedRole !== experience.role)}
                onExpand={setExpandedRole}
                onCollapse={(role) => {
                  setExpandedRole((current) => (current === role ? null : current));
                }}
                onSelect={selectRole}
              />
            ))}
          </div>
        </section>
      </main>
    );
  }

  if (screen === "welcome") {
    return (
      <main
        className="echo-welcome-screen"
        onPointerMove={trackWelcomeSpotlight}
        onPointerLeave={resetWelcomeSpotlight}
      >
        <div className="echo-welcome-atmosphere" aria-hidden="true">
          <span className="welcome-orb orb-cyan" />
          <span className="welcome-orb orb-violet" />
          <span className="welcome-light-beam" />
        </div>
        <div className="echo-welcome-cursor-light" aria-hidden="true" />

        <header className="echo-welcome-nav">
          <a className="echo-welcome-brand" href="#echo-welcome-home" aria-label="Echo home">
            <EchoLogo />
          </a>
          <nav aria-label="Welcome navigation">
            <a href="#echo-welcome-home">Home</a>
            <a href="#echo-welcome-about">About</a>
          </nav>
        </header>

        <section className="echo-welcome-hero" id="echo-welcome-home">
          <div className="echo-welcome-hero-logo">
            <EchoLogo />
          </div>
          <p className="echo-welcome-eyebrow">
            <span aria-hidden="true" />
            AI Engineering Performance Advisor
          </p>
          <h1>
            <span>Stop searching dashboards.</span>
            <span>Start asking questions.</span>
          </h1>
          <p className="echo-welcome-subheading">
            Transform Jira and DORA engineering data into clear engineering
            intelligence using conversational AI.
          </p>

          <div className="echo-welcome-actions">
            <button type="button" onClick={() => setScreen("chat")}>
              Get Started
              <ArrowRight aria-hidden="true" />
            </button>
            <a href="#echo-welcome-about">Learn More</a>
          </div>

          <div className="echo-welcome-features" id="echo-welcome-about" aria-label="Echo capabilities">
            {["DORA Metrics", "Sprint Intelligence", "AI Recommendations", "Executive Summary"].map(
              (feature, index) => (
                <span key={feature} style={{ "--chip-index": index }}>
                  <i aria-hidden="true" />
                  {feature}
                </span>
              ),
            )}
          </div>
        </section>

        <p className="echo-welcome-footnote">
          Governed intelligence for modern delivery teams
        </p>
      </main>
    );
  }

  if (screen === "chat") {
    return (
      <main className="echo-chat-app">
        <header className="echo-chat-app-header">
          <button type="button" onClick={() => setScreen("welcome")}>
            <ArrowLeft aria-hidden="true" />
            <span>Back</span>
          </button>

          <div className="echo-chat-app-brand" aria-label="Echo chat workspace">
            <EchoLogo />
          </div>

          <div className="echo-chat-app-meta">
            <span className="echo-chat-workspace-label">
              {selectedRole === "business" ? "Business Workspace" : "Technical Workspace"}
            </span>
            <span className={`echo-chat-status ${system.dataSource}`}>
              <i aria-hidden="true" />
              {statusLabel}
            </span>
          </div>
        </header>

        <section className="echo-chat-app-body" aria-label="Echo chat workspace">
          <Chat
            projects={projects}
            databaseConnected={system.databaseConnected}
            selectedRole={selectedRole}
            onWorkspaceChange={changeWorkspace}
          />
        </section>
      </main>
    );
  }

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
          <Chat
            projects={projects}
            databaseConnected={system.databaseConnected}
            selectedRole={selectedRole}
            onWorkspaceChange={changeWorkspace}
          />
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

function trackWelcomeSpotlight(event) {
  if (event.pointerType !== "mouse") return;
  const bounds = event.currentTarget.getBoundingClientRect();
  event.currentTarget.style.setProperty(
    "--welcome-pointer-x",
    `${event.clientX - bounds.left}px`,
  );
  event.currentTarget.style.setProperty(
    "--welcome-pointer-y",
    `${event.clientY - bounds.top}px`,
  );
}

function resetWelcomeSpotlight(event) {
  event.currentTarget.style.setProperty("--welcome-pointer-x", "50%");
  event.currentTarget.style.setProperty("--welcome-pointer-y", "43%");
}

function RoleExperiencePanel({
  experience,
  isActive,
  isMuted,
  onExpand,
  onCollapse,
  onSelect,
}) {
  const ExperienceIcon = experience.icon;
  const descriptionId = `${experience.role}-experience-description`;

  function revealPanel(event) {
    if (!event.target.closest("button")) onExpand(experience.role);
  }

  function handlePanelKeyDown(event) {
    if (event.target !== event.currentTarget) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onExpand(experience.role);
    }
  }

  function collapseWhenUnfocused(event) {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      onCollapse(experience.role);
    }
  }

  function collapseAfterPointerLeaves(event) {
    if (!event.currentTarget.contains(document.activeElement)) {
      onCollapse(experience.role);
    }
  }

  return (
    <article
      className={`role-experience-panel role-${experience.role} ${isActive ? "is-active" : ""} ${isMuted ? "is-muted" : ""}`}
      tabIndex="0"
      role="group"
      aria-expanded={isActive}
      aria-labelledby={`${experience.role}-experience-title`}
      aria-describedby={descriptionId}
      onMouseEnter={() => onExpand(experience.role)}
      onMouseLeave={collapseAfterPointerLeaves}
      onFocus={() => onExpand(experience.role)}
      onBlur={collapseWhenUnfocused}
      onClick={revealPanel}
      onKeyDown={handlePanelKeyDown}
    >
      <div className="role-panel-glow" aria-hidden="true" />
      <div className="role-panel-summary">
        <div className="role-panel-topline">
          <span>{experience.eyebrow}</span>
          <span className="role-panel-index">
            {experience.role === "technical" ? "01" : "02"}
          </span>
        </div>
        <span className="role-panel-icon" aria-hidden="true">
          <ExperienceIcon />
        </span>
        <h2 id={`${experience.role}-experience-title`}>{experience.title}</h2>
        <p className="role-panel-short" id={descriptionId}>
          {experience.shortDescription}
        </p>
      </div>

      <div className="role-panel-expanded" aria-hidden={!isActive}>
        <p>{experience.expandedDescription}</p>
        <ul>
          {experience.features.map((feature) => {
            const FeatureIcon = feature.icon;
            return (
              <li key={feature.label}>
                <FeatureIcon aria-hidden="true" />
                <span>{feature.label}</span>
              </li>
            );
          })}
        </ul>
        <button
          className="role-enter-button"
          type="button"
          tabIndex={isActive ? 0 : -1}
          onClick={() => onSelect(experience.role)}
        >
          <span>{experience.buttonLabel}</span>
          <ArrowRight aria-hidden="true" />
        </button>
      </div>
    </article>
  );
}

function EchoGrainientBackground() {
  return (
    <div className="echo-grainient-background" aria-hidden="true">
      <Grainient
        color1="#ffffff"
        color2="#06B6D4"
        color3="#f35d5d"
        timeSpeed={1.35}
        colorBalance={0}
        warpStrength={1}
        warpFrequency={5}
        warpSpeed={2}
        warpAmplitude={50}
        blendAngle={0}
        blendSoftness={0.05}
        rotationAmount={500}
        noiseScale={2}
        grainAmount={0.1}
        grainScale={2}
        grainAnimated={false}
        contrast={1.5}
        gamma={1}
        saturation={1}
        centerX={0}
        centerY={0}
        zoom={0.9}
      />
    </div>
  );
}

function EchoLogo() {
  return (
    <div className="echo-logo" aria-label="Echo">
      <span className="echo-logo-mark" aria-hidden="true">
        <span className="echo-logo-letter">E</span>
        <span className="echo-logo-bars"><i /><i /><i /></span>
      </span>
      <span className="echo-logo-word">ECHO</span>
    </div>
  );
}
