# AGENTS.md — Developer Guide for DORA Copilot

> **This file is for the coding agent/IDE working on this repository
> (Claude Code, Codex, or a human).** It is durable development guidance:
> layout, stack, commands, conventions, and boundaries.
>
> It is **not** loaded into the chatbot's runtime prompt. The AI assistant's
> persona, standard operating procedure, guardrails, and response templates
> live in [`backend/agent/INSTRUCTIONS.md`](backend/agent/INSTRUCTIONS.md),
> which `instruction_loader.py` reads live on every chat request. Keep these
> two files separate: editing this one changes how the repo is developed;
> editing that one changes what real users see immediately.

---

## 1. Project purpose

A FastAPI + React conversational AI application ("DORA Copilot") that answers
questions about a real, read-only PostgreSQL database (**DoraDB**) holding
Jira issue data and DORA delivery metrics for the **DCPM** project. DeepSeek
(with a Google AI Studio / Ollama fallback) provides generative planning and
natural-language responses; every factual claim must be backed by an approved,
parameterized query executed in the same session.

## 2. Repository layout

```text
AGENTS.md                          # this file — IDE/development guidance only
.codex/                            # captured reference notes (not project-specific)
frontend/                          # React 18 + Vite chat UI
backend/
  main.py                          # FastAPI app + middleware/lifespan — composition root only
  config.py                        # typed Settings, loaded from .env
  schemas.py                       # Pydantic API request/response contracts
  conversation_context.py          # persisted per-conversation summary/cache builder
  conversation_repository.py       # conversation/message persistence (SQLAlchemy)
  dashboard_service.py             # cached Jira dashboard aggregates (REST, non-chat)
  knowledge_service.py             # verified Jira documentation lookup
  knowledge/jira_issues.md         # the verified documentation itself
  llm.py                           # multi-provider LLM client (DeepSeek/Gemini/Ollama)
  tts.py                           # ElevenLabs TTS with monthly quota accounting
  doradb_agent.py                  # thin backward-compatible re-export of the agent
  context/
    data_dictionary.yaml           # governed dimension definitions (loaded at runtime)
  api/                             # FastAPI routers — request handling lives here
    dependencies.py, conversations.py, chat.py, dashboard.py, system.py, tts.py
  tools/                           # capabilities the agent may call
    query_execution.py             # the one tool: run an approved DoraDB query
  services/                        # deterministic, reusable business/domain logic
    chart_generation.py, comparison.py, trend_analysis.py, anomaly_detection.py,
    filter_extraction.py, intent_matching.py, metric_selection.py,
    entity_grounding.py, dimension_discovery.py
  database/                        # data access, isolated from AI behavior
    db.py                          # writable runtime DB (conversations, TTS usage)
    doradb.py                      # read-only DoraDB engine + approved parameterized SQL
    doradb_catalog.py              # approved query/metric catalogue (metadata, no SQL)
  memory/                          # conversation state, top-level (not agent-only)
    memory.py                      # bounded in-process session memory (LRU)
    result_cache.py                # per-conversation query-result reuse/follow-up eligibility
  agent/                           # the governed LangGraph agent
    INSTRUCTIONS.md                # RUNTIME system prompt (see warning above)
    instruction_loader.py          # reads INSTRUCTIONS.md + skills live, every request
    agent_definition.py            # AdvancedDoraDbAgent: builds/configures the graph
    context.py                     # RuntimeContext — one chat turn's application state
    orchestrator.py                # AgentOrchestrator: the LangGraph node implementations
  planner.py                     # model-first intent/plan generation with controlled fallbacks
  request_router.py              # legacy deterministic Jira route definitions (not primary runtime understanding)
    skill_registry.py              # discovers/matches/loads skill playbooks
    controls/
      execution_control.py         # timeouts, retry/tool-call limits, confidence gate
      permission_control.py        # static allowlist: permitted query IDs/filters/limits
      response_controller.py       # tone/length/format/evidence/follow-up policy
    guardrails/
      input_guardrail.py           # pre-planning safety check on the raw message
      tool_guardrail.py            # validates/blocks a proposed tool call (enforce_plan)
      output_guardrail.py          # restricted-field stripping + generated-text safety check
    validators/
      request_validator.py         # structural shape checks on a proposed plan
      data_validator.py            # required fields, types, duplicates, empty results
      metric_validator.py          # numeric ranges, business rules, date parseability
      evidence_validator.py        # every numeric claim must be grounded in evidence
      response_validator.py        # conclusion consistency, required limitations, safety
    response/
      responder.py                 # composes the final answer (was orchestrator._respond)
      response_models.py           # ChartData/DataTable — the agent's output contract
    skills/                        # runtime domain-skill playbooks (SKILL.md per skill)
tests/
  unit/                            # pure functions / mocked dependencies
  integration/                     # real DB engine or the full agent .chat() pipeline
evals/
  evaluation_cases.yaml            # representative questions + expected intent/query
  run_evals.py                     # behavior-quality harness (see Section 4 and evals/README.md)
```

## 3. Tech stack

- **Backend:** FastAPI (Python 3.11+), LangGraph, SQLAlchemy 2.0, Pydantic v2
- **Frontend:** React 18 + Vite, Chart.js
- **LLM:** DeepSeek (OpenAI-compatible chat-completions API), with Google AI
  Studio and Ollama as configurable alternate providers (`backend/llm.py`)
- **Databases:** PostgreSQL DoraDB (read-only, external) for analysis;
  SQLite/PostgreSQL runtime DB (`backend/database/db.py`) for conversations + TTS usage
- **TTS:** ElevenLabs (quota-gated)

## 4. Architecture — where each responsibility lives

| Responsibility | Lives in |
|---|---|
| API / chat interface | `backend/api/` (routers), `backend/main.py` (composition root) |
| Runtime agent instructions (system prompt) | `backend/agent/INSTRUCTIONS.md`, read by `instruction_loader.py` |
| Runtime task-specific skills | `backend/agent/skills/<name>/SKILL.md`, matched/loaded by `skill_registry.py` |
| Planning / intent routing | `backend/agent/planner.py`, `request_router.py` |
| Runtime agent definition | `backend/agent/agent_definition.py` |
| Runtime context | `backend/agent/context.py` (`RuntimeContext`) |
| Orchestration (node implementations) | `backend/agent/orchestrator.py` (`AgentOrchestrator`) |
| Response composition | `backend/agent/response/responder.py` |
| Response control (tone/length/format/evidence/follow-up) | `backend/agent/controls/response_controller.py` |
| Execution control (timeouts, retry/tool-call limits, approval) | `backend/agent/controls/execution_control.py` |
| Permission control (static query/filter allowlist) | `backend/agent/controls/permission_control.py` |
| Input guardrail | `backend/agent/guardrails/input_guardrail.py` |
| Tool guardrail (blocks disallowed/malformed tool calls) | `backend/agent/guardrails/tool_guardrail.py` (`enforce_plan`) |
| Output guardrail (restricted-field stripping + leak check) | `backend/agent/guardrails/output_guardrail.py` |
| Tools + approved query catalogue | `backend/tools/query_execution.py`, `backend/database/doradb_catalog.py` |
| Data access (parameterized, read-only SQL) | `backend/database/doradb.py`, `db.py` |
| Domain/business logic (deterministic analytics) | `backend/services/*.py` |
| Validation (request/data/metric/evidence/response) | `backend/agent/validators/*.py` |
| Conversation state / memory | `backend/memory/*.py`, `backend/conversation_context.py`, `conversation_repository.py` |
| Tracing / observability | `backend/agent/audit.py`, `/api/audit/recent`, `response_policy`/`input_guardrail` in every turn's metadata |
| Testing | `tests/unit/`, `tests/integration/` |
| Agent behavior evaluation | `evals/` (informational, not pytest-gated — see `evals/README.md`) |
| AI IDE dev skills (Codex/coding workflows) | none yet — see Section 8 before adding any |

This mapping is the source of truth. Do not create a parallel module for a
responsibility that already lives somewhere on this list — move or improve
the existing one instead.

## 5. Runtime vs IDE instruction separation

This project used to load the entire root `AGENTS.md` directly into the
chatbot's system prompt (including this developer-facing content), and stored
its runtime skill playbooks under `.codex/skills/`, a location conventionally
reserved for IDE-discoverable development skills. Both were restructured:

- **Runtime system prompt** → `backend/agent/INSTRUCTIONS.md` (persona,
  standard operating procedure, skill-trigger table, steering, guardrails,
  validation checklist, response templates, out-of-context policy). Read live
  by `instruction_loader.py` on every request.
- **Runtime domain skills** → `backend/agent/skills/<name>/SKILL.md`
  (19 Jira/DORA playbooks). Discovered, matched to the current message, and
  loaded by `skill_registry.py`, which `response/responder.py` calls (via
  `instruction_loader.load_system_instructions`) on every turn. `skill_registry.py`
  was added because the original scan only ever pulled a skill's
  `name`/`description` into the prompt and discarded its body — the model
  never actually received the matched skill's query IDs, interpretation
  rules, response template, or common mistakes despite `INSTRUCTIONS.md`
  §2 saying to "load and follow" it. Matching is deterministic (regex per
  skill, tested in `tests/unit/test_skill_registry.py`), not left to the
  model to re-derive from the routing table every turn.
- **This file** → durable IDE/development guidance only. Never read by the
  running application.

When adding to either instruction file, put durable engineering guidance
here and product/persona/policy behavior in `INSTRUCTIONS.md`. Do not merge
them back into one file.

## 6. Commands

```powershell
# Backend
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload --port 8000
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe evals\run_evals.py

# Frontend
Set-Location frontend
npm run dev
npm run build
npm test
```

Or use the VS Code workspace task: `Terminal -> Run Task -> DORA: Start All`
(see `DORA-Copilot.code-workspace`).

## 7. Coding conventions

- **No arbitrary SQL.** All DoraDB access goes through the approved,
  parameterized query catalogue in `database/doradb_catalog.py` + `doradb.py`.
  Adding a new query means adding a catalogue entry and a static SQL
  template, never string-built SQL.
- **Guardrails and validation are enforced in code**, not only in
  `INSTRUCTIONS.md` prose. `guardrails/tool_guardrail.py` allowlists tools/
  filters/limits; `validators/*.py` check metric ranges and evidence
  grounding deterministically. Prompt text is a second layer, not the only
  layer.
- **One deterministic implementation per calculation.** Business logic
  (comparisons, trends, anomaly detection, chart specs, filter extraction)
  lives once in `backend/services/`, reused by both the planner and the
  responder — never recompute the same thing in a prompt.
- Keep new state on `AgentState` (`agent/state.py`) typed, not stringly keyed.
- Prefer extending an existing module over adding a new one; only split when
  a file mixes genuinely unrelated responsibilities or needs different tests
  — most `controls/`/`guardrails/`/`validators/` files here are intentionally
  small and single-purpose; don't further fragment them without a real new
  responsibility to isolate.
- `backend/agent/orchestrator.py`'s `AgentOrchestrator` and
  `agent_definition.py`'s `AdvancedDoraDbAgent(AgentOrchestrator)` split node
  *behavior* from agent *configuration*; `response/responder.py` is a
  separate `Responder` object (not a method on the agent) so it can be
  constructed and tested with just an LLM client, no graph required.

## 8. Adding a Codex/IDE development skill

`.agents/` and `.codex/skills/` are reserved for **coding-workflow** skills
(e.g. "add-api-endpoint", "database-migration", "security-review") — reusable
development recipes, not product behavior. This project does not currently
have any; don't create placeholder ones. Add a skill only when a development
workflow is genuinely repeated, has a clear trigger, and benefits from a
fixed sequence. Domain/product skills (Jira/DORA playbooks) belong in
`backend/agent/skills/`, not here.

## 9. Security expectations

- DoraDB connections are opened with `default_transaction_read_only=on` and a
  statement timeout; never remove this.
- Only `APPROVED_QUERY_IDS` in `database/doradb_catalog.py` may execute;
  filters are normalized and validated per-query in
  `database/doradb.py::_normalize_filters`, and re-validated independently by
  `guardrails/tool_guardrail.py` before that.
- Credentials (`DEEPSEEK_API_KEY`, `DORADB_PASSWORD`, `ELEVENLABS_API_KEY`,
  etc.) live only in `.env` (git-ignored). Never log them, never send them to
  the model, never add them to `INSTRUCTIONS.md` or any skill file.
- `backend/context/data_dictionary.yaml` is the only file under
  `backend/context/` that production code loads (`doradb_catalog.py`). Don't
  add speculative YAML config there that nothing reads.
- The unsafe-request guardrail (`services/intent_matching.py::_UNSAFE`) is a
  regex heuristic, not exhaustive — see `evals/README.md` for known gaps
  (e.g. credential-request phrasing) before assuming it catches everything.

## 10. Definition of done / how to verify a change

1. `.\.venv\Scripts\python.exe -m pytest tests -q` passes.
2. If you touched `frontend/`, `npm run build` (and `npm test` if relevant)
   passes.
3. If you changed agent behavior (planner, control, guardrail, validator,
   response_controller, orchestrator), add or update a test under
   `tests/unit/` or `tests/integration/` — don't rely on manual chat testing
   alone. Consider running `evals\run_evals.py` too if you touched intent
   classification or planning.
4. If you changed `backend/agent/INSTRUCTIONS.md` or any file under
   `backend/agent/skills/`, treat it as a product change: the effect
   is live on the next chat request, not just on redeploy.
5. No new duplicate implementation of an agent runner, planner, guardrail,
   validator, or query catalogue was introduced — reuse or extend the modules
   listed in Section 4.
