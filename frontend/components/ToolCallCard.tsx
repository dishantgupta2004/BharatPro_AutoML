"use client";

import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  Wrench,
} from "lucide-react";
import { useState } from "react";

import { downloadUrl, staticOutputUrl } from "@/lib/api";
import type { ToolCallRecord } from "@/lib/types";

interface Props {
  call: ToolCallRecord;
  index: number;
}

const IMAGE_EXT = /\.(png|jpg|jpeg|gif|webp)$/i;
const DOWNLOAD_EXT = /\.(py|md|joblib|csv|json|txt)$/i;

interface Artifact {
  filename: string;
  kind: "image" | "file";
}

function collectArtifacts(value: unknown, acc: Artifact[] = []): Artifact[] {
  if (value == null) return acc;
  if (typeof value === "string") {
    if (IMAGE_EXT.test(value) && !value.includes("/")) {
      acc.push({ filename: value, kind: "image" });
    } else if (DOWNLOAD_EXT.test(value) && !value.includes("/")) {
      acc.push({ filename: value, kind: "file" });
    }
    return acc;
  }
  if (Array.isArray(value)) {
    value.forEach((v) => collectArtifacts(v, acc));
    return acc;
  }
  if (typeof value === "object") {
    Object.entries(value as Record<string, unknown>).forEach(([k, v]) => {
      if (typeof v === "string") {
        if (
          (k === "file" || k === "report_file" || k === "script_file" || k === "model_file") &&
          v
        ) {
          if (IMAGE_EXT.test(v)) acc.push({ filename: v, kind: "image" });
          else acc.push({ filename: v, kind: "file" });
          return;
        }
      }
      collectArtifacts(v, acc);
    });
  }
  return acc;
}

export default function ToolCallCard({ call, index }: Props) {
  const [open, setOpen] = useState(false);
  const artifacts = collectArtifacts(call.result);
  const succeeded = !call.error;

  return (
    <div className="rounded-lg border border-ink-200 bg-ink-50/60">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 text-ink-500" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-ink-500" />
        )}
        <Wrench className="h-3.5 w-3.5 text-brand-600" />
        <span className="font-mono font-semibold text-ink-800">
          #{index + 1} {call.name}
        </span>
        <span className="text-ink-500">·</span>
        <span className="text-ink-500">{call.duration_ms} ms</span>
        <span className="ml-auto flex items-center gap-1">
          {succeeded ? (
            <>
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
              <span className="text-emerald-700">ok</span>
            </>
          ) : (
            <>
              <AlertCircle className="h-3.5 w-3.5 text-red-600" />
              <span className="text-red-700">error</span>
            </>
          )}
        </span>
      </button>

      {open && (
        <div className="space-y-2 border-t border-ink-200 px-3 py-2 text-xs">
          <div>
            <div className="mb-1 font-semibold text-ink-700">Arguments</div>
            <pre className="overflow-x-auto rounded-md bg-ink-900 p-2 text-ink-50">
{JSON.stringify(call.arguments, null, 2)}
            </pre>
          </div>
          <div>
            <div className="mb-1 font-semibold text-ink-700">
              {succeeded ? "Result" : "Error"}
            </div>
            <pre className="max-h-72 overflow-auto rounded-md bg-ink-900 p-2 text-ink-50">
{succeeded
  ? JSON.stringify(call.result, null, 2)
  : call.error || "Unknown error"}
            </pre>
          </div>

          {artifacts.length > 0 && (
            <div>
              <div className="mb-1 font-semibold text-ink-700">Artifacts</div>
              <div className="flex flex-wrap gap-3">
                {artifacts.map((a) =>
                  a.kind === "image" ? (
                    <a
                      key={a.filename}
                      href={staticOutputUrl(a.filename)}
                      target="_blank"
                      rel="noreferrer"
                      className="block max-w-xs rounded-md border border-ink-200 bg-white p-1 hover:border-brand-400"
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={staticOutputUrl(a.filename)}
                        alt={a.filename}
                        className="max-h-60 rounded"
                      />
                      <div className="mt-1 truncate px-1 text-[11px] text-ink-500">
                        {a.filename}
                      </div>
                    </a>
                  ) : (
                    <a
                      key={a.filename}
                      href={downloadUrl(a.filename)}
                      className="inline-flex items-center gap-1 rounded-md border border-ink-200 bg-white px-2 py-1 text-xs text-ink-700 hover:border-brand-400 hover:text-brand-700"
                    >
                      <Download className="h-3.5 w-3.5" />
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
