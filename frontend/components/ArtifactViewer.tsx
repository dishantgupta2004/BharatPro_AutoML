"use client";

import {
  Download,
  ExternalLink,
  FileSpreadsheet,
  ImageIcon,
  Layers,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";

import type { WorkspaceArtifact } from "@/lib/types";

interface Props {
  artifacts: WorkspaceArtifact[];
  onClear: () => void;
}

type TabKey = "all" | "image" | "report" | "table" | "file";

const TABS: { key: TabKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "image", label: "Charts" },
  { key: "report", label: "Reports" },
  { key: "table", label: "Tables" },
  { key: "file", label: "Files" },
];

function ArtifactCard({ a }: { a: WorkspaceArtifact }) {
  if (a.kind === "image") {
    return (
      <div className="overflow-hidden rounded-xl border border-canvas-500 bg-canvas-800 shadow-elevate">
        <a href={a.url} target="_blank" rel="noreferrer" className="block">
          <img src={a.url} alt={a.title} className="w-full" />
        </a>
        <div className="flex items-center gap-2 px-3 py-2 text-[11px] text-fg-300">
          <ImageIcon className="h-3 w-3 text-accent-400" />
          <span className="truncate font-mono">{a.title}</span>
          {a.source_service && (
            <span className="ml-auto rounded bg-canvas-700 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider">
              {a.source_service}
            </span>
          )}
        </div>
      </div>
    );
  }

  if (a.kind === "report") {
    return (
      <a
        href={a.url}
        target="_blank"
        rel="noreferrer"
        className="block rounded-xl border border-accent-500/30 bg-accent-500/5 p-4 transition hover:border-accent-500/60"
      >
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-500/15 text-accent-400">
            <ExternalLink className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-semibold text-fg-50">HTML Report</div>
            <div className="truncate font-mono text-[10px] text-fg-300">{a.title}</div>
            {a.source_tool && (
              <div className="mt-1 text-[10px] text-fg-300">
                from <span className="font-mono">{a.source_tool}</span>
              </div>
            )}
          </div>
        </div>
      </a>
    );
  }

  if (a.kind === "table" && a.table) {
    const cols = a.table.columns.slice(0, 10);
    const rows = a.table.rows.slice(0, 20);
    return (
      <div className="overflow-hidden rounded-xl border border-canvas-500 bg-canvas-800 shadow-elevate">
        <div className="flex items-center gap-2 border-b border-canvas-500 px-3 py-2 text-[11px]">
          <FileSpreadsheet className="h-3 w-3 text-accent-400" />
          <span className="font-semibold text-fg-50">{a.title}</span>
          {a.source_service && (
            <span className="ml-auto rounded bg-canvas-700 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-300">
              {a.source_service}
            </span>
          )}
        </div>
        <div className="max-h-72 overflow-auto">
          <table className="w-full border-collapse text-left text-[11px]">
            <thead className="sticky top-0 bg-canvas-700">
              <tr>
                {cols.map((c) => (
                  <th
                    key={c}
                    className="border-b border-canvas-500 px-2 py-1.5 font-semibold text-fg-50"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr
                  key={i}
                  className={i % 2 === 0 ? "bg-canvas-800" : "bg-canvas-900/40"}
                >
                  {cols.map((c) => (
                    <td
                      key={c}
                      className="border-b border-canvas-500/60 px-2 py-1 font-mono text-fg-100"
                    >
                      {formatCell(r[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // file
  return (
    <a
      href={a.url}
      download
      className="flex items-center gap-3 rounded-xl border border-canvas-500 bg-canvas-800 p-3 transition hover:border-canvas-400"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-canvas-700 text-fg-100">
        <Download className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold text-fg-50">
          {a.title}
        </div>
        {a.source_tool && (
          <div className="text-[10px] text-fg-300">
            from <span className="font-mono">{a.source_tool}</span>
          </div>
        )}
      </div>
    </a>
  );
}

function formatCell(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toFixed(4);
  }
  return String(v);
}

export default function ArtifactViewer({ artifacts, onClear }: Props) {
  const [tab, setTab] = useState<TabKey>("all");

  useEffect(() => {
    if (tab !== "all" && !artifacts.some((a) => a.kind === tab)) {
      setTab("all");
    }
  }, [artifacts, tab]);

  const filtered =
    tab === "all" ? artifacts : artifacts.filter((a) => a.kind === tab);

  return (
    <div className="flex h-full flex-col bg-canvas-900/30">
      <div className="flex items-center justify-between border-b border-canvas-500 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Layers className="h-3.5 w-3.5 text-accent-400" />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-fg-200">
            Workspace
          </span>
          <span className="rounded bg-canvas-700 px-1.5 py-0.5 font-mono text-[10px] text-fg-300">
            {artifacts.length}
          </span>
        </div>
        {artifacts.length > 0 && (
          <button
            onClick={onClear}
            className="rounded p-1 text-fg-300 hover:bg-canvas-700 hover:text-status-error"
            title="Clear workspace"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-1 border-b border-canvas-500 px-3 py-1.5">
        {TABS.map((t) => {
          const count =
            t.key === "all"
              ? artifacts.length
              : artifacts.filter((a) => a.kind === t.key).length;
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={[
                "rounded-md px-2.5 py-1 text-[11px] font-medium transition",
                active
                  ? "bg-canvas-700 text-fg-50 shadow-ring"
                  : "text-fg-300 hover:bg-canvas-800 hover:text-fg-100",
              ].join(" ")}
            >
              {t.label}
              {count > 0 && (
                <span className="ml-1.5 rounded bg-canvas-600 px-1 py-0.5 font-mono text-[9px] text-fg-200">
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {filtered.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="max-w-xs text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-dashed border-canvas-500 bg-canvas-800/50">
                <Layers className="h-5 w-5 text-fg-300" />
              </div>
              <div className="text-[13px] font-semibold text-fg-100">
                No artifacts yet
              </div>
              <div className="mt-1 text-[11px] text-fg-300">
                Run a profile, train a model, or render a SHAP chart — results
                land here.
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((a) => (
              <ArtifactCard key={a.id} a={a} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}