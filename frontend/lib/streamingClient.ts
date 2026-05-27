import type { StreamEvent } from "./types";
import { authedFetch, chatStreamUrl } from "./api";

export interface ChatStreamPayload {
  query: string;
  active_file: string | null;
  conversation_id: string | null;
  history: { role: "user" | "assistant"; content: string }[];
  prompt_name?: string | null;
  prompt_arguments?: Record<string, unknown> | null;
}

export async function* openChatStream(
  payload: ChatStreamPayload,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent, void, unknown> {
  // EventSource can't send headers; use fetch + ReadableStream so we can
  // attach Authorization: Bearer <jwt> via authedFetch.
  const res = await authedFetch(chatStreamUrl(), {
    method: "POST",
    headers: { Accept: "text/event-stream" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let separator = buffer.indexOf("\n\n");
      while (separator !== -1) {
        const rawFrame = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        separator = buffer.indexOf("\n\n");

        const dataLines = rawFrame
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).replace(/^ /, ""));
        if (dataLines.length === 0) continue;

        const dataStr = dataLines.join("\n");
        try {
          yield JSON.parse(dataStr) as StreamEvent;
        } catch (err) {
          console.warn("Failed to parse SSE frame", err, dataStr);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}