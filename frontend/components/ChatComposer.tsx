"use client";

import { Send, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { PromptDescriptor } from "@/lib/types";

import PromptCommandMenu from "./PromptCommandMenu";

interface Props {
  value: string;
  onChange: (val: string) => void;
  onSubmit: (overrides?: {
    promptName: string;
    promptArguments: Record<string, unknown>;
  }) => void;
  disabled: boolean;
  activeFile: string | null;
  pinnedPrompt: PromptDescriptor | null;
  onClearPrompt: () => void;
  onPickPrompt: (p: PromptDescriptor) => void;
}

export default function ChatComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  activeFile,
  pinnedPrompt,
  onClearPrompt,
  onPickPrompt,
}: Props) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = `${Math.min(ref.current.scrollHeight, 200)}px`;
    }
  }, [value]);

  // Detect slash-command intent
  const slashQuery = useMemo(() => {
    const m = value.match(/(^|\s)\/([\w-]*)$/);
    return m ? m[2] : null;
  }, [value]);

  useEffect(() => {
    setMenuOpen(slashQuery !== null);
  }, [slashQuery]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (menuOpen) {
      // Let the menu handle navigation/selection
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && (value.trim() || pinnedPrompt)) onSubmit();
    }
  };

  const handlePick = (p: PromptDescriptor) => {
    // Strip the partial slash command from the textarea
    onChange(value.replace(/(^|\s)\/([\w-]*)$/, "$1").trimEnd());
    setMenuOpen(false);
    onPickPrompt(p);
  };

  return (
    <div className="border-t border-canvas-500 bg-canvas-900/80 px-4 py-3 backdrop-blur">
      <div className="relative mx-auto flex max-w-3xl items-end gap-2">
        {/* Slash menu */}
        <PromptCommandMenu
          open={menuOpen}
          query={slashQuery ?? ""}
          onPick={handlePick}
          onClose={() => setMenuOpen(false)}
        />

        <div className="focus-ring flex-1 rounded-2xl border border-canvas-500 bg-canvas-800 px-3 py-2 transition focus-within:border-accent-500/60">
          {pinnedPrompt && (
            <div className="mb-1.5 flex items-center gap-2 rounded-lg border border-accent-500/30 bg-accent-500/10 px-2 py-1">
              <Sparkles className="h-3 w-3 text-accent-400" />
              <span className="font-mono text-[11px] font-semibold text-fg-50">
                /{pinnedPrompt.name}
              </span>
              <span className="text-[10px] text-fg-300">queued</span>
              <button
                onClick={onClearPrompt}
                className="ml-auto rounded p-0.5 text-fg-300 hover:bg-canvas-700 hover:text-fg-50"
                aria-label="Clear prompt"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          )}
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              activeFile
                ? `Ask anything about ${activeFile}…   ( / for prompt commands )`
                : "Upload a CSV first, or type / to see prompt commands…"
            }
            rows={1}
            className="block w-full resize-none bg-transparent text-[14px] text-fg-50 placeholder:text-fg-300 focus:outline-none"
          />
          {activeFile && (
            <div className="mt-1 text-[10px] text-fg-300">
              Active file: <span className="font-mono text-fg-100">{activeFile}</span>
            </div>
          )}
        </div>

        <button
          disabled={disabled || (!value.trim() && !pinnedPrompt)}
          onClick={() => onSubmit()}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-600 text-white shadow-glow transition hover:bg-accent-500 disabled:cursor-not-allowed disabled:bg-canvas-600 disabled:text-fg-300 disabled:shadow-none"
          title="Send (Enter)"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
      <div className="mx-auto mt-1.5 max-w-3xl text-[10px] text-fg-300">
        <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for newline · <kbd>/</kbd> for prompts
      </div>
    </div>
  );
}