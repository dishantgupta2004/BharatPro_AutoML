"use client";

import { CloudUpload, FileSpreadsheet, Loader2, RotateCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { listDatasets, uploadCsv } from "@/lib/api";
import type { DatasetItem, UploadResponse } from "@/lib/types";

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
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const fetchFiles = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listDatasets();
      setFiles(resp.files);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to list.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchFiles();
  }, [refreshKey]);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      if (!file.name.match(/\.(csv|tsv)$/i)) {
        setError("Only .csv or .tsv accepted.");
        return;
      }
      setBusy(true);
      try {
        const resp = await uploadCsv(file);
        onUploaded(resp);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Upload failed.");
      } finally {
        setBusy(false);
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    [onUploaded],
  );

  return (
    <aside className="flex h-full w-full flex-col border-l border-canvas-500 bg-canvas-800/30">
      <div className="border-b border-canvas-500 px-4 py-2.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-fg-200">
          Datasets
        </span>
      </div>

      <div className="p-3">
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files?.[0];
            if (f) void handleFile(f);
          }}
          className={[
            "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-5 text-center transition",
            dragging
              ? "border-accent-500 bg-accent-500/10"
              : "border-canvas-500 bg-canvas-800/40 hover:border-accent-500/60 hover:bg-canvas-800",
            busy ? "pointer-events-none opacity-70" : "",
          ].join(" ")}
        >
          {busy ? (
            <Loader2 className="h-5 w-5 animate-spin text-accent-400" />
          ) : (
            <CloudUpload className="h-5 w-5 text-fg-300 group-hover:text-accent-400" />
          )}
          <div className="mt-2 text-[12px] font-medium text-fg-100">
            {busy ? "Uploading…" : "Drop CSV or click"}
          </div>
          <div className="mt-0.5 text-[10px] text-fg-300">.csv or .tsv — local-only</div>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,.tsv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFile(f);
            }}
          />
        </div>
        {error && <div className="mt-2 text-[11px] text-status-error">{error}</div>}
      </div>

      <div className="flex items-center justify-between border-t border-canvas-500 px-3 py-2">
        <span className="text-[10px] uppercase tracking-wider text-fg-300">Files</span>
        <button
          onClick={() => void fetchFiles()}
          className="rounded p-1 text-fg-300 hover:bg-canvas-700 hover:text-fg-100"
          title="Refresh"
        >
          <RotateCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3">
        {!error && files.length === 0 && !loading && (
          <div className="mx-2 rounded-md border border-dashed border-canvas-500 p-3 text-[11px] text-fg-300">
            No datasets uploaded yet.
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
                    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] transition",
                    isActive
                      ? "bg-accent-500/15 text-fg-50 ring-1 ring-accent-500/30"
                      : "text-fg-100 hover:bg-canvas-700",
                  ].join(" ")}
                >
                  <FileSpreadsheet
                    className={`h-3.5 w-3.5 shrink-0 ${
                      isActive ? "text-accent-400" : "text-fg-300"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{f.filename}</div>
                    <div className="text-[10px] text-fg-300">
                      {f.size_kb.toFixed(1)} KB
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}