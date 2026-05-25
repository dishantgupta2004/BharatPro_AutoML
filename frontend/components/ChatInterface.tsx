"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getConversation } from "@/lib/api";
import type {
  ChatMessage,
  UiMessage,
  UploadResponse,
} from "@/lib/types";

import ChatComposer from "./ChatComposer";
import ConversationSidebar from "./ConversationSidebar";
import DatasetSidebar from "./DatasetSidebar";
import EmptyState from "./EmptyState";
import MessageBubble from "./MessageBubble";
import { useStreamingChat } from "@/hooks/useStreamingChat";

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function ChatInterface() {
  const {
    messages,
    setMessages,
    busy,
    activeTool,
    conversationId,
    conversationTitle,
    setConversationId,
    setConversationTitle,
    reset,
    send,
    abort,
  } = useStreamingChat();

  const [input, setInput] = useState("");
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [datasetRefreshKey, setDatasetRefreshKey] = useState(0);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  const threadRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, busy, activeTool]);

  const handleUploaded = useCallback(
    (resp: UploadResponse) => {
      setActiveFile(resp.filename);
      setDatasetRefreshKey((k) => k + 1);
      const note: UiMessage = {
        id: uid(),
        role: "assistant",
        content: `Uploaded **${resp.filename}** (${resp.rows.toLocaleString()} rows × ${resp.columns} columns). Selected as active dataset.\n\nColumns: ${resp.column_names
          .slice(0, 12)
          .map((c) => `\`${c}\``)
          .join(", ")}${resp.column_names.length > 12 ? "…" : ""}`,
      };
      setMessages((prev) => [...prev, note]);
    },
    [setMessages],
  );

  const handleSelectConversation = useCallback(
    async (id: string) => {
      if (id === conversationId) return;
      try {
        const detail = await getConversation(id);
        setConversationId(detail.id);
        setConversationTitle(detail.title);
        setActiveFile(detail.active_file);
        setMessages(
          detail.messages.map((m) => ({
            id: m.id,
            role: m.role === "user" ? "user" : "assistant",
            content: m.content,
            toolCalls: m.tool_calls || undefined,
          })),
        );
      } catch (err) {
        alert(err instanceof Error ? err.message : "Failed to load conversation.");
      }
    },
    [conversationId, setConversationId, setConversationTitle, setMessages],
  );

  const handleNewConversation = useCallback(() => {
    reset();
    setInput("");
  }, [reset]);

  const submit = useCallback(
    async (overrideText?: string) => {
      const text = (overrideText ?? input).trim();
      if (!text || busy) return;
      setInput("");

      const history: ChatMessage[] = messages
        .filter((m) => !m.pending && !m.errored && m.content)
        .map((m) => ({ role: m.role, content: m.content }));

      await send({
        query: text,
        activeFile,
        conversationId,
        history,
      });
      setHistoryRefreshKey((k) => k + 1);
    },
    [activeFile, busy, conversationId, input, messages, send],
  );

  return (
    <div className="flex h-screen">
      <div className="hidden w-64 shrink-0 lg:block">
        <ConversationSidebar
          activeConversationId={conversationId}
          onSelect={(id) => void handleSelectConversation(id)}
          onNew={handleNewConversation}
          refreshKey={historyRefreshKey}
        />
      </div>

      <div className="hidden w-72 shrink-0 md:block">
        <DatasetSidebar
          activeFile={activeFile}
          onSelect={setActiveFile}
          onUploaded={handleUploaded}
          refreshKey={datasetRefreshKey}
        />
      </div>

      <div className="flex h-full flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-ink-200 bg-white px-4 py-3 md:px-6">
          <div className="min-w-0 truncate text-sm font-semibold text-ink-800">
            {conversationTitle || "New conversation"}
          </div>
          <div className="flex items-center gap-3 text-xs text-ink-500">
            {activeFile && (
              <span>
                Active: <span className="font-mono text-ink-700">{activeFile}</span>
              </span>
            )}
            {busy && (
              <button
                onClick={abort}
                className="rounded-md border border-ink-200 px-2 py-1 text-ink-700 hover:bg-ink-100"
              >
                Stop
              </button>
            )}
          </div>
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