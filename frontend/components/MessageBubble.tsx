"use client";

import { Bot, Loader2, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { API_BASE_URL } from "@/lib/api";
import type { UiMessage } from "@/lib/types";

import ToolCallCard from "./ToolCallCard";
import ToolProgressBanner from "./ToolProgressBanner";

interface Props {
  message: UiMessage;
}

// Rewrite relative /static/... URLs so images and links work cross-origin
function rewriteUrl(url: string): string {
  if (url.startsWith("/static/")) return `${API_BASE_URL}${url}`;
  return url;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      <div
        className={[
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-ink-900 text-white" : "bg-brand-600 text-white",
        ].join(" ")}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      <div
        className={[
          "max-w-[78%] rounded-2xl px-4 py-3 text-sm shadow-soft",
          isUser
            ? "rounded-tr-sm bg-brand-600 text-white"
            : "rounded-tl-sm bg-white text-ink-900 ring-1 ring-ink-200",
        ].join(" ")}
      >
        {message.pending && !message.content && !message.activeTool && (
          <div className="flex items-center gap-2 text-ink-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Thinking…</span>
          </div>
        )}

        {!isUser && message.activeTool && (
          <div className="mb-2">
            <ToolProgressBanner badge={message.activeTool} />
          </div>
        )}

        {message.content &&
          (isUser ? (
            <div className="whitespace-pre-wrap">{message.content}</div>
          ) : (
            <div className="prose-tight">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                urlTransform={rewriteUrl}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          ))}

        {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mt-3 space-y-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
              Tool calls ({message.toolCalls.length})
            </div>
            {message.toolCalls.map((c, i) => (
              <ToolCallCard key={`${message.id}-tc-${i}`} call={c} index={i} />
            ))}
          </div>
        )}

        {message.errored && (
          <div className="mt-2 text-xs text-red-600">
            Something went wrong with this response.
          </div>
        )}
      </div>
    </div>
  );
}