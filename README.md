# AutoML MCP Platform — Phase 2

An MCP-based AutoML copilot with **streaming responses**, **persistent
conversation history**, and an **enterprise-grade ML engine** (XGBoost,
LightGBM, Optuna tuning, SHAP explanations). Upload a CSV, chat in plain
English, and watch the LLM dynamically orchestrate local Python tools with
live progress updates.

┌────────────────────┐   SSE stream  ┌──────────────────────┐   stdio MCP    ┌──────────────────┐
│  Next.js frontend  │ ◀──────────── │  FastAPI backend     │ ─────────────▶ │  MCP server      │
│  (chat + history)  │ ────────────▶ │  Groq orchestrator   │ ◀───────────── │  ydata-profiling │
└────────────────────┘               │  SQLite persistence  │  ctx.progress  │  XGB / LGBM / RF │
│  Notification bridge │   ctx.info     │  Optuna + SHAP   │
└──────────────────────┘                └──────────────────┘

## What's new in Phase 2

| Upgrade | What it does |
|---|---|
| **SSE streaming `/api/chat`** | Tokens, tool starts, live progress, and tool results stream as `data: {...}\n\n` events. Tool badges appear in the UI within ~200 ms of the LLM emitting a tool call. |
| **SQLite + SQLAlchemy persistence** | Every conversation and message is saved to `automl_local.db`. A sidebar lets you jump back to any prior chat and continue where you left off. |
| **Enterprise AutoML engine** | `run_data_profiling` (ydata-profiling HTML report), `run_model_bake_off` (parallel CV across RandomForest, XGBoost, LightGBM, and a linear baseline; optional Optuna tuning), and `generate_model_explanations` (SHAP summary plot). |
| **MCP Context progress hooks** | Tools call `ctx.report_progress(...)` and `ctx.info(...)`. The FastAPI client subscribes to these notifications and pipes them straight into the open SSE stream as `tool_progress` events. |

## Tech stack

- **Frontend** — Next.js 15 (App Router), Tailwind, Lucide, react-markdown,
  manual `ReadableStream` + `TextDecoder` SSE parser
- **Backend** — FastAPI (`StreamingResponse`), Pydantic, uvicorn,
  SQLAlchemy 2.x, SQLite
- **LLM** — Groq API (`llama-3.3-70b-versatile`) with `stream=True`
  tool-calling
- **MCP** — `fastmcp` 3.x (server + client over `PythonStdioTransport`,
  `Context` for progress/log notifications)
- **ML / EDA** — pandas, scikit-learn, **ydata-profiling**, **xgboost**,
  **lightgbm**, **optuna**, **shap**, matplotlib, seaborn, joblib

## Project structure

automl-mcp-platform/
├── backend/
│   ├── main.py                     FastAPI app — SSE chat, conversations, uploads, static mounts
│   ├── database.py                 SQLAlchemy engine + Conversation / Message models
│   ├── mcp_server.py               FastMCP server (Context-aware async tools)
│   ├── core/
│   │   ├── config.py               Pydantic settings + reports/plots/models paths
│   │   ├── logger.py               stderr-only logger (stdio-safe)
│   │   ├── orchestrator.py         Groq ↔ MCP streaming generator (SSE event yields)
│   │   └── paths.py                Safe path resolver
│   ├── tools/
│   │   ├── data_analysis.py        head, schema, dataset info, problem-type detection
│   │   ├── data_profiling.py       ydata-profiling → HTML report + summary dict
│   │   ├── model_bakeoff.py        Parallel CV bake-off + optional Optuna study
│   │   ├── explainability.py       SHAP summary plot for the champion model
│   │   ├── visualization.py        7 chart types saved as PNG
│   │   └── code_generator.py       Downloadable .py training script
│   ├── schemas/
│   │   ├── chat.py                 Request/response models
│   │   └── conversation.py         Conversation + message DTOs
│   ├── uploads/                    User CSVs (gitignored)
│   ├── outputs/
│   │   ├── reports/                ydata-profiling HTML
│   │   ├── plots/                  SHAP / matplotlib PNGs
│   │   └── models/                 Champion .joblib + X_train sample .parquet
│   ├── automl_local.db             SQLite DB (created on first run, gitignored)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   └── globals.css
├── components/
│   ├── ChatInterface.tsx          Top-level layout: conversation sidebar + dataset sidebar + thread
│   ├── ChatComposer.tsx
│   ├── ConversationSidebar.tsx    Past conversations list with one-click load
│   ├── DatasetSidebar.tsx
│   ├── FileUploader.tsx
│   ├── MessageBubble.tsx          Renders streaming markdown + inline tool progress
│   ├── ToolCallCard.tsx           Expandable card with args, result, image / report / file artifacts
│   ├── ToolProgressBanner.tsx     Live "Calling X… 60%" badge
│   └── EmptyState.tsx
├── hooks/
│   └── useStreamingChat.ts        SSE consumer hook (token / tool_start / tool_progress / tool_end / done)
├── lib/
│   ├── api.ts                     REST helpers + static URL builders
│   ├── streamingClient.ts         Manual ReadableStream + TextDecoder line-buffer parser
│   └── types.ts                   ChatMessage, StreamEvent union, ToolCallRecord, etc.
├── package.json
├── tailwind.config.ts
├── tsconfig.json
└── next.config.mjs
## MCP tools exposed

| Tool                            | Purpose                                                                                  |
|---------------------------------|------------------------------------------------------------------------------------------|
| `list_uploaded_files`           | List CSVs in the upload dir                                                              |
| `analyze_csv_head`              | First N rows + dtypes + shape                                                            |
| `get_dataset_info`              | Shape, dtypes, missing counts, numeric/categorical groupings                             |
| `detect_problem_type`           | Classification vs regression heuristic                                                   |
| `run_data_profiling`            | Full ydata-profiling HTML report + summary dict (reports progress via `ctx`)             |
| `create_visualization`          | 7 chart types saved as PNG                                                               |
| `run_model_bake_off`            | Parallel CV across RF / XGB / LGBM / linear baseline; optional Optuna tuning             |
| `generate_model_explanations`   | SHAP summary plot for the champion model; returns `/static/plots/...png` URL             |
| `download_main_code_file`       | Standalone runnable `.py` training script                                                |

## SSE event protocol

The `/api/chat` endpoint returns a `text/event-stream` of JSON-encoded events.
Each frame is `data: {...}\n\n`. Event types:

```ts
{ type: "meta",          conversation_id: string, title: string }
{ type: "token",         content: string }
{ type: "tool_start",    name: string, arguments: object }
{ type: "tool_progress", message: string, percentage: number }      // -1 = log message, no percentage
{ type: "tool_end",      name: string, result: string, error: string | null, duration_ms: number }
{ type: "done",          answer: string, tool_calls: ToolCallRecord[] }
{ type: "error",         message: string }
```

The frontend hook `useStreamingChat` reads these via a manual
`ReadableStream` reader with line-by-line buffering — no `EventSource`,
which would not allow POST bodies.

## Setup — Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # then edit .env and paste your GROQ_API_KEY
```

Get a free Groq key at <https://console.groq.com>. The default model
`llama-3.3-70b-versatile` is supported on the free tier and handles
streaming tool-calling well.

Run the backend:

```bash
uvicorn main:app --reload --port 8000
```

On startup the app creates `automl_local.db` (SQLite) in the backend
directory. Static asset directories (`outputs/reports/`, `outputs/plots/`,
`outputs/models/`) are created automatically. Health check:

```bash
curl http://localhost:8000/api/health
```

## Setup — Frontend

```bash
cd frontend
cp .env.local.example .env.local    # already points to http://localhost:8000
npm install
npm run dev
```

Open <http://localhost:3000>.

## Using it

1. **Upload** a CSV in the dataset sidebar — it's saved to
   `backend/uploads/` and marked as the active file.
2. **Chat** with the data. Try:
   - *"Run a full data profile on my dataset."* → streams progress while
     ydata-profiling builds the HTML report; the LLM then links to it.
   - *"Train a model — the target is `species`. Spend 1 minute tuning."*
     → kicks off the parallel bake-off with `tune_budget_mins=1`; you'll
     see "Training in progress… (4s)" badges update in place.
   - *"Now explain the champion model."* → SHAP summary plot appears
     inline in the chat as a rendered Markdown image.
3. **Resume** any past chat from the left sidebar — the full thread,
   tool-call cards, and downloadable artifacts all rehydrate.

## API reference

| Method | Path                                            | Purpose                          |
|--------|-------------------------------------------------|----------------------------------|
| GET    | `/api/health`                                   | Service status                   |
| GET    | `/api/datasets`                                 | List uploaded CSVs               |
| POST   | `/api/upload`                                   | Upload a CSV / TSV               |
| POST   | `/api/chat`                                     | **SSE stream** (see protocol)    |
| GET    | `/api/conversations`                            | List past conversations          |
| GET    | `/api/conversations/{id}/messages`              | Fetch full conversation thread   |
| DELETE | `/api/conversations/{id}`                       | Remove a conversation            |
| GET    | `/api/download/{filename}`                      | Download any artifact            |
| —      | `/static/outputs/{file}`                        | Generic output static mount      |
| —      | `/static/reports/{file}`                        | ydata-profiling HTML reports     |
| —      | `/static/plots/{file}`                          | SHAP and other PNG plots         |
| —      | `/static/models/{file}`                         | Champion model artifacts         |

## Notes

- Everything runs locally except the Groq LLM call.
- `automl_local.db` lives next to `main.py`. Delete the file to wipe all
  conversation history.
- The active dataset is sent with every chat request; the system prompt
  instructs the LLM to use it as `file_path` unless the user names a
  different one.
- File-path resolution is locked to the upload directory — the resolver
  rejects any path that escapes it.
- MCP progress notifications are bridged to SSE via an `asyncio.Queue`
  drained between tool invocations, so a single tool call can emit
  many `tool_progress` events to the browser before its `tool_end`.
- Output files are served from `/static/{outputs,reports,plots,models}/`
  and downloadable via `/api/download/{filename}` (which searches all four
  directories).