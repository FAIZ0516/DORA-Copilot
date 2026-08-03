# DORA Intelligence — Google AI Studio or Ollama + real DoraDB

A FastAPI and React conversational AI application for the real local PostgreSQL
DoraDB database. Google Gemini or a local Ollama model provides generative
planning and natural-language responses. There is no synthetic Jira project mode.

## Runtime architecture

```text
User question
  -> structured session memory
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

Google Gemini is configured through the official Google GenAI SDK and a Google
AI Studio API key. Ollama uses its local HTTP API. Both providers remain behind
the same deterministic query allowlist and receive no database credentials or
executable SQL.

## Required configuration

```env
LLM_PROVIDER=google-ai-studio
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-3.6-flash

DORADB_HOST=127.0.0.1
DORADB_PORT=5432
DORADB_NAME=doradb
DORADB_USER=your_readonly_username
DORADB_PASSWORD=your_readonly_password
DORADB_PROJECT_KEY=DCPM
```

To use local Ollama instead of Gemini:

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

The Gemini key and DoraDB password belong only in `.env`, which is ignored by
Git. The configured model never receives database credentials or executable
SQL. Dataset answers are generated only after the backend executes an approved,
parameterized read-only query and validates its results.

## Conversation behavior

- Greetings, conceptual questions, software-delivery guidance, and normal
  in-scope questions are answered by the configured provider.
- Dataset questions execute the real DoraDB tools first.
- A response never claims to be based on DoraDB unless a query ran in that turn.
- Database writes, arbitrary SQL, and credential disclosure remain prohibited.
- The chat does not provide fixed example-question templates.

## Approved DoraDB query tools

- `dora_metrics_by_year`
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
