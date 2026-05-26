"use client";

import { Database, Layers, MessageSquare } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { getConversation } from "@/lib/api";
import type {
  ChatMessage,
  PromptDescriptor,
  UiMessage,
  UploadResponse,
} from "@/lib/types";
import { useStreamingChat } from "@/hooks/useStreamingChat";

import ArtifactViewer from "./ArtifactViewer";
import ChatComposer from "./ChatComposer";
import ConversationSidebar from "./ConversationSidebar";
import DatasetSidebar from "./DatasetSidebar";
import EmptyState from "./EmptyState";
import HelpDialog from "./HelpDialog";
import MessageBubble from "./MessageBubble";

type RightPaneTab = "workspace" | "datasets";

export default function ChatInterface() {
  const [composerValue, setComposerValue] = useState("");
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [convListBust, setConvListBust] = useState(0);
  const [datasetBust, setDatasetBust] = useState(0);
  const [rightTab, setRightTab] = useState<RightPaneTab>("workspace");
  const [pinnedPrompt, setPinnedPrompt] = useState<PromptDescriptor | null>(null);
  const [promptArgs, setPromptArgs] = useState<Record<string, string>>({});

  const {
    messages, setMessages,
    busy, activeTool,
    conversationId, conversationTitle,
    artifacts, clearArtifacts,
    setConversationId, setConversationTitle,
    reset, send, abort,
  } = useStreamingChat();

  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll on new content
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, activeTool]);

  // First-visit help dialog
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!localStorage.getItem("unisole-onboarded")) {
      setHelpOpen(true);
      localStorage.setItem("unisole-onboarded", "1");
    }
  }, []);

  const handleSelectConversation = useCallback(
    async (id: string) => {
      if (id === conversationId) return;
      abort();
      try {
        const detail = await getConversation(id);
        setConversationId(detail.id);
        setConversationTitle(detail.title);
        setActiveFile(detail.active_file);
        clearArtifacts();
        const restored: UiMessage[] = detail.messages.map((m, i) => ({
          id: `${detail.id}-${i}`,
          role: m.role as "user" | "assistant",
          content: m.content,
          toolCalls: m.tool_calls || [],
          activeTool: null,
        }));
        setMessages(restored);
        setPinnedPrompt(null);
        setPromptArgs({});
      } catch (err) {
        alert(err instanceof Error ? err.message : "Failed to load conversation");
      }
    },
    [
      conversationId, abort, clearArtifacts, setMessages,
      setConversationId, setConversationTitle,
    ],
  );

  const handleNewConversation = useCallback(() => {
    abort();
    reset();
    setComposerValue("");
    setPinnedPrompt(null);
    setPromptArgs({});
  }, [abort, reset]);

  const handleUploaded = useCallback((resp: UploadResponse) => {
    setActiveFile(resp.filename);
    setDatasetBust((k) => k + 1);
  }, []);

  const handlePickPrompt = useCallback((p: PromptDescriptor) => {
    setPinnedPrompt(p);
    const initial: Record<string, string> = {};
    for (const a of p.arguments) {
      if (a.name === "file_path" && activeFile) initial[a.name] = activeFile;
      else initial[a.name] = "";
    }
    setPromptArgs(initial);
  }, [activeFile]);

  const handleSend = useCallback(() => {
    const text = composerValue.trim();
    if (!text && !pinnedPrompt) return;

    const history: ChatMessage[] = messages
      .filter((m) => !m.pending && !m.errored)
      .map((m) => ({ role: m.role, content: m.content }));

    let promptName: string | null = null;
    let promptArguments: Record<string, unknown> | null = null;
    let userQuery = text;

    if (pinnedPrompt) {
      promptName = pinnedPrompt.name;
      promptArguments = { ...promptArgs };
      if ("file_path" in promptArguments && !promptArguments.file_path && activeFile) {
        promptArguments.file_path = activeFile;
      }
      if (!userQuery) {
        userQuery = `Run /${pinnedPrompt.name}`;
      }
    }

    void send({
      query: userQuery,
      activeFile,
      conversationId,
      history,
      promptName,
      promptArguments,
    });

    setComposerValue("");
    setPinnedPrompt(null);
    setPromptArgs({});
    setConvListBust((k) => k + 1);
  }, [
    composerValue, pinnedPrompt, promptArgs, messages,
    activeFile, conversationId, send,
  ]);

  useEffect(() => {
    if (!busy && conversationId) {
      setConvListBust((k) => k + 1);
    }
  }, [busy, conversationId]);

  const hasMessages = messages.length > 0;
  const requiredArgs = pinnedPrompt
    ? pinnedPrompt.arguments.filter((a) => a.required)
    : [];
  const missingArgs = requiredArgs.filter(
    (a) => !promptArgs[a.name]?.trim() && !(a.name === "file_path" && activeFile),
  );

  return (
    <div className="grid h-screen w-screen grid-cols-[260px_minmax(0,1fr)_360px] grid-rows-1 bg-canvas-900 text-fg-100">
      <ConversationSidebar
        activeConversationId={conversationId}
        onSelect={handleSelectConversation}
        onNew={handleNewConversation}
        onOpenHelp={() => setHelpOpen(true)}
        refreshKey={convListBust}
      />

      <main className="flex min-w-0 flex-col">
        <header className="flex items-center justify-between border-b border-canvas-500 bg-canvas-900/60 px-5 py-2.5 backdrop-blur">
          <div className="flex min-w-0 items-center gap-2.5">
            <MessageSquare className="h-3.5 w-3.5 text-accent-400" />
            <div className="min-w-0">
              <div className="truncate text-[13px] font-semibold text-fg-50">
                {conversationTitle ?? "New conversation"}
              </div>
              {activeFile && (
                <div className="truncate font-mono text-[10px] text-fg-300">
                  Working on {activeFile}
                </div>
              )}
            </div>
          </div>
          {busy && (
            <button
              onClick={abort}
              className="rounded-md border border-status-error/30 bg-status-error/10 px-2.5 py-1 text-[11px] font-medium text-status-error hover:bg-status-error/20"
            >
              Stop generating
            </button>
          )}
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          {!hasMessages ? (
            <EmptyState
              onSuggestion={(t) => setComposerValue(t)}
              hasActiveFile={!!activeFile}
            />
          ) : (
            <div className="mx-auto max-w-3xl space-y-4 px-5 py-5">
              {messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}
            </div>
          )}
        </div>

        {pinnedPrompt && pinnedPrompt.arguments.length > 0 && (
          <div className="border-t border-canvas-500 bg-canvas-800/40 px-5 py-2">
            <div className="mx-auto max-w-3xl">
              <div className="mb-1.5 flex items-center gap-2 text-[11px]">
                <span className="font-semibold text-fg-50">Arguments for</span>
                <code className="font-mono text-accent-400">/{pinnedPrompt.name}</code>
                {missingArgs.length > 0 && (
                  <span className="ml-auto text-status-processing">
                    Fill {missingArgs.map((a) => a.name).join(", ")}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {pinnedPrompt.arguments.map((a) => (
                  <div key={a.name} className="flex flex-col gap-0.5">
                    <label className="text-[10px] font-mono text-fg-300">
                      {a.name}{a.required ? "*" : ""}
                    </label>
                    <input
                      value={promptArgs[a.name] ?? ""}
                      onChange={(e) =>
                        setPromptArgs((p) => ({ ...p, [a.name]: e.target.value }))
                      }
                      placeholder={
                        a.name === "file_path" && activeFile
                          ? activeFile
                          : a.description ?? a.name
                      }
                      className="rounded-md border border-canvas-500 bg-canvas-900 px-2 py-1 text-[12px] text-fg-50 placeholder:text-fg-300 focus:border-accent-500/60 focus:outline-none"
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <ChatComposer
          value={composerValue}
          onChange={setComposerValue}
          onSubmit={handleSend}
          disabled={busy || missingArgs.length > 0}
          activeFile={activeFile}
          pinnedPrompt={pinnedPrompt}
          onClearPrompt={() => {
            setPinnedPrompt(null);
            setPromptArgs({});
          }}
          onPickPrompt={handlePickPrompt}
        />
      </main>

      <aside className="flex min-w-0 flex-col border-l border-canvas-500">
        <div className="flex items-center border-b border-canvas-500 bg-canvas-900/40">
          <button
            onClick={() => setRightTab("workspace")}
            className={[
              "flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-[11px] font-medium transition",
              rightTab === "workspace"
                ? "border-b-2 border-accent-500 text-fg-50"
                : "border-b-2 border-transparent text-fg-300 hover:text-fg-100",
            ].join(" ")}
          >
            <Layers className="h-3 w-3" />
            Workspace
            {artifacts.length > 0 && (
              <span className="rounded bg-canvas-700 px-1.5 py-0.5 font-mono text-[9px] text-fg-200">
                {artifacts.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setRightTab("datasets")}
            className={[
              "flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-[11px] font-medium transition",
              rightTab === "datasets"
                ? "border-b-2 border-accent-500 text-fg-50"
                : "border-b-2 border-transparent text-fg-300 hover:text-fg-100",
            ].join(" ")}
          >
            <Database className="h-3 w-3" />
            Datasets
          </button>
        </div>

        <div className="min-h-0 flex-1">
          {rightTab === "workspace" ? (
            <ArtifactViewer artifacts={artifacts} onClear={clearArtifacts} />
          ) : (
            <DatasetSidebar
              activeFile={activeFile}
              onSelect={setActiveFile}
              onUploaded={handleUploaded}
              refreshKey={datasetBust}
            />
          )}
        </div>
      </aside>

      <HelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}