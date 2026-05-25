import type {
  ChatMessage,
  ChatResponse,
  DatasetListResponse,
  UploadResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export const API_BASE_URL = API_BASE;

export function staticOutputUrl(filename: string): string {
  return `${API_BASE}/static/outputs/${encodeURIComponent(filename)}`;
}

export function downloadUrl(filename: string): string {
  return `${API_BASE}/api/download/${encodeURIComponent(filename)}`;
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* swallow */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function uploadCsv(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: form,
  });
  return handle<UploadResponse>(res);
}

export async function listDatasets(): Promise<DatasetListResponse> {
  const res = await fetch(`${API_BASE}/api/datasets`, { cache: "no-store" });
  return handle<DatasetListResponse>(res);
}

export interface ChatRequest {
  query: string;
  active_file: string | null;
  history: ChatMessage[];
}

export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return handle<ChatResponse>(res);
}
