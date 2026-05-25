# AutoML MCP Platform — Phase 1

An MCP-based AutoML copilot for students and researchers. Upload a CSV, chat
in plain English, and the LLM dynamically calls local Python tools to read the
data, run EDA, plot charts, and train baseline models.

```
┌────────────────────┐     HTTP      ┌──────────────────────┐    stdio MCP   ┌──────────────────┐
│  Next.js frontend  │  ───────────▶ │  FastAPI backend     │  ────────────▶ │  MCP server      │
│  (chat + upload)   │ ◀───────────  │  (LLM orchestrator)  │  ◀──────────── │  (tools)         │
└────────────────────┘               │  Groq tool-calling   │                │  pandas, sklearn │
                                     └──────────────────────┘                └──────────────────┘
```

## Tech stack

- **Frontend** — Next.js 15 (App Router), Tailwind, Lucide, react-markdown
- **Backend** — FastAPI, Pydantic, uvicorn
- **LLM** — Groq API (`llama-3.3-70b-versatile`), OpenAI-compatible tool calling
- **MCP** — `fastmcp` (server + client over `PythonStdioTransport`)
- **ML/EDA** — pandas, scikit-learn, matplotlib, seaborn, joblib

## Project structure

```
automl-mcp-platform/
├── backend/
│   ├── main.py                 FastAPI app (MCP client + Groq orchestrator)
│   ├── mcp_server.py           FastMCP server exposing all tools
│   ├── core/
│   │   ├── config.py           Pydantic settings
│   │   ├── logger.py           stderr-only logger (stdio-safe)
│   │   ├── orchestrator.py     Groq ↔ MCP tool-calling loop
│   │   └── paths.py            Safe path resolver
│   ├── tools/
│   │   ├── data_analysis.py    head, schema, dataset info, problem-type detection
│   │   ├── eda.py              full EDA report (markdown)
│   │   ├── visualization.py    7 chart types saved as PNG
│   │   ├── ml_training.py      Random Forest baseline (classif/regression)
│   │   └── code_generator.py   downloadable .py training script
│   ├── schemas/chat.py         request/response models
│   ├── uploads/                user CSVs (gitignored)
│   ├── outputs/                generated PNGs, reports, models, scripts
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx
    │   └── globals.css
    ├── components/
    │   ├── ChatInterface.tsx
    │   ├── ChatComposer.tsx
    │   ├── DatasetSidebar.tsx
    │   ├── FileUploader.tsx
    │   ├── MessageBubble.tsx
    │   ├── ToolCallCard.tsx
    │   └── EmptyState.tsx
    ├── lib/
    │   ├── api.ts
    │   └── types.ts
    ├── package.json
    ├── tailwind.config.ts
    ├── tsconfig.json
    └── next.config.mjs
```

## MCP tools exposed

| Tool                        | Purpose                                                              |
|-----------------------------|----------------------------------------------------------------------|
| `list_uploaded_files`       | List CSVs in the upload dir                                          |
| `analyze_csv_head`          | First N rows + dtypes + shape                                        |
| `get_dataset_info`          | Shape, dtypes, missing counts, numeric/categorical groups            |
| `detect_problem_type`       | Classification vs regression heuristic                               |
| `generate_eda_report`       | Full EDA summary + markdown file                                     |
| `create_visualization`      | 7 chart types saved as PNG                                           |
| `train_baseline_model`      | Random Forest with auto-preprocessing, returns metrics + importances |
| `download_main_code_file`   | Generates a standalone runnable `.py` training script                |

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
tool-calling well.

Run the backend:

```bash
uvicorn main:app --reload --port 8000
```

The FastAPI app boots the MCP server on demand (one stdio subprocess per
chat request via `PythonStdioTransport`). Health check:

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

1. Drop a CSV into the sidebar — it’s saved to `backend/uploads/` and marked
   as the **active file**.
2. Ask things like:
   - "Show me the first 5 rows and the column types."
   - "Give me an EDA report."
   - "Plot a correlation heatmap."
   - "Train a baseline Random Forest. The target column is `species`."
   - "Generate a Python script I can run locally for that model."
3. Expand any tool-call card in the assistant’s response to inspect the
   exact arguments, raw result, generated PNGs, and download links for
   reports / models / scripts.

## Notes

- Everything runs locally. Only the LLM step calls Groq's API.
- The active file is sent with every chat request — the system prompt
  instructs the LLM to use it as `file_path` unless the user names a
  different one.
- Output files (PNGs, `.md`, `.joblib`, `.py`) are served from
  `/static/outputs/<filename>` and downloadable via `/api/download/<filename>`.
- File-path resolution is locked to the upload directory — the resolver
  rejects any path that escapes it.
