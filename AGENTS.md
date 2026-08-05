# DORA Copilot — Agent Instructions

> **Auto-loaded by the AI agent at the start of every session.**
> Treat everything below as binding project rules.

---

## ⚠️ RESPONSE PROTOCOL (ACTIVE — DO NOT SKIP)

**Before answering ANY user prompt — including greetings, follow-ups, clarifications, and code tasks — you MUST begin your response with exactly:**

```
YES TUAN.
```

This is a non-negotiable, always-on directive. No exceptions for brevity, casual tone, or conversational flow. The phrase must appear verbatim as the first line of every response, before any other text, code block, or tool output commentary.

*Why:* This rule exists to verify that the AGENTS.md instruction-loading mechanism is functioning correctly. It will be removed once confirmed.

---

## Project Identity

- **Name:** DORA Copilot (DORA Intelligence)
- **Purpose:** Conversational AI application for querying a real PostgreSQL DoraDB database using natural language. DeepSeek provides generative planning and natural-language responses. There is no synthetic/Jira project mode and no local LLM runtime.
- **Repo root:** `d:\DevTools\BC`

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI (Python 3.11+) |
| Frontend framework | React 18 + Vite |
| Database (analytics) | PostgreSQL (DoraDB) — **read-only** |
| Database (runtime) | SQLite (ElevenLabs usage counter only) |
| LLM provider | DeepSeek (via OpenAI-compatible chat-completions API) |
| Agent orchestration | LangChain + LangGraph |
| Charts (frontend) | Chart.js + react-chartjs-2 |
| Styling | Lucide React icons, Inter font, custom CSS |
| TTS | ElevenLabs (on-demand, quota-gated) |
| Tests | pytest + pytest-cov |

---

## Architecture Rules

1. **DoraDB is strictly read-only.** The agent system must never generate or execute `INSERT`, `UPDATE`, `DELETE`, `DROP`, or arbitrary SQL. Only the approved query tools in the catalogue may be used.
2. **Credentials never leave the backend.** The LLM never receives database credentials or executable SQL. All queries go through the parameterized DoraDB agent layer.
3. **The LLM is the primary planner.** DeepSeek handles intent planning and answer synthesis. Deterministic routing is a fallback only — used when the planner fails or returns an invalid plan.
4. **No hard-coded dimensions.** Project, squad, release, issue-type, and status values are discovered dynamically from DoraDB via `list_dimension_values`. Never embed dimension values in code or prompts.
5. **Answer honesty.** A response must never claim to be based on DoraDB unless a query actually executed in that turn.

---

## Approved DoraDB Query Tools

These are the ONLY functions allowed to touch DoraDB:

- `list_dimension_values`
- `dora_metrics_by_year`
- `dora_metrics_by_squad`
- `dora_metrics_release_detail`
- `feature_vs_release_frequency`
- `feature_vs_user_story`
- `story_to_feature_ratio`

Any new query tool must be added to `backend/doradb_catalog.py` and the allowlist in `backend/agent_system/control.py`.

---

## Coding Standards

### Python (Backend)

- Python 3.11+. Use `from __future__ import annotations` in all new modules.
- Type hints on all public function signatures. Use `|` union syntax, not `Optional[X]`.
- Pydantic v2 (`pydantic-settings`) for all configuration models.
- SQLAlchemy 2.0+ style — use `select()` statements, not `Query` objects.
- FastAPI dependency injection for DB sessions and settings.
- Logging via `logging.getLogger(__name__)` — never `print()`.
- Follow existing patterns: see `backend/config.py` for settings, `backend/main.py` for route structure.

### JavaScript/React (Frontend)

- React 18 with functional components and hooks only — no class components.
- Use Vite for dev/build. Module type: `"type": "module"`.
- Charts via `react-chartjs-2` wrapping Chart.js.
- Icons from `lucide-react` only.
- Font: Inter Variable from `@fontsource-variable/inter`.
- Follow existing component structure in `frontend/src/components/`.

### General

- `.env` is git-ignored. Never commit secrets, keys, or passwords.
- Use `.env.example` as the template for required environment variables.
- Follow existing naming conventions in each directory.
- Prefer composition over inheritance.

---

## Key Files Reference

| File | Purpose |
|---|---|
| `backend/main.py` | FastAPI entry point, lifespan, routes |
| `backend/config.py` | Typed settings from `.env` |
| `backend/doradb.py` | DoraDB connection, query execution, error types |
| `backend/doradb_catalog.py` | Metric definitions and query catalogue |
| `backend/agent_system/` | LangGraph agent: planner, memory, control, graph, state, validation |
| `backend/context/` | YAML config: intents, schema, guardrails, skills, steering, memory, data dictionary |
| `backend/skills/` | Deterministic skills: intent matching, filter extraction, dimension discovery, entity grounding |
| `backend/tests/` | pytest test suite |
| `frontend/src/App.jsx` | React app root |
| `frontend/src/components/Chat.jsx` | Main chat component |
| `frontend/src/components/Grainient.jsx` | Background animation component |

---

## Constraints

- **No write operations on DoraDB.** This is a hard security boundary.
- **No credential exposure to the LLM or frontend.**
- **No local LLM runtime.** The app depends on the DeepSeek API.
- **Agent workflow is governed.** Max tool calls: 2, max retries: 1, timeout: 90s (configurable in `.env`).
- **Result limits enforced.** Default 1000 rows, detail limit 50 rows.
- **ElevenLabs TTS is quota-gated.** Monthly character limit enforced via SQLite counter.
