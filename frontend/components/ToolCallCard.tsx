"use client";

import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
} from "lucide-react";

import { useState } from "react";

import { API_BASE_URL, downloadUrl, staticOutputUrl } from "@/lib/api";
import { getToolDoneLabel } from "@/lib/toolEventMap";
import type { ToolCallRecord } from "@/lib/types";

interface Props {
  call: ToolCallRecord;
  index: number;
}

const IMAGE_EXT = /\.(png|jpg|jpeg|gif|webp)$/i;
const DOWNLOAD_EXT = /\.(py|md|joblib|csv|json|txt|html|parquet|ipynb|pdf)$/i;

interface Artifact {
  filename: string;
  kind: "image" | "file" | "report";
  url: string;
}

function collectArtifacts(value: unknown, acc: Artifact[] = []): Artifact[] {
  if (value == null) return acc;
  if (typeof value === "string") return acc;
  if (Array.isArray(value)) {
    value.forEach((v) => collectArtifacts(v, acc));
    return acc;
  }
  if (typeof value !== "object") return acc;

  const obj = value as Record<string, unknown>;

  const push = (filename: string, kind: Artifact["kind"], url: string) => {
    if (acc.some((a) => a.url === url)) return;
    acc.push({ filename, kind, url });
  };

  for (const [k, v] of Object.entries(obj)) {
    if (typeof v === "string") {
      if (k.endsWith("_url")) {
        const filename = v.split("/").pop() || v;
        const kind: Artifact["kind"] = k === "report_url"
          ? "report"
          : IMAGE_EXT.test(v) ? "image" : "file";
        push(filename, kind, v.startsWith("http") ? v : `${API_BASE_URL}${v}`);
      }
    } else if (typeof v === "object") {
      collectArtifacts(v, acc);
    }
  }

  for (const key of ["file", "model_file", "script_file", "plot_file", "report_file", "notebook_file", "pdf_file"]) {
    const fn = obj[key];
    if (typeof fn === "string") {
      if (IMAGE_EXT.test(fn)) push(fn, "image", staticOutputUrl(fn));
      else if (DOWNLOAD_EXT.test(fn)) push(fn, "file", downloadUrl(fn));
    }
  }

  return acc;
}

export default function ToolCallCard({ call, index }: Props) {
  const [open, setOpen] = useState(false);
  const artifacts = collectArtifacts(call.result);
  const succeeded = !call.error;
  const friendlyLabel = getToolDoneLabel(call.name);

  return (
    <div className="rounded-lg border border-canvas-500 bg-canvas-900/60 transition hover:border-canvas-400">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11px]"
      >
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-fg-300" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-fg-300" />
        )}
        <span className="flex-1 truncate font-medium text-fg-100">
          {friendlyLabel}
        </span>
        <span className="font-mono text-[10px] text-fg-400">{call.duration_ms} ms</span>
        <span className="flex items-center gap-1">
          {succeeded ? (
            <CheckCircle2 className="h-3 w-3 text-status-online" />
          ) : (
            <AlertCircle className="h-3 w-3 text-status-error" />
          )}
        </span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-canvas-500 px-3 py-2 text-[11px]">
          {/* Technical details — power user section */}
          <div className="flex items-center gap-2 rounded-md bg-canvas-900/80 px-2 py-1">
            <span className="font-mono text-[10px] text-fg-400">#{index + 1}</span>
            <code className="flex-1 truncate font-mono text-[10px] text-fg-300">{call.name}</code>
            {call.service && (
              <span className="rounded bg-canvas-700 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-400">
                {call.service}
              </span>
            )}
          </div>

          {Object.keys(call.arguments || {}).length > 0 && (
            <div>
              <div className="mb-1 font-semibold text-fg-200">Arguments</div>
              <pre className="overflow-x-auto rounded-md border border-canvas-500 bg-canvas-900 p-2 text-fg-100">
                {JSON.stringify(call.arguments, null, 2)}
              </pre>
            </div>
          )}

          <div>
            <div className="mb-1 font-semibold text-fg-200">
              {succeeded ? "Result" : "Error"}
            </div>
            <pre className="max-h-72 overflow-auto rounded-md border border-canvas-500 bg-canvas-900 p-2 text-fg-100">
              {succeeded
                ? JSON.stringify(call.result, null, 2)
                : call.error || "Unknown error"}
            </pre>
          </div>

          {artifacts.length > 0 && (
            <div>
              <div className="mb-1 font-semibold text-fg-200">Artifacts</div>
              <div className="flex flex-wrap gap-2">
                {artifacts.map((a, i) =>
                  a.kind === "image" ? (
                    <a
                      key={`${a.filename}-${i}`}
                      href={a.url}
                      target="_blank"
                      rel="noreferrer"
                      className="block max-w-[180px] rounded-md border border-canvas-500 bg-canvas-800 p-1 hover:border-accent-500/60"
                    >
                      <img src={a.url} alt={a.filename} className="max-h-32 rounded" />
                      <div className="mt-1 truncate px-1 text-[9px] text-fg-300">
                        {a.filename}
                      </div>
                    </a>
                  ) : a.kind === "report" ? (
                    <a
                      key={`${a.filename}-${i}`}
                      href={a.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded-md border border-accent-500/30 bg-accent-500/10 px-2 py-1 text-[11px] text-accent-400 hover:bg-accent-500/20"
                    >
                      <ExternalLink className="h-3 w-3" />
                      {a.filename}
                    </a>
                  ) : (
                    <a
                      key={`${a.filename}-${i}`}
                      href={a.url}
                      download
                      className="inline-flex items-center gap-1 rounded-md border border-canvas-500 bg-canvas-800 px-2 py-1 text-[11px] text-fg-100 hover:border-canvas-400"
                    >
                      <Download className="h-3 w-3" />
                      {a.filename}
                    </a>
                  ),
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
