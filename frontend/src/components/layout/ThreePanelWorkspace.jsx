import {
  History,
  LayoutDashboard,
  Maximize2,
  Minimize2,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Sparkles,
} from "lucide-react";
import Grainient, { ZARA_GRAINIENT_THEME } from "../Grainient";
import zaraWordmark from "../../assets/zara-wordmark.png";
import { panelColumns } from "../../hooks/usePanelLayout";

const PANEL_META = {
  history: { title: "Workspace Navigation", actionName: "menu", shortTitle: "Menu", icon: History, collapseIcon: PanelLeftClose, expandIcon: PanelLeftOpen },
  dashboard: { title: "Analytics Dashboard", actionName: "dashboard", shortTitle: "Dashboard", icon: LayoutDashboard, collapseIcon: Minimize2, expandIcon: Maximize2 },
  chat: { title: "Zara Assistant", actionName: "Zara", shortTitle: "Zara", icon: Sparkles, collapseIcon: PanelRightClose, expandIcon: PanelRightOpen },
};

function ZaraGrainientBackground() {
  return (
    <div className="zara-grainient-background" aria-hidden="true">
      <Grainient {...ZARA_GRAINIENT_THEME} />
    </div>
  );
}

function WorkspacePanel({ panel, visible, onToggle, children }) {
  const meta = PANEL_META[panel];
  const Icon = meta.icon;
  const CollapseIcon = meta.collapseIcon;
  const ExpandIcon = meta.expandIcon;
  const collapseLabel = `Collapse ${meta.actionName}`;
  const expandLabel = `Expand ${meta.actionName}`;
  return (
    <section className={`workspace-panel workspace-panel-${panel} ${visible ? "is-expanded" : "is-collapsed"}`} aria-label={meta.title} data-panel={panel}>
      {panel === "chat" && <ZaraGrainientBackground />}
      {visible ? (
        <>
          <header className="workspace-panel-header">
            {panel === "chat" ? (
              <div className="workspace-zara-brand" aria-label="ZARA AI Chat">
                <img src={zaraWordmark} alt="ZARA" /><strong>AI</strong><small>Engineering intelligence</small>
              </div>
            ) : <div><Icon aria-hidden="true" /><span>{meta.title}</span></div>}
            <button type="button" onClick={onToggle} aria-label={collapseLabel} title={collapseLabel}><CollapseIcon aria-hidden="true" /></button>
          </header>
          <div className="workspace-panel-content">{children}</div>
        </>
      ) : (
        <button className="workspace-panel-rail" type="button" onClick={onToggle} aria-label={expandLabel} title={expandLabel}>
          <Icon aria-hidden="true" /><span>{meta.shortTitle}</span><ExpandIcon aria-hidden="true" />
        </button>
      )}
    </section>
  );
}

export default function ThreePanelWorkspace({ layout, history, dashboard, chat }) {
  const { panels, mobilePanel, togglePanel, showPanel } = layout;
  return (
    <div className="three-panel-workspace">
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

      <div className="workspace-panels" data-mobile-panel={mobilePanel} style={{ "--workspace-columns": panelColumns(panels) }}>
        <WorkspacePanel panel="history" visible={panels.history} onToggle={() => togglePanel("history")}>{history}</WorkspacePanel>
        <WorkspacePanel panel="dashboard" visible={panels.dashboard} onToggle={() => togglePanel("dashboard")}>{dashboard}</WorkspacePanel>
        <WorkspacePanel panel="chat" visible={panels.chat} onToggle={() => togglePanel("chat")}>{chat}</WorkspacePanel>
      </div>
    </div>
  );
}
