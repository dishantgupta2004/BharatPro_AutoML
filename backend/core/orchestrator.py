from __future__ import annotations

import json
import time
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport
from groq import Groq

from core.config import settings
from core.logger import get_logger
from schemas.chat import ChatMessage, ChatResponse, ToolCallRecord

log = get_logger("orchestrator")


SYSTEM_PROMPT = """You are AutoML Copilot, an AI assistant for students and researchers \
who want to explore data and train baseline machine-learning models.

You have a local MCP server with these tools available:
  - list_uploaded_files
  - analyze_csv_head
  - get_dataset_info
  - detect_problem_type
  - generate_eda_report
  - create_visualization
  - train_baseline_model
  - download_main_code_file

Rules of engagement:
1. If a user message references "my data", "the dataset", "this file", or similar, \
use the active_file from context as file_path. If no active file is provided and \
the user did not name one, call list_uploaded_files first.
2. Prefer calling tools to ground every factual claim about the dataset. Do not \
invent column names, row counts, or metrics.
3. When training a model, if the target column is not specified, ask the user. \
Do not guess.
4. After running tools, summarize results in plain language for a student audience. \
Mention saved output files by name (e.g. "Saved as plot_histogram_iris_*.png") so \
the user knows what they can download.
5. Be concise. Use short paragraphs and bullet lists. Avoid heavy markdown headers.
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


def _build_groq_messages(
    query: str,
    history: list[ChatMessage],
    active_file: str | None,
) -> list[dict[str, Any]]:
    context_lines = [SYSTEM_PROMPT]
    if active_file:
        context_lines.append(
            f"\nThe user's currently active dataset filename is: `{active_file}`. "
            "Use this as file_path unless the user specifies a different one."
        )
    else:
        context_lines.append(
            "\nNo active dataset is currently selected. If a tool needs file_path, "
            "either ask the user or call list_uploaded_files first."
        )

    messages: list[dict[str, Any]] = [{"role": "system", "content": "\n".join(context_lines)}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": query})
    return messages


async def run_chat(
    query: str,
    active_file: str | None,
    history: list[ChatMessage],
    mcp_server_script: str,
) -> ChatResponse:
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set. Add it to backend/.env")

    groq_client = Groq(api_key=settings.GROQ_API_KEY)
    transport = PythonStdioTransport(script_path=mcp_server_script)

    messages = _build_groq_messages(query, history, active_file)
    tool_call_log: list[ToolCallRecord] = []
    iterations = 0

    async with Client(transport) as mcp_client:
        tool_list = await mcp_client.list_tools()
        openai_tools = [_mcp_tool_to_openai_schema(t) for t in tool_list]
        log.info("Discovered %d MCP tools", len(openai_tools))

        for step in range(settings.MAX_TOOL_ITERATIONS):
            iterations = step + 1
            log.info("Groq call iteration=%d messages=%d", iterations, len(messages))

            completion = groq_client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
                temperature=0.2,
                max_tokens=2048,
            )
            choice = completion.choices[0]
            assistant_msg = choice.message

            serialized_assistant: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_msg.content or "",
            }
            if assistant_msg.tool_calls:
                serialized_assistant["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_msg.tool_calls
                ]
            messages.append(serialized_assistant)

            if not assistant_msg.tool_calls:
                final_text = assistant_msg.content or ""
                return ChatResponse(
                    answer=final_text.strip(),
                    tool_calls=tool_call_log,
                    iterations=iterations,
                )

            for tc in assistant_msg.tool_calls:
                tool_name = tc.function.name
                try:
                    raw_args = tc.function.arguments or "{}"
                    tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    tool_args = {}
                t0 = time.time()
                error: str | None = None
                result_payload: Any = None
                try:
                    mcp_result = await mcp_client.call_tool(tool_name, tool_args)
                    result_payload = _extract_tool_result(mcp_result)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    result_payload = {"error": error}
                duration_ms = int((time.time() - t0) * 1000)

                log.info(
                    "tool=%s args=%s status=%s duration_ms=%d",
                    tool_name, tool_args, "error" if error else "ok", duration_ms,
                )

                tool_call_log.append(
                    ToolCallRecord(
                        name=tool_name,
                        arguments=tool_args,
                        result=result_payload,
                        error=error,
                        duration_ms=duration_ms,
                    )
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tool_name,
                        "content": json.dumps(result_payload, default=str),
                    }
                )

        log.warning("Hit MAX_TOOL_ITERATIONS=%d without final answer", settings.MAX_TOOL_ITERATIONS)
        return ChatResponse(
            answer=(
                "I ran several tool calls but could not finalize an answer within the "
                "iteration limit. Please refine your question or try a smaller step."
            ),
            tool_calls=tool_call_log,
            iterations=iterations,
        )
