import {
  History,
  LayoutDashboard,
  MessageSquareText,
  PanelLeftClose,
  PanelLeftOpen,
  RotateCcw,
} from "lucide-react";

const PANEL_META = {
  history: { title: "Workspace Navigation", shortTitle: "Menu", icon: History },
  dashboard: { title: "Analytics Dashboard", shortTitle: "Dashboard", icon: LayoutDashboard },
  chat: { title: "Zara Assistant", shortTitle: "Zara", icon: MessageSquareText },
};

function columnsFor(panels) {
  return [
    panels.history ? "minmax(210px, 236px)" : "48px",
    panels.dashboard ? "minmax(600px, 1fr)" : "48px",
    panels.chat ? "minmax(320px, 360px)" : "48px",
  ].join(" ");
}

function WorkspacePanel({ panel, visible, onToggle, children }) {
  const meta = PANEL_META[panel];
  const Icon = meta.icon;
  return (
    <section className={`workspace-panel workspace-panel-${panel} ${visible ? "is-expanded" : "is-collapsed"}`} aria-label={meta.title} data-panel={panel}>
      {visible ? (
        <>
          <header className="workspace-panel-header">
            <div><Icon aria-hidden="true" /><span>{meta.title}</span></div>
            <button type="button" onClick={onToggle} aria-label={`Collapse ${meta.title}`} title={`Collapse ${meta.title}`}><PanelLeftClose aria-hidden="true" /></button>
          </header>
          <div className="workspace-panel-content">{children}</div>
        </>
      ) : (
        <button className="workspace-panel-rail" type="button" onClick={onToggle} aria-label={`Expand ${meta.title}`}>
          <Icon aria-hidden="true" /><span>{meta.shortTitle}</span><PanelLeftOpen aria-hidden="true" />
        </button>
      )}
    </section>
  );
}

export default function ThreePanelWorkspace({ layout, history, dashboard, chat }) {
  const { panels, mobilePanel, togglePanel, showPanel, restoreDefault } = layout;
  return (
    <div className="three-panel-workspace">
      <header className="workspace-layout-toolbar" aria-label="Workspace panel controls">
        <div>
          {Object.entries(PANEL_META).map(([key, meta]) => {
            const Icon = meta.icon;
            return (
              <button className={panels[key] ? "is-visible" : ""} type="button" key={key} onClick={() => togglePanel(key)} aria-pressed={panels[key]}>
                <Icon aria-hidden="true" /> {panels[key] ? `Hide ${meta.shortTitle}` : `Show ${meta.shortTitle}`}
              </button>
            );
          })}
        </div>
        <button type="button" onClick={restoreDefault}><RotateCcw aria-hidden="true" /> Restore default</button>
      </header>

      <nav className="workspace-mobile-tabs" aria-label="Workspace views">
        {Object.entries(PANEL_META).map(([key, meta]) => {
          const Icon = meta.icon;
          return (
            <button type="button" key={key} className={mobilePanel === key ? "active" : ""} onClick={() => showPanel(key)} aria-current={mobilePanel === key ? "page" : undefined}>
              <Icon aria-hidden="true" /> {meta.shortTitle}
            </button>
          );
        })}
      </nav>

      <div className="workspace-panels" data-mobile-panel={mobilePanel} style={{ "--workspace-columns": columnsFor(panels) }}>
        <WorkspacePanel panel="history" visible={panels.history} onToggle={() => togglePanel("history")}>{history}</WorkspacePanel>
        <WorkspacePanel panel="dashboard" visible={panels.dashboard} onToggle={() => togglePanel("dashboard")}>{dashboard}</WorkspacePanel>
        <WorkspacePanel panel="chat" visible={panels.chat} onToggle={() => togglePanel("chat")}>{chat}</WorkspacePanel>
      </div>
    </div>
  );
}
