# DORA Intelligence — DeepSeek + real DoraDB

A FastAPI and React conversational AI application for the real local PostgreSQL
DoraDB database. DeepSeek provides generative planning and natural-language
responses. There is no synthetic Jira project mode and no local LLM runtime.

## Runtime architecture

```text
User question
  -> structured session memory
  -> live DoraDB entity grounding (project, squad, year, release, type, status, metric)
  -> semantic follow-up/context resolution
  -> DeepSeek intent planner
  -> conversation response, or approved DoraDB query plan
  -> deterministic query/filter/limit controls
  -> parameterized read-only PostgreSQL execution
  -> result validation and one controlled repair
  -> deterministic comparison, trend, anomaly, chart, and table skills
  -> DeepSeek evidence synthesis
  -> answer consistency validation
  -> privacy-safe audit metadata
```

DeepSeek is configured through its OpenAI-compatible chat-completions API.

## Required configuration

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_MODEL=deepseek-v4-flash

DORADB_HOST=127.0.0.1
DORADB_PORT=5432
DORADB_NAME=doradb
DORADB_USER=your_readonly_username
DORADB_PASSWORD=your_readonly_password
DORADB_PROJECT_KEY=DCPM
```

The DeepSeek key and DoraDB password belong only in `.env`, which is ignored
by Git. The model never receives database credentials or executable SQL.

## Conversation behavior

- Greetings, conceptual questions, software-delivery guidance, and normal
  in-scope questions are answered generatively by DeepSeek.
- Dataset questions execute the real DoraDB tools first.
- Any current governed dimension value is recognized dynamically; squad,
  release, issue-type, and status names are not hard-coded in the router.
- Short follow-ups can refer to terms and conclusions from the preceding answer.
- A response never claims to be based on DoraDB unless a query ran in that turn.
- Charts and supporting tables are returned only when requested or materially
  useful for a long listing.
- Database writes, arbitrary SQL, and credential disclosure remain prohibited.
- The chat does not provide fixed example-question templates.

## Approved DoraDB query tools

- `list_dimension_values`
- `dora_metrics_by_year`
- `dora_metrics_by_squad`
- `dora_metrics_release_detail`
- `feature_vs_release_frequency`
- `feature_vs_user_story`
- `story_to_feature_ratio`

`list_dimension_values` provides governed, current discovery for projects,
squads, release years, releases, issue types, statuses, and supported metrics.
The runtime business meanings for those dimensions live in
`backend/context/data_dictionary.yaml`; row values are retrieved from DoraDB
rather than embedded in prompts or documentation.

DeepSeek is the primary planner and answer synthesizer for both discovery and
analysis. Deterministic routing is an outage/invalid-plan fallback, while the
non-generative control layer continues to enforce read-only allowlists, project
scope, filters, and row limits.

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
- `POST /api/reset-session`
- `POST /api/tts`
- `GET /api/health`
- `GET /api/projects`
- `GET /api/metrics`
- `GET /api/query-catalogue`
- `GET /api/audit/recent`

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
Set-Location frontend
npm run build
```
