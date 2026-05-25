import type {
  ConversationDetail,
  ConversationList,
  DatasetListResponse,
  UploadResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
export const API_BASE_URL = API_BASE;

export function staticOutputUrl(filename: string): string {
  return `${API_BASE}/static/outputs/${encodeURIComponent(filename)}`;
}
export function staticReportUrl(filename: string): string {
  return `${API_BASE}/static/reports/${encodeURIComponent(filename)}`;
}
export function staticPlotUrl(filename: string): string {
  return `${API_BASE}/static/plots/${encodeURIComponent(filename)}`;
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
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function uploadCsv(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: form });
  return handle<UploadResponse>(res);
}

export async function listDatasets(): Promise<DatasetListResponse> {
  const res = await fetch(`${API_BASE}/api/datasets`, { cache: "no-store" });
  return handle<DatasetListResponse>(res);
}

export async function listConversations(): Promise<ConversationList> {
  const res = await fetch(`${API_BASE}/api/conversations`, { cache: "no-store" });
  return handle<ConversationList>(res);
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}/messages`, {
    cache: "no-store",
  });
  return handle<ConversationDetail>(res);
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Delete failed: ${res.status}`);
  }
}

export function chatStreamUrl(): string {
  return `${API_BASE}/api/chat`;
}