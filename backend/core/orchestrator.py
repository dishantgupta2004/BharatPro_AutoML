"""SSE-streaming Groq <-> multi-MCP orchestration loop.

Now propagates `user_id` to every tool call via FastMCP's elicit/context system —
we pipe it through the arguments dict under the `_user_id` key, which each MCP
tool extracts before forwarding to storage helpers. This is the cleanest way to
pass per-request context through the MCP tool call boundary without redesigning
the protocol.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncGenerator

from groq import Groq

from core.config import settings
from core.logger import get_logger
from core.mcp_pool import MCPClientPool

log = get_logger("orchestrator")

SYSTEM_PROMPT = """You are **Unisole Empower Copilot**, an AI assistant for students, \
researchers, and data engineers exploring datasets and training ML models.

You are connected to a distributed network of FIVE specialized MCP microservices:

  • mcp-data      — Ingestion, schema, pandera validation
  • mcp-eda       — Profiling reports, correlation matrices, charts
  • mcp-modeling  — Parallel AutoML bake-off, Optuna hyperparameter sweeps
  • mcp-explain   — SHAP values, feature importance, explainability cards
  • mcp-export    — Jupyter notebooks, PDF reports

All tools from all 5 services are available to you in a unified catalog.

Rules:
1. If the user says "my data" / "the dataset" / "this file", use the active_file in \
context as the file_path. If none is set, call `list_uploaded_files` first.
2. Always ground factual claims in tool results.
3. When training a model, if the target column is unclear, ASK the user.
4. After `run_parallel_bake_off` succeeds, you may proactively call \
`calculate_shap_values` using the returned `model_id`.
5. When a tool returns `report_url`, `plot_url`, `markdown_embed`, or `download_url`, \
render it inline as Markdown.
6. Be concise — short paragraphs, light bullets.
"""


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def _extract_tool_result(result: Any) -> Any:
    if hasattr(result, "structured_content") and result.structured_content is not None:
        return result.structured_content
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "content") and result.content:
        chunks: list[str] = []
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


def _build_messages(
    query: str,
    history: list[dict[str, str]],
    active_file: str | None,
    pool_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    sys_lines = [SYSTEM_PROMPT]
    if active_file:
        sys_lines.append(
            f"\nThe user's active dataset filename is `{active_file}`. "
            "Use it as file_path unless they specify another."
        )
    else:
        sys_lines.append(
            "\nNo active dataset selected. If a tool needs file_path, "
            "ask or call list_uploaded_files first."
        )
    online = [s["name"] for s in pool_snapshot["services"] if s["status"] == "online"]
    offline = [s["name"] for s in pool_snapshot["services"] if s["status"] != "online"]
    sys_lines.append(f"\nMicroservices online: {', '.join(online) or 'none'}.")
    if offline:
        sys_lines.append(f"Microservices offline / degraded: {', '.join(offline)}.")

    msgs: list[dict[str, Any]] = [{"role": "system", "content": "\n".join(sys_lines)}]
    for m in history:
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": query})
    return msgs


async def stream_chat(
    query: str,
    active_file: str | None,
    history: list[dict[str, str]],
    pool: MCPClientPool,
    user_id: str,
    conversation_id: str | None = None,
    prompt_inject: str | None = None,
) -> AsyncGenerator[str, None]:
    """Run the Groq <-> multi-MCP loop, yielding SSE-formatted event strings."""
    if not settings.GROQ_API_KEY:
        yield _sse({"type": "error", "message": "GROQ_API_KEY is not set."})
        return

    groq_client = Groq(api_key=settings.GROQ_API_KEY)
    pool_snapshot = pool.snapshot()
    messages = _build_messages(query, history, active_file, pool_snapshot)
    if prompt_inject:
        messages.insert(1, {"role": "system", "content": prompt_inject})

    openai_tools = pool.tool_schemas

    progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def progress_handler(
        progress: float, total: float | None = None, message: str | None = None
    ) -> None:
        pct = (float(progress) / float(total) * 100.0) if total else float(progress)
        await progress_queue.put({
            "type": "tool_progress",
            "message": message or "Working…",
            "percentage": round(pct, 1),
        })

    full_answer: list[str] = []
    tool_calls_collected: list[dict[str, Any]] = []

    try:
        for step in range(settings.MAX_TOOL_ITERATIONS):
            stream = await asyncio.to_thread(
                groq_client.chat.completions.create,
                model=settings.GROQ_MODEL, messages=messages,
                tools=openai_tools if openai_tools else None,
                tool_choice="auto" if openai_tools else None,
                temperature=0.2, max_tokens=2048, stream=True,
            )

            assistant_text: list[str] = []
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
                        if idx not in started_tool_indices and slot["name"]:
                            started_tool_indices.add(idx)
                            try:
                                partial_args = json.loads(slot["arguments"] or "{}")
                            except json.JSONDecodeError:
                                partial_args = {}
                            owner = pool.service_for_tool(slot["name"]) or "unknown"
                            yield _sse({
                                "type": "tool_start",
                                "name": slot["name"],
                                "service": owner,
                                "arguments": partial_args,
                            })

            joined_text = "".join(assistant_text)
            if joined_text:
                full_answer.append(joined_text)

            if not pending_tool_calls:
                messages.append({"role": "assistant", "content": joined_text})
                break

            ordered = [pending_tool_calls[i] for i in sorted(pending_tool_calls.keys())]
            messages.append({
                "role": "assistant", "content": joined_text,
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"],
                                  "arguments": tc["arguments"] or "{}"}}
                    for tc in ordered
                ],
            })

            for tc in ordered:
                name = tc["name"]
                try:
                    args = json.loads(tc["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                # Inject the per-request user context for storage scoping
                args["_user_id"] = user_id
                if conversation_id:
                    args["_conversation_id"] = conversation_id

                owner = pool.service_for_tool(name) or "unknown"
                t0 = time.time()

                call_task = asyncio.create_task(
                    pool.call_tool(name, args, progress_handler=progress_handler)
                )

                while True:
                    try:
                        evt = await asyncio.wait_for(progress_queue.get(), timeout=0.05)
                        yield _sse(evt)
                    except asyncio.TimeoutError:
                        if call_task.done():
                            break
                while not progress_queue.empty():
                    yield _sse(progress_queue.get_nowait())

                error: str | None = None
                try:
                    mcp_result = await call_task
                    payload = _extract_tool_result(mcp_result)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    payload = {"error": error, "service": owner}
                    yield _sse({"type": "service_status",
                                "service": {"name": owner, "status": "error",
                                            "last_error": error}})

                duration_ms = int((time.time() - t0) * 1000)
                # Strip internal args from the result echoed back to the UI
                public_args = {k: v for k, v in args.items() if not k.startswith("_")}
                result_str = json.dumps(payload, default=str)

                yield _sse({
                    "type": "tool_end", "name": name, "service": owner,
                    "result": result_str, "error": error,
                    "duration_ms": duration_ms,
                })

                tool_calls_collected.append({
                    "name": name, "service": owner, "arguments": public_args,
                    "result": payload, "error": error, "duration_ms": duration_ms,
                })

                messages.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "name": name, "content": result_str,
                })

        else:
            full_answer.append(
                "\n\n_I hit the tool-iteration limit before producing a final answer._"
            )

        yield _sse({
            "type": "done",
            "answer": "".join(full_answer),
            "tool_calls": tool_calls_collected,
        })

    except Exception as exc:
        log.exception("stream_chat failed")
        yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})