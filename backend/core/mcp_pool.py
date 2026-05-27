"""In-process MCP client pool — same protocol, no HTTP, no sockets.

We import the 5 FastMCP server instances directly and wrap each in a Client via
FastMCPTransport. The unified tool/resource/prompt registry, the SSE status
stream, and the progress bridge all behave identically to the HTTP version.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from fastmcp import Client
from fastmcp.client.transports import FastMCPTransport

from core.logger import get_logger

log = get_logger("mcp.pool")


# Server instances are imported at registration time (see register_default_servers)
@dataclass
class ServiceState:
    name: str
    url: str  # kept as a label, e.g. "in-process://mcp-data"
    status: str = "offline"
    last_error: str | None = None
    last_seen: float = 0.0
    tool_names: list[str] = field(default_factory=list)
    resource_uris: list[str] = field(default_factory=list)
    prompt_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "url": self.url, "status": self.status,
            "last_error": self.last_error,
            "last_seen": int(self.last_seen) if self.last_seen else 0,
            "tools": self.tool_names, "resources": self.resource_uris,
            "prompts": self.prompt_names,
        }


class MCPClientPool:
    def __init__(self) -> None:
        self._exit_stack: contextlib.AsyncExitStack | None = None
        self._server_instances: dict[str, Any] = {}  # name -> FastMCP instance
        self.clients: dict[str, Client] = {}
        self.states: dict[str, ServiceState] = {}
        self.tool_index: dict[str, str] = {}
        self.tool_schemas: list[dict[str, Any]] = []
        self.resource_index: dict[str, str] = {}
        self.prompt_index: dict[str, str] = {}
        self.prompts_meta: list[dict[str, Any]] = []
        self._observers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    def register(self, name: str, server: Any) -> None:
        """Register an in-process FastMCP server instance under a logical name."""
        self._server_instances[name] = server
        self.states[name] = ServiceState(name=name, url=f"in-process://{name}")

    # ── Lifecycle ────────────────────────────────────────────────
    async def start(self) -> None:
        self._exit_stack = contextlib.AsyncExitStack()
        await self._exit_stack.__aenter__()
        for name, server in self._server_instances.items():
            await self._connect_one(name, server)
        await self._rebuild_registries()
        log.info(
            "Pool ready (in-process): %d/%d services online, %d unified tools",
            sum(1 for s in self.states.values() if s.status == "online"),
            len(self.states), len(self.tool_index),
        )

    async def _connect_one(self, name: str, server: Any) -> None:
        assert self._exit_stack is not None
        state = self.states[name]
        try:
            client = Client(FastMCPTransport(server))
            await self._exit_stack.enter_async_context(client)
            self.clients[name] = client
            state.status = "online"
            state.last_seen = time.time()
            state.last_error = None
            log.info("Connected %s (in-process)", name)
        except Exception as exc:
            state.status = "offline"
            state.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("Failed to connect %s: %s", name, exc)
        await self._notify_observers(state)

    async def shutdown(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(None, None, None)
            self._exit_stack = None
        self.clients.clear()

    # ── Catalog assembly (unchanged) ─────────────────────────────
    async def _rebuild_registries(self) -> None:
        self.tool_index.clear()
        self.tool_schemas.clear()
        self.resource_index.clear()
        self.prompt_index.clear()
        self.prompts_meta.clear()

        for name, client in self.clients.items():
            state = self.states[name]
            try:
                tools = await client.list_tools()
                state.tool_names = [t.name for t in tools]
                for t in tools:
                    canonical = t.name
                    if canonical in self.tool_index:
                        canonical = f"{name.replace('-', '_')}__{t.name}"
                    self.tool_index[canonical] = name
                    self.tool_schemas.append(_to_openai_schema(canonical, t))

                try:
                    resources = await client.list_resources()
                    state.resource_uris = [str(r.uri) for r in resources]
                    for r in resources:
                        self.resource_index[str(r.uri)] = name
                except Exception as exc:
                    log.debug("list_resources unavailable on %s: %s", name, exc)

                try:
                    prompts = await client.list_prompts()
                    state.prompt_names = [p.name for p in prompts]
                    for p in prompts:
                        self.prompt_index[p.name] = name
                        self.prompts_meta.append({
                            "name": p.name,
                            "description": getattr(p, "description", None) or "",
                            "service": name,
                            "arguments": [
                                {"name": a.name,
                                 "description": getattr(a, "description", None),
                                 "required": bool(getattr(a, "required", False))}
                                for a in (getattr(p, "arguments", None) or [])
                            ],
                        })
                except Exception as exc:
                    log.debug("list_prompts unavailable on %s: %s", name, exc)

                state.last_seen = time.time()
            except Exception as exc:
                state.status = "error"
                state.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("Catalog refresh failed for %s: %s", name, exc)
                await self._notify_observers(state)

    # ── Routing ───────────────────────────────────────────────────
    def service_for_tool(self, tool_name: str) -> str | None:
        return self.tool_index.get(tool_name)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        progress_handler: Callable[..., Awaitable[None]] | None = None,
        log_handler: Callable[[Any], Awaitable[None]] | None = None,
    ) -> Any:
        service = self.tool_index.get(tool_name)
        if service is None:
            raise KeyError(f"Tool not in unified registry: {tool_name}")
        actual_name = tool_name
        if "__" in tool_name and tool_name.split("__", 1)[0].replace("_", "-") == service:
            actual_name = tool_name.split("__", 1)[1]

        client = self.clients.get(service)
        state = self.states[service]
        if client is None:
            state.status = "offline"
            raise RuntimeError(f"Service `{service}` is not connected")

        state.status = "processing"
        await self._notify_observers(state)
        try:
            kwargs: dict[str, Any] = {}
            if progress_handler is not None:
                kwargs["progress_handler"] = progress_handler
            result = await client.call_tool(actual_name, arguments, **kwargs)
            state.status = "online"
            state.last_seen = time.time()
            state.last_error = None
            await self._notify_observers(state)
            return result
        except Exception as exc:
            state.last_error = f"{type(exc).__name__}: {exc}"
            state.status = "error"
            await self._notify_observers(state)
            raise

    async def read_resource(self, uri: str) -> Any:
        service = self.resource_index.get(uri)
        if service is None:
            for known_uri, svc in self.resource_index.items():
                if "{" in known_uri and uri.split("/")[0] == known_uri.split("/")[0]:
                    service = svc
                    break
        if service is None:
            raise KeyError(f"Resource URI not in registry: {uri}")
        return await self.clients[service].read_resource(uri)

    async def get_prompt(self, name: str, arguments: dict[str, Any]) -> Any:
        service = self.prompt_index.get(name)
        if service is None:
            raise KeyError(f"Prompt not in registry: {name}")
        return await self.clients[service].get_prompt(name, arguments)

    # ── Health / observer API ────────────────────────────────────
    def snapshot(self) -> dict[str, Any]:
        return {
            "services": [s.to_dict() for s in self.states.values()],
            "tool_count": len(self.tool_index),
            "resource_count": len(self.resource_index),
            "prompt_count": len(self.prompt_index),
            "prompts": self.prompts_meta,
        }

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._observers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._observers.discard(q)

    async def _notify_observers(self, state: ServiceState) -> None:
        payload = {"type": "service_status", "service": state.to_dict()}
        for q in list(self._observers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def refresh_all(self) -> None:
        async with self._lock:
            for name, state in self.states.items():
                if state.status == "offline":
                    server = self._server_instances.get(name)
                    if server is not None:
                        await self._connect_one(name, server)
            await self._rebuild_registries()

    async def status_event_stream(self) -> AsyncIterator[dict[str, Any]]:
        q = self.subscribe()
        try:
            yield {"type": "snapshot", "payload": self.snapshot()}
            while True:
                evt = await q.get()
                yield evt
        finally:
            self.unsubscribe(q)


def _to_openai_schema(canonical_name: str, tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None) or {}
    if not isinstance(schema, dict) or "type" not in schema:
        schema = {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": canonical_name,
            "description": (tool.description or "").strip(),
            "parameters": schema,
        },
    }


def register_default_servers(pool: MCPClientPool) -> None:
    """Import the 5 FastMCP server modules and register their instances.

    These imports are deferred until pool startup so that heavy ML deps don't
    load at module-import time (matters for test/CI imports of main).
    """
    from mcp_data import mcp as mcp_data
    from mcp_eda import mcp as mcp_eda
    from mcp_modeling import mcp as mcp_modeling
    from mcp_explain import mcp as mcp_explain
    from mcp_export import mcp as mcp_export

    pool.register("mcp-data", mcp_data)
    pool.register("mcp-eda", mcp_eda)
    pool.register("mcp-modeling", mcp_modeling)
    pool.register("mcp-explain", mcp_explain)
    pool.register("mcp-export", mcp_export)