"""SSE-streaming Groq <-> MCP orchestration loop.

Emits four event types as `data: {...}\\n\\n` SSE frames:
  - {"type": "token", "content": str}
  - {"type": "tool_start", "name": str, "arguments": dict}
  - {"type": "tool_progress", "message": str, "percentage": float}
  - {"type": "tool_end", "name": str, "result": str}
Plus housekeeping events: "meta" (conversation_id/title), "done", "error".
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from groq import Groq

from core.config import settings
from core.logger import get_logger

log = get_logger("orchestrator")

SYSTEM_PROMPT = """You are AutoML Copilot, an AI assistant for students and \
researchers exploring data and training machine-learning models.

You have a local MCP server with these tools:
  - list_uploaded_files
  - analyze_csv_head
  - get_dataset_info
  - detect_problem_type
  - run_data_profiling           (ydata-profiling, returns HTML report URL)
  - create_visualization
  - run_model_bake_off           (parallel RF / XGBoost / LightGBM / linear baseline; optional Optuna tuning)
  - generate_model_explanations  (SHAP summary; returns a /static/plots/*.png URL)
  - download_main_code_file

Rules:
1. If a user message says "my data", "the dataset", "this file", use the active_file from \
context as file_path. If no active file is provided and the user did not name one, call \
list_uploaded_files first.
2. Always ground factual claims about the data in a tool call. Never invent columns, rows, or metrics.
3. When training a model, if the target column is not specified, ASK the user. Do not guess.
4. After run_model_bake_off succeeds, you may proactively call generate_model_explanations \
using the returned model_artifact_path and x_train_sample_path.
5. When a tool returns `report_url`, `plot_url`, or `markdown_embed`, render it inline in your \
reply as Markdown (e.g. `![SHAP](/static/plots/...)` or `[Full profile report](/static/reports/...)`).
6. Be concise. Short paragraphs, light bullet use. Audience: students.
"""


def _mcp_tool_to_openai_schema(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None) or {}
    if not isinstance(schema, dict) or "type" not in schema:
        schema = {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": (tool.description or "").strip(),
            "parameters": schema,
        },
    }


def _extract_tool_result(result: Any) -> Any:
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "content") and result.content:
        chunks = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                chunks.append(text)
        joined = "\n".join(chunks)
        try:
            return json.loads(joined)
        except (json.JSONDecodeError, TypeError):
            return joined
    return str(result)


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def _build_messages(query: str, history: list[dict[str, str]], active_file: str | None) -> list[dict[str, Any]]:
    sys_lines = [SYSTEM_PROMPT]
    if active_file:
        sys_lines.append(
            f"\nThe user's active dataset filename is `{active_file}`. "
            "Use it as file_path unless they specify another."
        )
    else:
        sys_lines.append(
            "\nNo active dataset selected. If a tool needs file_path, ask or call "
            "list_uploaded_files first."
        )
    msgs: list[dict[str, Any]] = [{"role": "system", "content": "\n".join(sys_lines)}]
    for m in history:
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": query})
    return msgs


async def stream_chat(
    query: str,
    active_file: str | None,
    history: list[dict[str, str]],
    mcp_server_script: str,
) -> AsyncGenerator[str, None]:
    """Async generator yielding SSE-formatted event strings."""
    if not settings.GROQ_API_KEY:
        yield _sse({"type": "error", "message": "GROQ_API_KEY is not set."})
        return

    groq_client = Groq(api_key=settings.GROQ_API_KEY)
    transport = PythonStdioTransport(script_path=mcp_server_script)
    messages = _build_messages(query, history, active_file)

    # Queue bridging MCP progress + log notifications into the SSE stream
    progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def progress_handler(
        progress: float, total: float | None = None, message: str | None = None
    ) -> None:
        pct = (float(progress) / float(total) * 100.0) if total else float(progress)
        await progress_queue.put(
            {
                "type": "tool_progress",
                "message": message or "Working…",
                "percentage": round(pct, 1),
            }
        )

    async def log_handler(msg: Any) -> None:
        # fastmcp passes a LogMessage with .data / .level
        data = getattr(msg, "data", None) or getattr(msg, "message", None) or str(msg)
        await progress_queue.put(
            {"type": "tool_progress", "message": str(data), "percentage": -1}
        )

    full_answer: list[str] = []
    tool_calls_collected: list[dict[str, Any]] = []

    try:
        async with Client(
            transport,
            progress_handler=progress_handler,
            log_handler=log_handler,
        ) as mcp_client:
            tool_list = await mcp_client.list_tools()
            openai_tools = [_mcp_tool_to_openai_schema(t) for t in tool_list]
            log.info("Discovered %d MCP tools", len(openai_tools))

            for step in range(settings.MAX_TOOL_ITERATIONS):
                # ---- Groq streaming call ----
                stream = await asyncio.to_thread(
                    groq_client.chat.completions.create,
                    model=settings.GROQ_MODEL,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=2048,
                    stream=True,
                )

                assistant_text: list[str] = []
                # tool_calls accumulator: index -> {id, name, arguments}
                pending_tool_calls: dict[int, dict[str, Any]] = {}
                started_tool_indices: set[int] = set()

                sentinel = object()

                while True:
                    chunk = await asyncio.to_thread(next, stream, sentinel)
                    if chunk is sentinel:
                        break
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    if getattr(delta, "content", None):
                        assistant_text.append(delta.content)
                        yield _sse({"type": "token", "content": delta.content})

                    if getattr(delta, "tool_calls", None):
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            slot = pending_tool_calls.setdefault(
                                idx, {"id": None, "name": "", "arguments": ""}
                            )
                            if tc_delta.id:
                                slot["id"] = tc_delta.id
                            fn = getattr(tc_delta, "function", None)
                            if fn:
                                if getattr(fn, "name", None):
                                    slot["name"] = fn.name
                                if getattr(fn, "arguments", None):
                                    slot["arguments"] += fn.arguments

                            # Emit tool_start on first sighting of this index with a name
                            if idx not in started_tool_indices and slot["name"]:
                                started_tool_indices.add(idx)
                                # Best-effort parse of partial arguments
                                try:
                                    partial_args = json.loads(slot["arguments"] or "{}")
                                except json.JSONDecodeError:
                                    partial_args = {}
                                yield _sse(
                                    {
                                        "type": "tool_start",
                                        "name": slot["name"],
                                        "arguments": partial_args,
                                    }
                                )

                # ---- After Groq stream completes for this iteration ----
                joined_text = "".join(assistant_text)
                if joined_text:
                    full_answer.append(joined_text)

                if not pending_tool_calls:
                    # Final assistant message reached, exit loop
                    messages.append({"role": "assistant", "content": joined_text})
                    break

                # Build the assistant message (with tool_calls) for the next round
                ordered = [pending_tool_calls[i] for i in sorted(pending_tool_calls.keys())]
                messages.append(
                    {
                        "role": "assistant",
                        "content": joined_text,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": tc["arguments"] or "{}",
                                },
                            }
                            for tc in ordered
                        ],
                    }
                )

                # ---- Execute each tool, draining progress queue concurrently ----
                for tc in ordered:
                    name = tc["name"]
                    try:
                        args = json.loads(tc["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}

                    t0 = time.time()
                    call_task = asyncio.create_task(mcp_client.call_tool(name, args))

                    # Drain progress while the tool runs
                    while True:
                        try:
                            evt = await asyncio.wait_for(progress_queue.get(), timeout=0.05)
                            yield _sse(evt)
                        except asyncio.TimeoutError:
                            if call_task.done():
                                break

                    # Drain remaining queued progress
                    while not progress_queue.empty():
                        yield _sse(progress_queue.get_nowait())

                    error: str | None = None
                    try:
                        mcp_result = await call_task
                        payload = _extract_tool_result(mcp_result)
                    except Exception as exc:  # noqa: BLE001
                        error = f"{type(exc).__name__}: {exc}"
                        payload = {"error": error}

                    duration_ms = int((time.time() - t0) * 1000)
                    result_str = json.dumps(payload, default=str)

                    yield _sse(
                        {
                            "type": "tool_end",
                            "name": name,
                            "result": result_str,
                            "error": error,
                            "duration_ms": duration_ms,
                        }
                    )

                    tool_calls_collected.append(
                        {
                            "name": name,
                            "arguments": args,
                            "result": payload,
                            "error": error,
                            "duration_ms": duration_ms,
                        }
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": name,
                            "content": result_str,
                        }
                    )

            else:
                # Hit iteration cap
                full_answer.append(
                    "\n\n_I hit the tool-iteration limit before producing a final answer._"
                )

        # Surface the final consolidated answer + tool_calls payload to caller
        yield _sse(
            {
                "type": "done",
                "answer": "".join(full_answer),
                "tool_calls": tool_calls_collected,
            }
        )

    except Exception as exc:  # noqa: BLE001
        log.exception("stream_chat failed")
        yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})