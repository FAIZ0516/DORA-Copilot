const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/$/, "");
export const DEVELOPMENT_SESSION_KEY = "echo-development-session";
export const ACTIVE_CONVERSATION_KEY = "echo-active-conversation";

export function getDevelopmentSession(storage = window.localStorage, cryptoApi = window.crypto) {
  const existing = storage.getItem(DEVELOPMENT_SESSION_KEY);
  if (existing) return existing;
  const value = cryptoApi?.randomUUID?.() || `development-${Date.now()}-${Math.random()}`;
  storage.setItem(DEVELOPMENT_SESSION_KEY, value);
  return value;
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Development-Session": getDevelopmentSession(),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed with status ${response.status}`);
  }
  return response.json();
}

export function listConversations() {
  return request("/api/conversations");
}

export function getConversation(id) {
  return request(`/api/conversations/${id}`);
}

export function createConversation(payload) {
  return request("/api/conversations", { method: "POST", body: JSON.stringify(payload) });
}

export function archiveConversation(id) {
  return request(`/api/conversations/${id}`, { method: "DELETE" });
}

export function sendChat(payload) {
  return request("/api/chat", { method: "POST", body: JSON.stringify(payload) });
}

export function messagesFromConversation(conversation) {
  return (conversation.messages || [])
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({
      id: message.id,
      role: message.role,
      text: message.content,
      ...(message.structured_content || {}),
    }));
}
