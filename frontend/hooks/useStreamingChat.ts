"use client";

import { useCallback, useRef, useState } from "react";

import { openChatStream } from "@/lib/streamingClient";
import type {
  ActiveToolBadge,
  ChatMessage,
  StreamEvent,
  ToolCallRecord,
  UiMessage,
  WorkspaceArtifact,
} from "@/lib/types";
import { API_BASE_URL } from "@/lib/api";

function uid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

interface SendArgs {
  query: string;
  activeFile: string | null;
  conversationId: string | null;
  history: ChatMessage[];
  promptName?: string | null;
  promptArguments?: Record<string, unknown> | null;
}

interface UseStreamingChatResult {
  messages: UiMessage[];
  setMessages: React.Dispatch<React.SetStateAction<UiMessage[]>>;
  busy: boolean;
  activeTool: ActiveToolBadge | null;
  conversationId: string | null;
  conversationTitle: string | null;
  artifacts: WorkspaceArtifact[];
  pushArtifact: (a: WorkspaceArtifact) => void;
  clearArtifacts: () => void;
  setConversationId: (id: string | null) => void;
  setConversationTitle: (t: string | null) => void;
  reset: () => void;
  send: (args: SendArgs) => Promise<void>;
  abort: () => void;
}

function absUrl(rel: string): string {
  if (/^https?:\/\//.test(rel)) return rel;
  if (rel.startsWith("/")) return `${API_BASE_URL}${rel}`;
  return rel;
}

function extractArtifacts(
  tool: ToolCallRecord,
  prev: WorkspaceArtifact[],
): WorkspaceArtifact[] {
  const newOnes: WorkspaceArtifact[] = [];
  const visit = (val: unknown): void => {
    if (val == null) return;
    if (Array.isArray(val)) {
      val.forEach(visit);
      return;
    }
    if (typeof val !== "object") return;
    const obj = val as Record<string, unknown>;

    const push = (kind: WorkspaceArtifact["kind"], url: string, titleHint?: string) => {
      const absolute = absUrl(url);
      if (prev.some((a) => a.url === absolute)) return;
      if (newOnes.some((a) => a.url === absolute)) return;
      newOnes.push({
        id: uid(),
        kind,
        title: titleHint || absolute.split("/").pop() || absolute,
        url: absolute,
        source_tool: tool.name,
        source_service: tool.service ?? undefined,
        created_at: Date.now(),
      });
    };

    if (typeof obj.plot_url === "string") push("image", obj.plot_url);
    if (typeof obj.report_url === "string") push("report", obj.report_url);
    if (typeof obj.notebook_url === "string") push("file", obj.notebook_url);
    if (typeof obj.pdf_url === "string") push("file", obj.pdf_url);
    if (typeof obj.download_url === "string" && !obj.notebook_url && !obj.pdf_url) {
      push("file", obj.download_url);
    }

    // Tabular: head_rows + columns
    if (Array.isArray(obj.head_rows) && Array.isArray(obj.columns)) {
      newOnes.push({
        id: uid(),
        kind: "table",
        title: typeof obj.file === "string" ? `Preview — ${obj.file}` : "Data preview",
        url: "",
        source_tool: tool.name,
        source_service: tool.service ?? undefined,
        created_at: Date.now(),
        table: {
          columns: obj.columns as string[],
          rows: obj.head_rows as Record<string, unknown>[],
        },
      });
    }

    // Leaderboard tables
    if (Array.isArray(obj.leaderboard) && obj.leaderboard.length > 0) {
      const lb = obj.leaderboard as Record<string, unknown>[];
      const cols = ["model", "cv_mean", "cv_std", "train_seconds", "error"];
      newOnes.push({
        id: uid(),
        kind: "table",
        title: "Leaderboard",
        url: "",
        source_tool: tool.name,
        source_service: tool.service ?? undefined,
        created_at: Date.now(),
        table: { columns: cols, rows: lb },
      });
    }

    // Recurse
    for (const v of Object.values(obj)) {
      if (v && typeof v === "object") visit(v);
    }
  };
  visit(tool.result);
  return newOnes;
}

export function useStreamingChat(): UseStreamingChatResult {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [activeTool, setActiveTool] = useState<ActiveToolBadge | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<WorkspaceArtifact[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const pushArtifact = useCallback((a: WorkspaceArtifact) => {
    setArtifacts((prev) => [a, ...prev]);
  }, []);

  const clearArtifacts = useCallback(() => setArtifacts([]), []);

  const reset = useCallback(() => {
    setMessages([]);
    setActiveTool(null);
    setConversationId(null);
    setConversationTitle(null);
    setArtifacts([]);
  }, []);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setActiveTool(null);
  }, []);

  const send = useCallback(
    async ({ query, activeFile, conversationId: cid, history, promptName, promptArguments }: SendArgs) => {
      const userMsg: UiMessage = { id: uid(), role: "user", content: query };
      const pendingId = uid();
      const pendingMsg: UiMessage = {
        id: pendingId, role: "assistant", content: "",
        pending: true, toolCalls: [], activeTool: null,
      };
      setMessages((prev) => [...prev, userMsg, pendingMsg]);
      setBusy(true);
      setActiveTool(null);

      const controller = new AbortController();
      abortRef.current = controller;

      const updatePending = (mutator: (msg: UiMessage) => UiMessage) => {
        setMessages((prev) => prev.map((m) => (m.id === pendingId ? mutator(m) : m)));
      };

      try {
        const stream = openChatStream(
          {
            query,
            active_file: activeFile,
            conversation_id: cid,
            history,
            prompt_name: promptName ?? null,
            prompt_arguments: promptArguments ?? null,
          },
          controller.signal,
        );

        for await (const evt of stream as AsyncGenerator<StreamEvent>) {
          switch (evt.type) {
            case "meta": {
              setConversationId(evt.conversation_id);
              setConversationTitle(evt.title);
              break;
            }
            case "token": {
              updatePending((m) => ({
                ...m, content: m.content + evt.content, pending: true,
              }));
              break;
            }
            case "tool_start": {
              const badge: ActiveToolBadge = {
                name: evt.name,
                service: evt.service,
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
                service: evt.service ?? null,
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
              // Extract artifacts into the workspace
              setArtifacts((prev) => {
                const found = extractArtifacts(record, prev);
                return found.length ? [...found, ...prev] : prev;
              });
              break;
            }
            case "done": {
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
            // service_status events handled by useServiceNetwork
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
    artifacts,
    pushArtifact,
    clearArtifacts,
    setConversationId,
    setConversationTitle,
    reset,
    send,
    abort,
  };
}