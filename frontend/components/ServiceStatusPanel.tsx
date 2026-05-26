"use client";

import { Activity, RotateCw } from "lucide-react";
import { useServiceNetwork } from "@/hooks/useServiceNetwork";
import type { ServiceState } from "@/lib/types";

const SERVICE_LABEL: Record<string, string> = {
  "mcp-data": "Data & Schema",
  "mcp-eda": "EDA & Charts",
  "mcp-modeling": "Modeling",
  "mcp-explain": "Explainability",
  "mcp-export": "Export",
};

function StatusDot({ status }: { status: ServiceState["status"] }) {
  const tone =
    status === "online"
      ? "bg-status-online"
      : status === "processing"
        ? "bg-status-processing animate-pulse-soft"
        : status === "error"
          ? "bg-status-error"
          : "bg-status-offline";
  return (
    <span className="relative inline-flex h-2 w-2 shrink-0">
      <span
        className={`absolute inline-flex h-full w-full rounded-full ${tone} opacity-50 ${
          status === "processing" ? "animate-ping" : ""
        }`}
      />
      <span className={`relative inline-flex h-2 w-2 rounded-full ${tone}`} />
    </span>
  );
}

export default function ServiceStatusPanel() {
  const { services, loading, refresh, countByStatus } = useServiceNetwork();

  const online = countByStatus.online;
  const total = services.length || 5;

  return (
    <div className="rounded-xl border border-canvas-500 bg-canvas-800/50 p-3 shadow-elevate">
      <div className="mb-2.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5 text-accent-400" />
          <span className="text-[10px] font-semibold uppercase tracking-wider text-fg-200">
            MCP Network
          </span>
        </div>
        <button
          onClick={() => void refresh()}
          className="rounded p-1 text-fg-300 hover:bg-canvas-600 hover:text-fg-100"
          title="Re-check all services"
        >
          <RotateCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="mb-2 flex items-center gap-1.5 text-[11px]">
        <span className="rounded-md bg-canvas-700 px-1.5 py-0.5 font-mono font-semibold text-status-online">
          {online}/{total}
        </span>
        <span className="text-fg-300">online</span>
        {countByStatus.processing > 0 && (
          <span className="ml-auto rounded-md bg-canvas-700 px-1.5 py-0.5 font-mono text-status-processing">
            {countByStatus.processing} busy
          </span>
        )}
      </div>

      <ul className="space-y-0.5">
        {services.map((s) => (
          <li
            key={s.name}
            className="group flex items-center gap-2 rounded-md px-1.5 py-1.5 text-xs hover:bg-canvas-700"
            title={s.last_error || `${s.tools.length} tools · ${s.resources.length} resources · ${s.prompts.length} prompts`}
          >
            <StatusDot status={s.status} />
            <span className="min-w-0 flex-1 truncate text-fg-100">
              {SERVICE_LABEL[s.name] || s.name}
            </span>
            <span className="font-mono text-[10px] text-fg-300">
              {s.url.match(/:(\d+)/)?.[1] ?? ""}
            </span>
          </li>
        ))}
        {services.length === 0 && (
          <li className="px-1.5 py-2 text-xs text-fg-300">No services discovered.</li>
        )}
      </ul>
    </div>
  );
}