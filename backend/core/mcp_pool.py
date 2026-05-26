"""Multi-MCP-client connection pool.

Manages 5 long-lived `fastmcp.Client` connections (one per microservice),
merges their tool / resource / prompt catalogs into a single unified registry,
and offers resilient call-routing with per-service health tracking.

Used by:
  - core/orchestrator.py (route tool calls)
  - main.py              (health endpoint, SSE status push)
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from core.config import settings
from core.logger import get_logger

log = get_logger("mcp.pool")


@dataclass
class ServiceState:
    """Runtime state for one upstream microservice."""

    name: str
    url: str
    status: str = "offline"  # offline | online | processing | error
    last_error: str | None = None
    last_seen: float = 0.0
    tool_names: list[str] = field(default_factory=list)
    resource_uris: list[str] = field(default_factory=list)
    prompt_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "status": self.status,
            "last_error": self.last_error,
            "last_seen": int(self.last_seen) if self.last_seen else 0,
            "tools": self.tool_names,
            "resources": self.resource_uris,
            "prompts": self.prompt_names,
        }


class MCPClientPool:
    """Owns one Client per microservice and a unified tool / resource / prompt index."""

    def __init__(self) -> None:
        self._exit_stack: contextlib.AsyncExitStack | None = None
        self.clients: dict[str, Client] = {}
        self.states: dict[str, ServiceState] = {
            name: ServiceState(name=name, url=url)
            for name, url in settings.microservice_map.items()
        }
        # Indexes — name -> service id (so the LLM sees a flat catalog)
        self.tool_index: dict[str, str] = {}
        self.tool_schemas: list[dict[str, Any]] = []
        self.resource_index: dict[str, str] = {}
        self.prompt_index: dict[str, str] = {}
        self.prompts_meta: list[dict[str, Any]] = []
        # Observers (SSE listeners for status updates)
        self._observers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Open one persistent connection per microservice. Resilient: any
        individual failure is recorded but does not abort the pool."""
        self._exit_stack = contextlib.AsyncExitStack()
        await self._exit_stack.__aenter__()

        for name, url in settings.microservice_map.items():
            await self._connect_one(name, url)

        await self._rebuild_registries()
        log.info(
            "Pool ready: %d/%d services online, %d unified tools",
            sum(1 for s in self.states.values() if s.status == "online"),
            len(self.states),
            len(self.tool_index),
        )

    async def _connect_one(self, name: str, url: str) -> None:
        """Open one client; catch failures and mark service offline."""
        assert self._exit_stack is not None
        state = self.states[name]
        try:
            transport = StreamableHttpTransport(url=url)
            client = Client(transport)
            await self._exit_stack.enter_async_context(client)
            self.clients[name] = client
            state.status = "online"
            state.last_seen = time.time()
            state.last_error = None
            log.info("Connected %s @ %s", name, url)
        except Exception as exc:
            state.status = "offline"
            state.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("Failed to connect %s @ %s: %s", name, url, exc)
        await self._notify_observers(state)

    async def shutdown(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(None, None, None)
            self._exit_stack = None
        self.clients.clear()

    # ------------------------------------------------------------------
    # Catalog assembly
    # ------------------------------------------------------------------
    async def _rebuild_registries(self) -> None:
        """Query every online client for its tools / resources / prompts and
        merge into the unified index. Name collisions get a service suffix."""
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
                        self.prompts_meta.append(
                            {
                                "name": p.name,
                                "description": getattr(p, "description", None) or "",
                                "service": name,
                                "arguments": [
                                    {
                                        "name": a.name,
                                        "description": getattr(a, "description", None),
                                        "required": bool(getattr(a, "required", False)),
                                    }
                                    for a in (getattr(p, "arguments", None) or [])
                                ],
                            }
                        )
                except Exception as exc:
                    log.debug("list_prompts unavailable on %s: %s", name, exc)

                state.last_seen = time.time()
            except Exception as exc:
                state.status = "error"
                state.last_error = f"{type(exc).__name__}: {exc}"
                log.warning("Catalog refresh failed for %s: %s", name, exc)
                await self._notify_observers(state)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    def service_for_tool(self, tool_name: str) -> str | None:
        return self.tool_index.get(tool_name)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        progress_handler: Callable[..., Awaitable[None]] | None = None,
        log_handler: Callable[[Any], Awaitable[None]] | None = None,
    ) -> Any:
        """Resilient tool invocation. If the owning microservice crashed,
        captures the error and marks the service offline without affecting
        the others."""
        service = self.tool_index.get(tool_name)
        if service is None:
            raise KeyError(f"Tool not in unified registry: {tool_name}")

        # If the tool name was a collision-mangled key, strip the prefix
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
            # fastmcp accepts progress_handler / log_handler as call kwargs on Client
            result = await client.call_tool(actual_name, arguments, **kwargs)
            state.status = "online"
            state.last_seen = time.time()
            state.last_error = None
            await self._notify_observers(state)
            return result
        except Exception as exc:
            state.last_error = f"{type(exc).__name__}: {exc}"
            # Distinguish recoverable tool error from a hard service crash:
            # if it's a connection-level failure, mark offline; otherwise error.
            msg = str(exc).lower()
            if any(k in msg for k in ("connection", "refused", "closed", "timeout")):
                state.status = "offline"
            else:
                state.status = "error"
            await self._notify_observers(state)
            raise

    async def read_resource(self, uri: str) -> Any:
        service = self.resource_index.get(uri)
        if service is None:
            # Allow uri-pattern resources too — search by prefix
            for known_uri, svc in self.resource_index.items():
                if "{" in known_uri:
                    if uri.split("/")[0] == known_uri.split("/")[0]:
                        service = svc
                        break
        if service is None:
            raise KeyError(f"Resource URI not in registry: {uri}")
        client = self.clients[service]
        return await client.read_resource(uri)

    async def get_prompt(self, name: str, arguments: dict[str, Any]) -> Any:
        service = self.prompt_index.get(name)
        if service is None:
            raise KeyError(f"Prompt not in registry: {name}")
        client = self.clients[service]
        return await client.get_prompt(name, arguments)

    # ------------------------------------------------------------------
    # Health / observer API
    # ------------------------------------------------------------------
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
        """Re-poll every offline service in case it came back up."""
        async with self._lock:
            for name, state in self.states.items():
                if state.status == "offline":
                    url = settings.microservice_map[name]
                    await self._connect_one(name, url)
            await self._rebuild_registries()

    async def status_event_stream(self) -> AsyncIterator[dict[str, Any]]:
        """Long-lived async generator yielding status updates."""
        q = self.subscribe()
        try:
            # Always send a snapshot up-front
            yield {"type": "snapshot", "payload": self.snapshot()}
            while True:
                evt = await q.get()
                yield evt
        finally:
            self.unsubscribe(q)


def _to_openai_schema(canonical_name: str, tool: Any) -> dict[str, Any]:
    """Convert a fastmcp Tool descriptor to the OpenAI function-calling shape."""
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