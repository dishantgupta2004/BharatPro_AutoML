"use client";

import { useCallback, useRef, useState } from "react";

import { openChatStream } from "@/lib/streamingClient";
import type {
  ActiveToolBadge,
  ChatMessage,
  StreamEvent,
  ToolCallRecord,
  UiMessage,
} from "@/lib/types";

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

interface SendArgs {
  query: string;
  activeFile: string | null;
  conversationId: string | null;
  history: ChatMessage[];
}

interface UseStreamingChatResult {
  messages: UiMessage[];
  setMessages: React.Dispatch<React.SetStateAction<UiMessage[]>>;
  busy: boolean;
  activeTool: ActiveToolBadge | null;
  conversationId: string | null;
  conversationTitle: string | null;
  setConversationId: (id: string | null) => void;
  setConversationTitle: (t: string | null) => void;
  reset: () => void;
  send: (args: SendArgs) => Promise<{
    conversationId: string | null;
    answer: string;
    toolCalls: ToolCallRecord[];
  }>;
  abort: () => void;
}

export function useStreamingChat(): UseStreamingChatResult {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [activeTool, setActiveTool] = useState<ActiveToolBadge | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    setMessages([]);
    setActiveTool(null);
    setConversationId(null);
    setConversationTitle(null);
  }, []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setActiveTool(null);
  }, []);

  const send = useCallback(
    async ({ query, activeFile, conversationId: cid, history }: SendArgs) => {
      const userMsg: UiMessage = { id: uid(), role: "user", content: query };
      const pendingId = uid();
      const pendingMsg: UiMessage = {
        id: pendingId,
        role: "assistant",
        content: "",
        pending: true,
        toolCalls: [],
        activeTool: null,
      };
      setMessages((prev) => [...prev, userMsg, pendingMsg]);
      setBusy(true);
      setActiveTool(null);

      const controller = new AbortController();
      abortRef.current = controller;

      let resolvedConversationId = cid;
      let finalAnswer = "";
      let finalToolCalls: ToolCallRecord[] = [];

      const updatePending = (mutator: (msg: UiMessage) => UiMessage) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === pendingId ? mutator(m) : m)),
        );
      };

      try {
        const stream = openChatStream(
          {
            query,
            active_file: activeFile,
            conversation_id: cid,
            history,
          },
          controller.signal,
        );

        for await (const evt of stream as AsyncGenerator<StreamEvent>) {
          switch (evt.type) {
            case "meta": {
              resolvedConversationId = evt.conversation_id;
              setConversationId(evt.conversation_id);
              setConversationTitle(evt.title);
              break;
            }
            case "token": {
              updatePending((m) => ({
                ...m,
                content: m.content + evt.content,
                pending: true,
              }));
              break;
            }
            case "tool_start": {
              const badge: ActiveToolBadge = {
                name: evt.name,
                message: `Calling ${evt.name}…`,
                percentage: 0,
                started_at: Date.now(),
              };
              setActiveTool(badge);
              updatePending((m) => ({ ...m, activeTool: badge }));
              break;
            }
            case "tool_progress": {
              setActiveTool((prev) =>
                prev
                  ? {
                      ...prev,
                      message: evt.message,
                      percentage: evt.percentage >= 0 ? evt.percentage : prev.percentage,
                    }
                  : prev,
              );
              updatePending((m) =>
                m.activeTool
                  ? {
                      ...m,
                      activeTool: {
                        ...m.activeTool,
                        message: evt.message,
                        percentage:
                          evt.percentage >= 0 ? evt.percentage : m.activeTool.percentage,
                      },
                    }
                  : m,
              );
              break;
            }
            case "tool_end": {
              let parsedResult: unknown = evt.result;
              try {
                parsedResult = JSON.parse(evt.result);
              } catch {}
              const record: ToolCallRecord = {
                name: evt.name,
                arguments: {},
                result: parsedResult,
                error: evt.error,
                duration_ms: evt.duration_ms,
              };
              setActiveTool(null);
              updatePending((m) => ({
                ...m,
                activeTool: null,
                toolCalls: [...(m.toolCalls ?? []), record],
              }));
              break;
            }
            case "done": {
              finalAnswer = evt.answer;
              finalToolCalls = evt.tool_calls;
              updatePending((m) => ({
                ...m,
                pending: false,
                activeTool: null,
                content: evt.answer || m.content,
                toolCalls:
                  evt.tool_calls && evt.tool_calls.length > 0
                    ? evt.tool_calls
                    : m.toolCalls,
              }));
              break;
            }
            case "error": {
              updatePending((m) => ({
                ...m,
                pending: false,
                activeTool: null,
                errored: true,
                content: `**Error:** ${evt.message}`,
              }));
              break;
            }
          }
        }
      } catch (err) {
        const detail = err instanceof Error ? err.message : String(err);
        updatePending((m) => ({
          ...m,
          pending: false,
          activeTool: null,
          errored: true,
          content: `**Error:** ${detail}`,
        }));
      } finally {
        setBusy(false);
        setActiveTool(null);
        abortRef.current = null;
      }

      return {
        conversationId: resolvedConversationId,
        answer: finalAnswer,
        toolCalls: finalToolCalls,
      };
    },
    [],
  );

  return {
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
  };
}