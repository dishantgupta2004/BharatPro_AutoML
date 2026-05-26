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
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg shadow-ring",
          isUser
            ? "bg-canvas-700 text-fg-100"
            : "bg-gradient-to-br from-accent-500 to-accent-700 text-white",
        ].join(" ")}
      >
        {isUser ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
      </div>

      <div
        className={[
          "max-w-[82%] rounded-2xl px-4 py-2.5 text-[13.5px] leading-relaxed shadow-elevate",
          isUser
            ? "rounded-tr-md bg-accent-600 text-white"
            : "rounded-tl-md bg-canvas-800 text-fg-100 ring-1 ring-canvas-500",
        ].join(" ")}
      >
        {message.pending && !message.content && !message.activeTool && (
          <div className="flex items-center gap-2 text-fg-300">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
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
            <div className="prose-dark">
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
            <div className="text-[10px] font-semibold uppercase tracking-wider text-fg-300">
              Tool calls ({message.toolCalls.length})
            </div>
            {message.toolCalls.map((c, i) => (
              <ToolCallCard key={`${message.id}-tc-${i}`} call={c} index={i} />
            ))}
          </div>
        )}

        {message.errored && (
          <div className="mt-2 text-xs text-status-error">
            Something went wrong with this response.
          </div>
        )}
      </div>
    </div>
  );
}