# AutoLab

> **Conversational AutoML on MCP.** Chat with your data. Get real notebooks, models, and reports.

AutoLab is a **development- and research-oriented** AutoML platform built around the
[Model Context Protocol](https://modelcontextprotocol.io). Five in-process
FastMCP services expose tools for data ingestion, EDA, modeling,
explainability, and export. A Groq-powered orchestrator drives them through a
natural-language tool-calling loop. A thin **Streamlit** UI is the front door.

No web frontend. No authentication. No cloud storage. Everything runs
locally against the filesystem — ideal for exploration, teaching, and
research prototypes.

**Stack:** Python 3.11 · Streamlit · FastMCP 3 · Groq (Llama 3.3 70B) · scikit-learn · XGBoost · LightGBM · Optuna · SHAP · pandera · ReportLab

---

## Why AutoLab

Most AutoML tools force a tradeoff: either a low-code GUI that hides the
engineering, or a notebook-first SDK that reproduces nothing. AutoLab sits
between them — the conversation produces *real, runnable, downloadable
artifacts* on every step. Every chart is a PNG. Every model is a pickled
scikit-learn pipeline. Every analysis is a Jupyter notebook you can re-execute
locally.

- **Distributed by design.** Each pipeline stage is an independent FastMCP
  server loaded in-process. Trivial to swap, extend, or replace one stage.
- **Conversational, not procedural.** Describe outcomes; the orchestrator
  picks tools, routes calls, and surfaces a clean activity timeline.
- **Real artifacts, every time.** Notebooks generated with `nbformat`,
  reports with `ReportLab`, models pickled with `joblib`, all indexed on disk.
- **Fully local.** No cloud, no auth, no telemetry. Your data never leaves
  your machine (except for LLM tokens sent to Groq).

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  app/streamlit_app.py  (thin UI: uploads, chat, artifacts) │
└─────────────────────────┬──────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────┐
│  orchestrator/                                             │
│    ├─ pool.py   MCPClientPool (in-process transport)       │
│    └─ loop.py   Groq tool-calling loop, yields event dicts │
└─────────────────────────┬──────────────────────────────────┘
                          │
        ┌─────────────┬───┴───┬──────────────┬─────────────┐
        ▼             ▼       ▼              ▼             ▼
   mcp_servers/  mcp_servers/ mcp_servers/  mcp_servers/  mcp_servers/
     data.py       eda.py     modeling.py    explain.py    export.py

                          │
┌─────────────────────────▼──────────────────────────────────┐
│  core/                                                     │
│    ├─ config.py     pydantic settings (env-driven)         │
│    ├─ logger.py     stderr logger                          │
│    └─ workspace.py  local dataset + artifact registries    │
└─────────────────────────┬──────────────────────────────────┘
                          ▼
                     data/  (uploads, artifacts, tmp)
```

## Repository layout

```
autolab/
├── app/
│   ├── streamlit_app.py         # Streamlit entrypoint
│   └── components/              # future render helpers
├── core/
│   ├── config.py                # Settings (env-driven)
│   ├── logger.py
│   └── workspace.py             # local dataset + artifact registries
├── mcp_servers/
│   ├── data.py                  # ingest, list, pandera validation
│   ├── eda.py                   # profile, correlations, distributions
│   ├── modeling.py              # parallel bake-off + Optuna sweep
│   ├── explain.py               # SHAP + feature importance
│   └── export.py                # Jupyter notebook + PDF report
├── orchestrator/
│   ├── pool.py                  # MCPClientPool (in-process transport)
│   └── loop.py                  # Groq tool-calling loop (async iterator)
├── data/
│   ├── uploads/                 # your CSV/TSV/Parquet files
│   ├── artifacts/               # generated plots, models, notebooks, reports
│   └── tmp/                     # scratch space
├── .env.example
├── requirements.txt
└── README.md
```

## MCP tool catalog

| Service        | Tools                                                                                   |
|----------------|-----------------------------------------------------------------------------------------|
| `mcp-data`     | `list_uploaded_files`, `ingest_dataset`, `validate_schema_with_pandera`                 |
| `mcp-eda`      | `run_full_eda`, `render_correlation_matrix`                                             |
| `mcp-modeling` | `run_parallel_bake_off`, `trigger_hyperparameter_sweep`                                 |
| `mcp-explain`  | `calculate_shap_values`, `generate_feature_importance_plot`                             |
| `mcp-export`   | `generate_jupyter_notebook`, `compile_pdf_report`                                       |

All 5 services load in-process at startup — no HTTP, no ports, no sub-processes.

## Setup

```bash
# 1. Create + activate a virtual env
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env to add your GROQ_API_KEY
```

## Run

```bash
streamlit run app/streamlit_app.py
```

Open http://localhost:8501 in your browser.

Workflow:

1. Upload a CSV / TSV / Parquet from the sidebar.
2. Ask the copilot to explore, train, or explain your data.
3. Generated plots, models, notebooks, and PDFs land under
   `data/artifacts/` and are previewable in the **Artifacts** tab.

## Configuration

Every setting is read from `.env` (see `.env.example`):

| Variable              | Default                     | Purpose                                    |
|-----------------------|-----------------------------|--------------------------------------------|
| `GROQ_API_KEY`        | *(required)*                | Groq API key for the chat/tool-call loop.  |
| `GROQ_MODEL`          | `llama-3.3-70b-versatile`   | Groq model name.                           |
| `MAX_TOOL_ITERATIONS` | `8`                         | Max tool-call loops per user message.      |
| `MAX_UPLOAD_MB`       | `200`                       | Upload size cap enforced in the UI.        |
| `DATA_DIR`            | `<repo>/data`               | Root for `uploads/`, `artifacts/`, `tmp/`. |

## Using AutoLab programmatically

The orchestrator and MCP pool are usable from any Python code, not just
Streamlit:

```python
import asyncio
from orchestrator import MCPClientPool, register_default_servers, stream_chat

async def main():
    pool = MCPClientPool()
    register_default_servers(pool)
    await pool.start()

    async for evt in stream_chat(
        query="Run EDA on iris.csv",
        active_file="iris.csv",
        history=[],
        pool=pool,
    ):
        print(evt)

    await pool.shutdown()

asyncio.run(main())
```

You can also call MCP tools directly:

```python
result = await pool.call_tool("ingest_dataset", {"file_path": "iris.csv"})
```

## Example prompts

Once you've uploaded a dataset, try:

- *"Run a full EDA and summarise what stands out."*
- *"Train a model to predict `<target>` and show me the leaderboard."*
- *"What features matter most? Compute SHAP values."*
- *"Generate a Jupyter notebook that reproduces the winning pipeline."*
- *"Compile a PDF report of the results."*

## License

Apache 2.0 — see `LICENSE`.
