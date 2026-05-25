"use client";

import { Database, FileSpreadsheet, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";

import { listDatasets } from "@/lib/api";
import type { DatasetItem, UploadResponse } from "@/lib/types";

import FileUploader from "./FileUploader";

interface Props {
  activeFile: string | null;
  onSelect: (filename: string | null) => void;
  onUploaded: (resp: UploadResponse) => void;
  refreshKey: number;
}

export default function DatasetSidebar({
  activeFile,
  onSelect,
  onUploaded,
  refreshKey,
}: Props) {
  const [files, setFiles] = useState<DatasetItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFiles = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listDatasets();
      setFiles(resp.files);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to list datasets.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchFiles();
  }, [refreshKey]);

  return (
    <aside className="flex h-full w-full flex-col gap-4 border-r border-ink-200 bg-white p-4">
      <div className="flex items-center gap-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white">
          <Database className="h-5 w-5" />
        </div>
        <div>
          <div className="text-sm font-semibold text-ink-900">AutoML Copilot</div>
          <div className="text-xs text-ink-500">MCP-powered · Phase 1</div>
        </div>
      </div>

      <FileUploader onUploaded={onUploaded} />

      <div className="flex items-center justify-between pt-2">
        <div className="text-xs font-semibold uppercase tracking-wide text-ink-500">
          Datasets
        </div>
        <button
          onClick={() => void fetchFiles()}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-ink-500 hover:bg-ink-100"
          title="Refresh"
        >
          <RotateCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="-mx-2 flex-1 overflow-y-auto pr-1">
        {error && (
          <div className="mx-2 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700">
            {error}
          </div>
        )}
        {!error && files.length === 0 && !loading && (
          <div className="mx-2 rounded-md border border-dashed border-ink-200 p-3 text-xs text-ink-500">
            No datasets uploaded yet. Upload a CSV to get started.
          </div>
        )}
        <ul className="space-y-1">
          {files.map((f) => {
            const isActive = f.filename === activeFile;
            return (
              <li key={f.filename}>
                <button
                  onClick={() => onSelect(isActive ? null : f.filename)}
                  className={[
                    "flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm transition",
                    isActive
                      ? "bg-brand-50 text-brand-700 ring-1 ring-brand-200"
                      : "hover:bg-ink-100 text-ink-700",
                  ].join(" ")}
                >
                  <FileSpreadsheet
                    className={`h-4 w-4 shrink-0 ${
                      isActive ? "text-brand-600" : "text-ink-400"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{f.filename}</div>
                    <div className="text-[11px] text-ink-500">
                      {f.size_kb.toFixed(1)} KB
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="rounded-lg bg-ink-100 p-3 text-[11px] leading-snug text-ink-600">
        <div className="font-semibold text-ink-700">Active file</div>
        <div className="mt-0.5 break-all">
          {activeFile ? activeFile : "None — the LLM will list files or ask."}
        </div>
      </div>
    </aside>
  );
}
