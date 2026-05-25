"use client";

import { Send } from "lucide-react";
import { useEffect, useRef } from "react";

interface Props {
  value: string;
  onChange: (val: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  activeFile: string | null;
}

export default function ChatComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  activeFile,
}: Props) {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = `${Math.min(ref.current.scrollHeight, 200)}px`;
    }
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && value.trim()) onSubmit();
    }
  };

  return (
    <div className="border-t border-ink-200 bg-white px-4 py-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <div className="flex-1 rounded-2xl border border-ink-200 bg-ink-50 px-3 py-2 shadow-soft focus-within:border-brand-400 focus-within:bg-white">
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              activeFile
                ? `Ask anything about ${activeFile}…`
                : "Upload a CSV or ask the assistant to list available datasets…"
            }
            rows={1}
            className="block w-full resize-none bg-transparent text-sm text-ink-900 placeholder:text-ink-400 focus:outline-none"
          />
          {activeFile && (
            <div className="mt-1 text-[11px] text-ink-500">
              Active file: <span className="font-mono text-ink-700">{activeFile}</span>
            </div>
          )}
        </div>
        <button
          disabled={disabled || !value.trim()}
          onClick={onSubmit}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white shadow-soft transition disabled:cursor-not-allowed disabled:bg-ink-300 disabled:text-white"
          title="Send (Enter)"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
      <div className="mx-auto mt-1.5 max-w-3xl text-[11px] text-ink-400">
        Press <kbd className="rounded bg-ink-100 px-1 py-0.5">Enter</kbd> to send · <kbd className="rounded bg-ink-100 px-1 py-0.5">Shift</kbd>+<kbd className="rounded bg-ink-100 px-1 py-0.5">Enter</kbd> for newline
      </div>
    </div>
  );
}
