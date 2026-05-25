"use client";

import { CloudUpload, Loader2 } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { uploadCsv } from "@/lib/api";
import type { UploadResponse } from "@/lib/types";

interface Props {
  onUploaded: (resp: UploadResponse) => void;
  compact?: boolean;
}

export default function FileUploader({ onUploaded, compact = false }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      if (!file.name.match(/\.(csv|tsv)$/i)) {
        setError("Only .csv or .tsv files are accepted.");
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

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) void handleFile(f);
  };

  return (
    <div className="space-y-2">
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={[
          "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed text-center transition",
          compact ? "p-4" : "p-6",
          dragging
            ? "border-brand-500 bg-brand-50"
            : "border-ink-200 bg-white hover:border-brand-400 hover:bg-brand-50/40",
          busy ? "pointer-events-none opacity-70" : "",
        ].join(" ")}
      >
        {busy ? (
          <Loader2 className="h-6 w-6 animate-spin text-brand-600" />
        ) : (
          <CloudUpload className="h-6 w-6 text-ink-400 group-hover:text-brand-600" />
        )}
        <div className="mt-2 text-sm font-medium text-ink-800">
          {busy ? "Uploading…" : "Drop a CSV here or click to browse"}
        </div>
        {!compact && (
          <div className="mt-1 text-xs text-ink-500">.csv or .tsv — kept locally on your machine</div>
        )}
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
      {error && <div className="text-xs text-red-600">{error}</div>}
    </div>
  );
}
