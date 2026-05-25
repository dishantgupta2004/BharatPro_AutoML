"use client";

import { MessageSquare, Plus, RotateCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  deleteConversation as apiDeleteConversation,
  listConversations,
} from "@/lib/api";
import type { ConversationSummary } from "@/lib/types";

interface Props {
  activeConversationId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  refreshKey: number;
}

export default function ConversationSidebar({
  activeConversationId,
  onSelect,
  onNew,
  refreshKey,
}: Props) {
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await listConversations();
      setItems(resp.conversations);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Delete this conversation?")) return;
    try {
      await apiDeleteConversation(id);
      void refresh();
      if (id === activeConversationId) onNew();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <aside className="flex h-full w-full flex-col border-r border-ink-200 bg-white">
      <div className="flex items-center justify-between px-3 py-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-ink-500">
          History
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => void refresh()}
            className="rounded-md p-1.5 text-ink-500 hover:bg-ink-100"
            title="Refresh"
          >
            <RotateCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={onNew}
            className="flex items-center gap-1 rounded-md bg-brand-600 px-2 py-1 text-xs font-medium text-white hover:bg-brand-700"
            title="New conversation"
          >
            <Plus className="h-3.5 w-3.5" /> New
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3">
        {error && (
          <div className="m-2 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700">
            {error}
          </div>
        )}
        {!error && items.length === 0 && !loading && (
          <div className="mx-2 mt-2 rounded-md border border-dashed border-ink-200 p-3 text-xs text-ink-500">
            No conversations yet. Start chatting to create one.
          </div>
        )}

        <ul className="space-y-0.5">
          {items.map((c) => {
            const isActive = c.id === activeConversationId;
            return (
              <li key={c.id}>
                <button
                  onClick={() => onSelect(c.id)}
                  className={[
                    "group flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left transition",
                    isActive
                      ? "bg-brand-50 text-brand-700 ring-1 ring-brand-200"
                      : "text-ink-700 hover:bg-ink-100",
                  ].join(" ")}
                >
                  <MessageSquare
                    className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${
                      isActive ? "text-brand-600" : "text-ink-400"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{c.title}</div>
                    {c.active_file && (
                      <div className="truncate text-[11px] text-ink-500">
                        {c.active_file}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={(e) => void handleDelete(c.id, e)}
                    className="invisible rounded p-1 text-ink-400 hover:bg-red-50 hover:text-red-600 group-hover:visible"
                    title="Delete"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}