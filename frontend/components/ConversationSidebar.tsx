"use client";

import { LifeBuoy, LogOut, MessageSquare, Plus, RotateCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  deleteConversation as apiDeleteConversation,
  listConversations,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { ConversationSummary } from "@/lib/types";

import ServiceStatusPanel from "./ServiceStatusPanel";

interface Props {
  activeConversationId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onOpenHelp: () => void;
  refreshKey: number;
}

export default function ConversationSidebar({
  activeConversationId,
  onSelect,
  onNew,
  onOpenHelp,
  refreshKey,
}: Props) {
  const { user, signOut } = useAuth();
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
    <aside className="flex h-full w-full flex-col border-r border-canvas-500 bg-canvas-800/40">
      {/* Brand + user */}
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-center gap-2.5">
          <img
            src="/nsk_logo.png"
            alt="NSK AI Labs"
            className="h-8 w-8 rounded-lg object-contain"
          />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-fg-50">
              BharatPro AutoML
            </div>
            <div className="truncate text-[10px] uppercase tracking-wider text-fg-300">
              NSK AI Labs
            </div>
          </div>
        </div>
        {user?.email && (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-canvas-500 bg-canvas-900/60 px-2 py-1.5">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-accent-500/20 font-mono text-[10px] font-bold text-accent-400">
              {user.email.charAt(0).toUpperCase()}
            </div>
            <span className="min-w-0 flex-1 truncate text-[11px] text-fg-100" title={user.email}>
              {user.email}
            </span>
            <button
              onClick={() => void signOut()}
              className="rounded p-1 text-fg-300 hover:bg-canvas-700 hover:text-status-error"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>

      <div className="mx-3 h-px divider-y" />

      {/* History */}
      <div className="flex items-center justify-between px-3 pt-3 pb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-fg-300">
          History
        </span>
        <div className="flex gap-1">
          <button
            onClick={() => void refresh()}
            className="rounded-md p-1 text-fg-300 hover:bg-canvas-600 hover:text-fg-100"
            title="Refresh"
          >
            <RotateCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={onNew}
            className="flex items-center gap-1 rounded-md bg-accent-600 px-2 py-1 text-[11px] font-medium text-white shadow-glow transition hover:bg-accent-500"
            title="New conversation"
          >
            <Plus className="h-3 w-3" />
            New
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3">
        {error && (
          <div className="m-2 rounded-md border border-status-error/30 bg-status-error/10 p-2 text-[11px] text-status-error">
            {error}
          </div>
        )}
        {!error && items.length === 0 && !loading && (
          <div className="mx-2 mt-1 rounded-md border border-dashed border-canvas-500 p-3 text-[11px] text-fg-300">
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
                      ? "bg-accent-500/10 text-fg-50 ring-1 ring-accent-500/30"
                      : "text-fg-100 hover:bg-canvas-700",
                  ].join(" ")}
                >
                  <MessageSquare
                    className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${
                      isActive ? "text-accent-400" : "text-fg-300"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-medium">{c.title}</div>
                    {c.active_file && (
                      <div className="truncate font-mono text-[10px] text-fg-300">
                        {c.active_file}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={(e) => void handleDelete(c.id, e)}
                    className="invisible rounded p-1 text-fg-300 hover:bg-status-error/10 hover:text-status-error group-hover:visible"
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

      <div className="px-3 pb-3">
        <ServiceStatusPanel />
      </div>

      <div className="border-t border-canvas-500 px-3 py-2.5">
        <button
          onClick={onOpenHelp}
          className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[12px] text-fg-200 transition hover:bg-canvas-700 hover:text-fg-50"
        >
          <LifeBuoy className="h-3.5 w-3.5 text-accent-400" />
          Help & Support
        </button>
      </div>
    </aside>
  );
}