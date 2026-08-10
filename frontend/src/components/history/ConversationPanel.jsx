import { useDeferredValue, useMemo, useState } from "react";
import {
  BarChart3,
  ChevronDown,
  FileText,
  MessageSquareText,
  Plus,
  Search,
  Settings,
  Trash2,
} from "lucide-react";
import { getRoleDashboardConfig } from "../../config/roleDashboardConfig";

const GROUP_ORDER = ["Today", "Yesterday", "Previous 7 Days", "Older"];

export function conversationGroup(value, now = new Date()) {
  const date = new Date(value || 0);
  if (Number.isNaN(date.getTime())) return "Older";
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const itemDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const days = Math.floor((today - itemDay) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days <= 7) return "Previous 7 Days";
  return "Older";
}

export default function ConversationPanel({
  conversations,
  status,
  error,
  activeConversationId,
  operationalRole,
  onRoleChange,
  onNew,
  onOpen,
  onArchive,
  onRetry,
  onNavigate,
}) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());
  const roleConfig = getRoleDashboardConfig(operationalRole);
  const groups = useMemo(() => {
    const result = Object.fromEntries(GROUP_ORDER.map((group) => [group, []]));
    conversations
      .filter((item) => !deferredQuery || `${item.title || ""} ${item.workspace || ""}`.toLowerCase().includes(deferredQuery))
      .forEach((item) => result[conversationGroup(item.updated_at || item.created_at)].push(item));
    return result;
  }, [conversations, deferredQuery]);

  return (
    <aside className="conversation-panel zara-sidebar" aria-label="Zara workspace navigation">
      <div className="zara-sidebar-brand"><span>Zara</span><small>Decision workspace</small></div>
      <nav className="zara-main-navigation" aria-label="Main workspace navigation">
        <button type="button" className="active" onClick={() => onNavigate("dashboard")}><BarChart3 aria-hidden="true" /><span>Dashboard</span></button>
        <button type="button" onClick={() => onNavigate("reports")}><FileText aria-hidden="true" /><span>Reports</span></button>
        <button type="button" onClick={() => onNavigate("assistant")}><MessageSquareText aria-hidden="true" /><span>Zara Assistant</span></button>
        <button type="button" onClick={() => document.getElementById("workspace-role-select")?.focus()}><Settings aria-hidden="true" /><span>Settings</span></button>
      </nav>

      <button className="conversation-new-button" type="button" onClick={onNew}><Plus aria-hidden="true" /> New conversation</button>

      <details className="recent-chats-accordion">
        <summary><span><MessageSquareText aria-hidden="true" /> Recent Chats</span><ChevronDown aria-hidden="true" /></summary>
        <div className="recent-chats-content">
          <label className="conversation-search"><Search aria-hidden="true" /><span className="sr-only">Search conversations</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search chats" /></label>
          <div className="conversation-groups">
            {status === "loading" && <p role="status">Loading conversations…</p>}
            {status === "error" && <div className="conversation-load-error" role="alert"><span>{error}</span><button type="button" onClick={onRetry}>Retry</button></div>}
            {status === "ready" && conversations.length === 0 && <p>No saved conversations yet.</p>}
            {status === "ready" && conversations.length > 0 && GROUP_ORDER.map((group) => groups[group].length > 0 && (
              <section key={group} aria-labelledby={`conversation-group-${group.replaceAll(" ", "-")}`}>
                <h3 id={`conversation-group-${group.replaceAll(" ", "-")}`}>{group}</h3>
                {groups[group].map((conversation) => (
                  <div className={`conversation-row ${conversation.id === activeConversationId ? "active" : ""}`} key={conversation.id}>
                    <button type="button" onClick={() => onOpen(conversation.id)} aria-current={conversation.id === activeConversationId ? "page" : undefined}>
                      <strong title={conversation.title}>{conversation.title || "Untitled conversation"}</strong>
                      <span>{conversation.workspace || roleConfig.workspace} workspace</span>
                    </button>
                    <button className="conversation-archive" type="button" onClick={() => onArchive(conversation.id)} aria-label={`Archive ${conversation.title || "conversation"}`} title="Archive conversation"><Trash2 aria-hidden="true" /></button>
                  </div>
                ))}
              </section>
            ))}
            {status === "ready" && conversations.length > 0 && GROUP_ORDER.every((group) => groups[group].length === 0) && <p>No conversations match your search.</p>}
          </div>
        </div>
      </details>

      <div className="conversation-panel-role">
        <label htmlFor="workspace-role-select">Workspace role</label>
        <select id="workspace-role-select" value={operationalRole} onChange={(event) => onRoleChange(event.target.value)}>
          <option value="scrum_master">Scrum Master</option>
          <option value="head_of_department">Head of Department</option>
        </select>
        <span>{roleConfig.access.join(" · ")}</span>
      </div>
    </aside>
  );
}
