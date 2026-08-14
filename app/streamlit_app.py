"""Streamlit UI for the AutoML MCP platform.

Thin — this file is a demo/development shell over the orchestrator + MCP pool.
All business logic lives in `core/`, `mcp_servers/`, and `orchestrator/`.

Run with:
    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import asyncio
import atexit
import queue as _queue
import sys
import threading
from pathlib import Path

# Ensure repo root is importable when Streamlit is launched from anywhere
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import streamlit as st

from core.config import settings
from core.workspace import (
    list_artifacts,
    list_datasets,
    save_uploaded_dataset,
)
from orchestrator import MCPClientPool, register_default_servers, stream_chat

st.set_page_config(
    page_title="AutoML MCP Platform",
    page_icon="🧪",
    layout="wide",
)


# ── Persistent MCP pool (one background event loop, kept alive) ─────
class PoolRunner:
    """Owns a single asyncio loop in a background thread so we can run
    async MCP calls from Streamlit's synchronous script."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.pool = MCPClientPool()
        register_default_servers(self.pool)
        asyncio.run_coroutine_threadsafe(self.pool.start(), self.loop).result()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def stream_events(
        self,
        query: str,
        active_file: str | None,
        history: list[dict[str, str]],
    ) -> _queue.Queue:
        """Kick off stream_chat on the background loop; return a thread-safe
        queue that yields event dicts. Sentinel `None` marks the end."""
        q: _queue.Queue = _queue.Queue()

        async def _drive() -> None:
            try:
                async for evt in stream_chat(
                    query=query,
                    active_file=active_file,
                    history=history,
                    pool=self.pool,
                ):
                    q.put(evt)
            except Exception as exc:
                q.put({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
            finally:
                q.put(None)

        asyncio.run_coroutine_threadsafe(_drive(), self.loop)
        return q

    def shutdown(self) -> None:
        try:
            asyncio.run_coroutine_threadsafe(
                self.pool.shutdown(), self.loop
            ).result(timeout=5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)


@st.cache_resource(show_spinner="Starting MCP pool…")
def get_runner() -> PoolRunner:
    runner = PoolRunner()
    atexit.register(runner.shutdown)
    return runner


runner = get_runner()
pool = runner.pool


# ── Session state defaults ──────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []          # list[dict{role,content,tool_calls?}]
if "active_file" not in st.session_state:
    st.session_state.active_file = None


# ── Sidebar: datasets, services ─────────────────────────────────────
with st.sidebar:
    st.markdown("### AutoML MCP")
    st.caption(f"Model: `{settings.GROQ_MODEL}`")
    if not settings.GROQ_API_KEY:
        st.error("GROQ_API_KEY is not set. Add it to `.env`.")

    st.divider()
    st.markdown("#### Upload dataset")
    uploaded = st.file_uploader(
        "CSV / TSV / Parquet",
        type=["csv", "tsv", "parquet"],
        accept_multiple_files=False,
    )
    if uploaded is not None:
        data = uploaded.getvalue()
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        if len(data) > max_bytes:
            st.error(f"File exceeds {settings.MAX_UPLOAD_MB} MB limit.")
        else:
            record = save_uploaded_dataset(uploaded.name, data)
            st.session_state.active_file = record.filename
            st.success(f"Saved `{record.filename}` ({record.size_bytes/1024:.1f} KB)")

    st.divider()
    st.markdown("#### Datasets")
    dataset_rows = list_datasets()
    if dataset_rows:
        filenames = [r["filename"] for r in dataset_rows]
        active_default = 0
        if st.session_state.active_file in filenames:
            active_default = filenames.index(st.session_state.active_file)
        st.session_state.active_file = st.radio(
            "Active dataset",
            options=filenames,
            index=active_default,
        )
    else:
        st.caption("No datasets yet — upload one above.")

    st.divider()
    st.markdown("#### MCP Services")
    snapshot = pool.snapshot()
    for svc in snapshot["services"]:
        icon = "🟢" if svc["status"] == "online" else "🔴"
        st.write(f"{icon} **{svc['name']}** — {len(svc['tools'])} tools")
    st.caption(
        f"Unified catalog: {snapshot['tool_count']} tools · "
        f"{snapshot['prompt_count']} prompts"
    )

    if st.button("Clear conversation", width="stretch"):
        st.session_state.messages = []
        st.rerun()


# ── Main area ───────────────────────────────────────────────────────
tab_chat, tab_artifacts, tab_tools = st.tabs(["💬 Chat", "📦 Artifacts", "🛠️ Tools"])


def _render_tool_call(tc: dict) -> None:
    label = f"🔧 {tc['name']} · {tc.get('service', '?')} · {tc.get('duration_ms', 0)} ms"
    with st.expander(label, expanded=False):
        st.markdown("**Arguments**")
        st.json(tc.get("arguments") or {})
        if tc.get("error"):
            st.error(tc["error"])
        else:
            st.markdown("**Result**")
            st.json(tc.get("result"))


# ── Chat tab ────────────────────────────────────────────────────────
with tab_chat:
    st.subheader("AutoML Copilot")
    st.caption(
        f"Active dataset: `{st.session_state.active_file or 'none — upload one from the sidebar'}`"
    )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["content"]:
                st.markdown(msg["content"])
            for tc in msg.get("tool_calls") or []:
                _render_tool_call(tc)

    prompt = st.chat_input(
        "Ask about your data, train a model, or generate a report…"
    )

    if prompt:
        if not settings.GROQ_API_KEY:
            st.error("Set GROQ_API_KEY in `.env` before chatting.")
            st.stop()

        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[:-1]
            if m["content"]
        ]

        with st.chat_message("assistant"):
            answer_slot = st.empty()
            tool_area = st.container()

            answer_buf: list[str] = []
            tool_records: list[dict] = []
            active_tools: dict[str, dict] = {}

            evt_queue = runner.stream_events(
                query=prompt,
                active_file=st.session_state.active_file,
                history=history,
            )

            while True:
                evt = evt_queue.get()
                if evt is None:
                    break
                etype = evt.get("type")

                if etype == "token":
                    answer_buf.append(evt["content"])
                    answer_slot.markdown("".join(answer_buf) + "▌")

                elif etype == "tool_start":
                    with tool_area:
                        placeholder = st.info(
                            f"🔧 **{evt['label']}** — `{evt['name']}` on `{evt['service']}`"
                        )
                    active_tools[evt["name"]] = {
                        "label": evt["label"],
                        "placeholder": placeholder,
                    }

                elif etype == "tool_progress":
                    for state in active_tools.values():
                        state["placeholder"].info(
                            f"🔧 **{state['label']}** — {evt['message']} ({evt['percentage']:.0f}%)"
                        )

                elif etype == "tool_end":
                    tool_records.append({
                        "name": evt["name"],
                        "service": evt["service"],
                        "arguments": evt.get("arguments", {}),
                        "result": evt["result"],
                        "error": evt.get("error"),
                        "duration_ms": evt["duration_ms"],
                    })
                    state = active_tools.pop(evt["name"], None)
                    if state:
                        if evt.get("error"):
                            state["placeholder"].error(
                                f"❌ **{state['label']}** — {evt['error']}"
                            )
                        else:
                            state["placeholder"].success(
                                f"✅ **{state['label']}** — {evt['duration_ms']} ms"
                            )

                elif etype == "done":
                    if evt.get("answer"):
                        answer_buf = [evt["answer"]]

                elif etype == "error":
                    st.error(evt["message"])

            final_answer = "".join(answer_buf)
            answer_slot.markdown(final_answer)

            for tc in tool_records:
                _render_tool_call(tc)

            st.session_state.messages.append({
                "role": "assistant",
                "content": final_answer,
                "tool_calls": tool_records,
            })


# ── Artifacts tab ───────────────────────────────────────────────────
with tab_artifacts:
    st.subheader("Generated artifacts")
    records = list_artifacts()
    if not records:
        st.caption("No artifacts yet — run an EDA or train a model to generate some.")
    else:
        kinds = sorted({r["kind"] for r in records})
        chosen = st.multiselect("Filter by kind", kinds, default=kinds)
        for r in records:
            if r["kind"] not in chosen:
                continue
            with st.expander(
                f"[{r['kind']}] {r['filename']}  ·  {r['size_bytes']/1024:.1f} KB",
                expanded=False,
            ):
                st.caption(f"ID: `{r['id']}` · path: `{r['path']}`")
                path = Path(r["path"])
                mime = r.get("mime_type", "")
                if mime.startswith("image/") and path.exists():
                    st.image(str(path), width="stretch")
                elif r["kind"] == "training_notebook" and path.exists():
                    st.code(
                        path.read_text(encoding="utf-8")[:4000] + "\n…",
                        language="json",
                    )
                elif r["kind"] == "xtrain_sample" and path.exists():
                    st.dataframe(pd.read_parquet(path).head(20))
                if r.get("metadata"):
                    st.markdown("**Metadata**")
                    st.json(r["metadata"])
                if path.exists():
                    st.download_button(
                        f"Download {r['filename']}",
                        data=path.read_bytes(),
                        file_name=r["filename"],
                        mime=mime or "application/octet-stream",
                        key=f"dl_{r['id']}",
                    )


# ── Tools tab ───────────────────────────────────────────────────────
with tab_tools:
    st.subheader("Available MCP tools")
    for schema in pool.tool_schemas:
        fn = schema["function"]
        with st.expander(f"`{fn['name']}` — {fn['description'][:80]}"):
            st.json(fn)
