import test from "node:test";
import assert from "node:assert/strict";

const storage = new Map();
globalThis.window = {
  localStorage: {
    getItem: (key) => storage.get(key) || null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  },
  crypto: { randomUUID: () => "development-session-0001" },
};
const service = await import("../src/services/conversations.js");

test("development identity persists across refresh-style service calls", () => {
  assert.equal(service.getDevelopmentSession(), "development-session-0001");
  window.crypto.randomUUID = () => "different";
  assert.equal(service.getDevelopmentSession(), "development-session-0001");
});

test("reopening maps persisted messages and structured response content", () => {
  assert.deepEqual(service.messagesFromConversation({ messages: [
    { id: "1", role: "user", content: "Question", structured_content: {} },
    { id: "2", role: "assistant", content: "Answer", structured_content: { warnings: ["Note"] } },
  ]}), [
    { id: "1", role: "user", text: "Question" },
    { id: "2", role: "assistant", text: "Answer", warnings: ["Note"] },
  ]);
});

test("list and create are scoped and starting new does not delete history", async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return { ok: true, json: async () => options.method === "POST" ? { id: "new" } : { conversations: [] } };
  };
  await service.listConversations();
  await service.createConversation({ workspace: "technical", project_scope: {} });
  assert.deepEqual(calls.map((call) => call.options.method || "GET"), ["GET", "POST"]);
  assert.equal(calls.some((call) => call.options.method === "DELETE"), false);
  assert.equal(calls[0].options.headers["X-Development-Session"], "development-session-0001");
});
