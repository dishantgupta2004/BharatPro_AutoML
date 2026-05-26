"use client";

import { Command, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { listPrompts } from "@/lib/api";
import type { PromptDescriptor } from "@/lib/types";

interface Props {
  open: boolean;
  query: string;
  onPick: (p: PromptDescriptor) => void;
  onClose: () => void;
}

export default function PromptCommandMenu({ open, query, onPick, onClose }: Props) {
  const [prompts, setPrompts] = useState<PromptDescriptor[]>([]);
  const [highlight, setHighlight] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const resp = await listPrompts();
        if (!cancelled) setPrompts(resp.prompts as PromptDescriptor[]);
      } catch {
        if (!cancelled) setPrompts([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  const filtered = useMemo(() => {
    if (!query) return prompts;
    const q = query.toLowerCase();
    return prompts.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q),
    );
  }, [query, prompts]);

  useEffect(() => {
    setHighlight(0);
  }, [query, open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlight((h) => Math.min(h + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlight((h) => Math.max(h - 1, 0));
      } else if (e.key === "Enter" && filtered[highlight]) {
        e.preventDefault();
        onPick(filtered[highlight]);
      }
    };
    document.addEventListener("keydown", handler, true);
    return () => document.removeEventListener("keydown", handler, true);
  }, [open, filtered, highlight, onPick, onClose]);

  if (!open) return null;

  return (
    <div className="absolute bottom-full left-0 right-0 mb-2 z-30 overflow-hidden rounded-xl border border-canvas-500 bg-canvas-800 shadow-elevate animate-slide-in">
      <div className="flex items-center gap-2 border-b border-canvas-500 px-3 py-2 text-[11px] uppercase tracking-wider text-fg-300">
        <Command className="h-3 w-3" />
        Prompt commands
      </div>
      <div className="max-h-72 overflow-y-auto py-1">
        {loading && (
          <div className="px-3 py-2 text-xs text-fg-300">Loading…</div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="px-3 py-3 text-xs text-fg-300">
            No prompt templates match "{query}".
          </div>
        )}
        {filtered.map((p, i) => (
          <button
            key={p.name}
            onMouseEnter={() => setHighlight(i)}
            onClick={() => onPick(p)}
            className={[
              "flex w-full items-start gap-2.5 px-3 py-2 text-left text-[13px] transition",
              i === highlight
                ? "bg-accent-500/15 text-fg-50"
                : "text-fg-100 hover:bg-canvas-700",
            ].join(" ")}
          >
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-400" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-mono font-semibold text-fg-50">
                  /{p.name}
                </span>
                <span className="rounded bg-canvas-700 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-fg-300">
                  {p.service}
                </span>
              </div>
              {p.description && (
                <div className="mt-0.5 line-clamp-2 text-[12px] text-fg-200">
                  {p.description}
                </div>
              )}
              {p.arguments.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {p.arguments.map((a) => (
                    <span
                      key={a.name}
                      className="rounded border border-canvas-500 bg-canvas-900 px-1.5 py-0.5 font-mono text-[10px] text-fg-300"
                    >
                      {a.name}
                      {a.required ? "*" : ""}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </button>
        ))}
      </div>
      <div className="border-t border-canvas-500 px-3 py-1.5 text-[10px] text-fg-300">
        <kbd>↑</kbd> <kbd>↓</kbd> to navigate · <kbd>Enter</kbd> to select · <kbd>Esc</kbd> to close
      </div>
    </div>
  );
}