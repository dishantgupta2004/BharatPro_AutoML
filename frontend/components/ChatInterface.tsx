"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { sendChat } from "@/lib/api";
import type { ChatMessage, UiMessage, UploadResponse } from "@/lib/types";

import ChatComposer from "./ChatComposer";
import DatasetSidebar from "./DatasetSidebar";
import EmptyState from "./EmptyState";
import MessageBubble from "./MessageBubble";

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const threadRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, busy]);

  const handleUploaded = useCallback((resp: UploadResponse) => {
    setActiveFile(resp.filename);
    setRefreshKey((k) => k + 1);
    const sysNote: UiMessage = {
      id: uid(),
      role: "assistant",
      content: `Uploaded **${resp.filename}** (${resp.rows.toLocaleString()} rows × ${resp.columns} columns). Selected as active dataset.\n\nColumns: ${resp.column_names.slice(0, 12).map((c) => `\`${c}\``).join(", ")}${resp.column_names.length > 12 ? "…" : ""}`,
    };
    setMessages((prev) => [...prev, sysNote]);
  }, []);

  const submit = useCallback(
    async (overrideText?: string) => {
      const text = (overrideText ?? input).trim();
      if (!text || busy) return;

      const userMsg: UiMessage = { id: uid(), role: "user", content: text };
      const pendingMsg: UiMessage = {
        id: uid(),
        role: "assistant",
        content: "",
        pending: true,
      };

      setMessages((prev) => [...prev, userMsg, pendingMsg]);
      setInput("");
      setBusy(true);

      const history: ChatMessage[] = messages
        .filter((m) => !m.pending && !m.errored)
        .map((m) => ({ role: m.role, content: m.content }));

      try {
        const resp = await sendChat({
          query: text,
          active_file: activeFile,
          history,
        });
        setMessages((prev) =>
          prev.map((m) =>
            m.id === pendingMsg.id
              ? {
                  ...m,
                  pending: false,
                  content: resp.answer,
                  toolCalls: resp.tool_calls,
                  iterations: resp.iterations,
                }
              : m,
          ),
        );
      } catch (err) {
        const detail = err instanceof Error ? err.message : "Unknown error.";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === pendingMsg.id
              ? {
                  ...m,
                  pending: false,
                  content: `**Error:** ${detail}`,
                  errored: true,
                }
              : m,
          ),
        );
      } finally {
        setBusy(false);
      }
    },
    [activeFile, busy, input, messages],
  );

  return (
    <div className="flex h-screen">
      <div className="hidden w-72 shrink-0 md:block">
        <DatasetSidebar
          activeFile={activeFile}
          onSelect={setActiveFile}
          onUploaded={handleUploaded}
          refreshKey={refreshKey}
        />
      </div>

      <div className="flex h-full flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-ink-200 bg-white px-4 py-3 md:px-6">
          <div className="text-sm font-semibold text-ink-800">Conversation</div>
          {activeFile && (
            <div className="text-xs text-ink-500">
              Active: <span className="font-mono text-ink-700">{activeFile}</span>
            </div>
          )}
        </header>

        <div ref={threadRef} className="flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <EmptyState
              hasActiveFile={!!activeFile}
              onSuggestion={(s) => void submit(s)}
            />
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-6">
              {messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}
            </div>
          )}
        </div>

        <ChatComposer
          value={input}
          onChange={setInput}
          onSubmit={() => void submit()}
          disabled={busy}
          activeFile={activeFile}
        />
      </div>
    </div>
  );
}
