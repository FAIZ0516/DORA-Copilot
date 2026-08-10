import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { buildDashboardContext, defaultDashboardView } from "./dashboardState";

const DashboardContext = createContext(null);

export function DashboardProvider({ role, project, children }) {
  const [selectedRole, setSelectedRole] = useState(role || "scrum_master");
  const [selectedProject, setSelectedProject] = useState(project || "DCPM");
  const [selectedSquad, setSelectedSquad] = useState("");
  const [selectedRelease, setSelectedRelease] = useState("");
  const [selectedSprint, setSelectedSprint] = useState("");
  const [dateRange, setDateRange] = useState({ from: "", to: "" });
  const [selectedMetric, setSelectedMetric] = useState("");
  const [activeView, setActiveView] = useState(defaultDashboardView(role));
  const [conversationId, setConversationId] = useState(null);
  const [selectedSquadRow, setSelectedSquadRow] = useState(null);
  const [currentMetricValue, setCurrentMetricValue] = useState(null);

  useEffect(() => {
    if (!role) return;
    setSelectedRole(role);
    setActiveView(defaultDashboardView(role));
    setSelectedSquad("");
    setSelectedSquadRow(null);
  }, [role]);

  useEffect(() => {
    if (project) setSelectedProject(project);
  }, [project]);

  const value = useMemo(() => {
    const dashboardContext = (overrides = {}) => buildDashboardContext({
      selectedRole,
      activeView,
      selectedProject,
      selectedSquad,
      selectedRelease,
      selectedSprint,
      dateRange,
      selectedMetric,
      selectedSquadRow,
      currentMetricValue,
    }, overrides);

    return {
      selectedRole,
      setSelectedRole,
      selectedProject,
      setSelectedProject,
      selectedSquad,
      setSelectedSquad,
      selectedRelease,
      setSelectedRelease,
      selectedSprint,
      setSelectedSprint,
      dateRange,
      setDateRange,
      selectedMetric,
      setSelectedMetric,
      activeView,
      setActiveView,
      conversationId,
      setConversationId,
      selectedSquadRow,
      setSelectedSquadRow,
      currentMetricValue,
      setCurrentMetricValue,
      dashboardContext,
    };
  }, [
    selectedRole,
    selectedProject,
    selectedSquad,
    selectedRelease,
    selectedSprint,
    dateRange,
    selectedMetric,
    activeView,
    conversationId,
    selectedSquadRow,
    currentMetricValue,
  ]);

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboardContext() {
  const context = useContext(DashboardContext);
  if (!context) throw new Error("useDashboardContext must be used inside DashboardProvider");
  return context;
}
