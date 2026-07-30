# DORA Intelligence — Google AI Studio + real DoraDB

A FastAPI and React conversational AI application for the real local PostgreSQL
DoraDB database. Google Gemini provides generative planning and natural-language
responses. There is no synthetic Jira project mode and no local LLM runtime.

## Runtime architecture

```text
User question
  -> structured session memory
  -> Gemini intent planner
  -> conversation response, or approved DoraDB query plan
  -> deterministic query/filter/limit controls
  -> parameterized read-only PostgreSQL execution
  -> result validation and one controlled repair
  -> deterministic comparison, trend, anomaly, chart, and table skills
  -> Gemini evidence synthesis
  -> answer consistency validation
  -> privacy-safe audit metadata
```

Gemini is configured through the official Google GenAI SDK and a Google AI
Studio API key.

## Required configuration

```env
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_MODEL=gemini-3.6-flash

DORADB_HOST=127.0.0.1
DORADB_PORT=5432
DORADB_NAME=doradb
DORADB_USER=your_readonly_username
DORADB_PASSWORD=your_readonly_password
DORADB_PROJECT_KEY=DCPM
```

The Gemini key and DoraDB password belong only in `.env`, which is ignored
by Git. The model never receives database credentials or executable SQL.

## Conversation behavior

- Greetings, conceptual questions, software-delivery guidance, and normal
  in-scope questions are answered generatively by Gemini.
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
