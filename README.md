# DORA Intelligence — DeepSeek, Google AI Studio, or Ollama + real DoraDB

A FastAPI and React conversational AI application for the real local PostgreSQL
DoraDB database. DeepSeek, Google Gemini, or a local Ollama model provides
generative planning and natural-language responses. There is no synthetic Jira
project mode.

## Runtime architecture

```text
User question
  -> user-scoped persistent conversation and recent-message window
  -> bounded conversation summary and compatible result-cache lookup
  -> deterministic Jira knowledge/metadata/data router
  -> cached relevant excerpts from backend/knowledge/jira_issues.md
  -> configured LLM intent planner
  -> conversation response, or approved DoraDB query plan
  -> deterministic query/filter/limit controls
  -> parameterized read-only PostgreSQL execution
  -> result validation and one controlled repair
  -> deterministic comparison, trend, anomaly, chart, and table skills
  -> configured LLM evidence synthesis
  -> answer consistency validation
  -> privacy-safe audit metadata
```

DeepSeek uses its OpenAI-compatible Chat Completions API, Google Gemini uses the
official Google GenAI SDK, and Ollama uses its local HTTP API. Every provider
remains behind the same deterministic query allowlist and receives no database
credentials or executable SQL.

## Required configuration

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_THINKING_ENABLED=true

DORADB_HOST=127.0.0.1
DORADB_PORT=5432
DORADB_NAME=doradb
DORADB_USER=your_readonly_username
DORADB_PASSWORD=your_readonly_password
DORADB_PROJECT_KEY=DCPM
```

To use Google AI Studio instead of DeepSeek:

```env
LLM_PROVIDER=google-ai-studio
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-3.6-flash
```

To use local Ollama:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT_SECONDS=90
```

Install the selected model before starting the backend:

```powershell
ollama pull qwen3:4b
```

If the Ollama application is not already serving in the background, run
`ollama serve` in a separate terminal.

Provider API keys and the DoraDB password belong only in `.env`, which is ignored
by Git. The configured model never receives database credentials or executable
SQL. Dataset answers are generated only after the backend executes an approved,
parameterized read-only query and validates its results.

## Conversation behavior

- Safe general questions and software-delivery guidance are answered directly
  by the configured provider.
- Dataset questions execute the real DoraDB tools first.
- A response never claims to be based on DoraDB unless a query ran in that turn.
- Database writes, arbitrary SQL, and credential disclosure remain prohibited.
- Suggested questions are workspace-specific and use the same request path as
  manually typed messages.
- Conversations and privacy-safe structured response metadata persist in the
  writable runtime database. DoraDB remains a separate read-only connection.
- The browser sends `X-Development-Session` as a temporary development identity.
  Production deployments must replace it with an authenticated user identity.

## Conversation storage and context

SQLite is the default writable development store. For deployment, set
`DATABASE_URL` to a writable PostgreSQL database and run the migration below.
The migration uses the existing `ai_assistant.conversations` and
`ai_assistant.messages` table shape; it does not write to analytical DoraDB.

```powershell
psql "$env:DATABASE_URL" -f backend/migrations/001_conversations.sql
```

Each model turn receives system controls, relevant Jira knowledge sections, a
bounded persistent summary, the 12 most recent messages, compatible bounded
query results, and the current question. Summaries retain workspace, project
scope, filters, query identifiers, findings, warnings, and unresolved
clarifications. Sensitive Jira text and identity fields are excluded.

Successful non-empty query results are reusable for five minutes within the
same conversation and project scope. Explicit refresh/current/latest requests,
changed scope or filters, stale/incomplete results, missing required fields,
and zero-row results prevent reuse. Development logs identify
`CONTEXT_REUSED`, `QUERY_RESULT_REUSED`, `DATABASE_QUERY_EXECUTED`, and
`KNOWLEDGE_ONLY_RESPONSE` decisions.

## Jira knowledge and routing

The verified Jira reference is loaded once and split into cached Markdown
sections. Only relevant excerpts are selected for a question. The pre-query
router distinguishes:

- `DATABASE_METADATA`: visible tables, views, and columns through PostgreSQL
  metadata queries;
- `KNOWLEDGE_EXPLANATION`: verified definitions and limitations without a
  business-data query;
- `DATA_RETRIEVAL`: bounded aggregate or distinct-value queries;
- `ANALYSIS`: data retrieval followed by evidence-grounded interpretation;
- `CLARIFICATION_REQUIRED`: ambiguous business terms that need a definition or
  scope before querying.

Zero matching rows are reported separately from missing schema objects, missing
required fields, unsupported metrics, and query failures. Sensitive Jira text
and identity fields are excluded from the AI evidence path.

## Jira Delivery Overview

The chat home loads a compact version-one snapshot dashboard from
`public.tbl_gdt_dte_jira_issues`. It shows total issues, locally defined open
work, current impeded issues, missing squad coverage, status categories, issue
types, calendar-age buckets, and aggregate data-quality checks. It does not
present Jira issue counts as DORA performance, productivity, delivery success,
or business value.

Dashboard aggregates are cached for 60 seconds per project key. Changing the
project key uses a separate cache entry. The refresh button requests
`refresh=true`, executes every approved aggregate again, and replaces the
cached snapshot. Dashboard responses never contain issue summaries or people.

## Approved DoraDB query tools

- `database_schema_objects`
- `database_table_presence`
- `database_columns`
- `database_metric_columns`
- `database_squad_sources`
- `jira_distinct_squads`
- `jira_bug_counts_by_squad`
- `jira_issue_counts_by_status`
- `jira_unresolved_older_than_days`
- `jira_backlog_by_status`
- `jira_bug_resolution_trend`
- `jira_dashboard_kpis`
- `jira_dashboard_status_categories`
- `jira_dashboard_issue_types`
- `jira_dashboard_open_ageing`
- `jira_dashboard_data_quality`
- `jira_open_work_breakdown`
- `jira_impeded_breakdown`
- `dora_metrics_by_year`
- `dora_metrics_by_squad`
- `dora_metrics_release_detail`
- `feature_vs_release_frequency`
- `feature_vs_user_story`
- `story_to_feature_ratio`

## Run

Open `DORA-Copilot.code-workspace`, then choose:

`Terminal -> Run Task -> DORA: Start All`

Or start the services manually:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload --port 8000
```

```powershell
Set-Location frontend
npm run dev
```

Open `http://localhost:5173`.

## API routes

- `POST /api/chat`
- `POST /api/conversations`
- `GET /api/conversations`
- `GET /api/conversations/{conversation_id}`
- `POST /api/conversations/{conversation_id}/messages`
- `DELETE /api/conversations/{conversation_id}`
- `POST /api/reset-session`
- `POST /api/tts`
- `GET /api/health`
- `GET /api/projects`
- `GET /api/jira-dashboard?project_key=DCPM&refresh=false`
- `GET /api/metrics`
- `GET /api/query-catalogue`
- `GET /api/audit/recent`

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
Set-Location frontend
npm test
npm run build
```
