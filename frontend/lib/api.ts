import { getSupabaseBrowserClient } from "./supabase";
import type {
  ConversationDetail,
  ConversationList,
  DatasetListResponse,
  ServicesSnapshot,
  UploadResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
export const API_BASE_URL = API_BASE;

// ── Auth helper ────────────────────────────────────────────────────
async function getAccessToken(): Promise<string | null> {
  const supabase = getSupabaseBrowserClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

function redirectToLogin(): never {
  if (typeof window !== "undefined") {
    const here = window.location.pathname + window.location.search;
    window.location.href = `/login?next=${encodeURIComponent(here)}`;
  }
  throw new Error("Unauthorized");
}

/** Attach Authorization: Bearer <jwt> to every backend call. 401 → /login. */
export async function authedFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = await getAccessToken();
  if (!token) redirectToLogin();

  const headers = new Headers(init.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  // Don't set Content-Type for FormData (browser sets multipart boundary)
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const res = await fetch(url, { ...init, headers });
  if (res.status === 401) redirectToLogin();
  return res;
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

// ── Datasets / uploads ────────────────────────────────────────────
export async function uploadCsv(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await authedFetch("/api/upload", { method: "POST", body: form });
  return handle<UploadResponse>(res);
}

export async function listDatasets(): Promise<DatasetListResponse> {
  const res = await authedFetch("/api/datasets", { cache: "no-store" });
  return handle<DatasetListResponse>(res);
}

// ── Conversations ─────────────────────────────────────────────────
export async function listConversations(): Promise<ConversationList> {
  const res = await authedFetch("/api/conversations", { cache: "no-store" });
  return handle<ConversationList>(res);
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await authedFetch(`/api/conversations/${id}/messages`, {
    cache: "no-store",
  });
  return handle<ConversationDetail>(res);
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await authedFetch(`/api/conversations/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`Delete failed: ${res.status}`);
  }
}

// ── Service network ──────────────────────────────────────────────
export async function fetchServicesSnapshot(): Promise<ServicesSnapshot> {
  const res = await authedFetch("/api/services", { cache: "no-store" });
  return handle<ServicesSnapshot>(res);
}

export async function refreshServices(): Promise<ServicesSnapshot> {
  const res = await authedFetch("/api/services/refresh", { method: "POST" });
  return handle<ServicesSnapshot>(res);
}

export function servicesStreamUrl(): string {
  return `${API_BASE}/api/services/stream`;
}

// ── Prompts ──────────────────────────────────────────────────────
export interface PromptListResponse {
  prompts: {
    name: string;
    description: string;
    service: string;
    arguments: { name: string; description?: string; required: boolean }[];
  }[];
}

export async function listPrompts(): Promise<PromptListResponse> {
  const res = await authedFetch("/api/prompts", { cache: "no-store" });
  return handle<PromptListResponse>(res);
}

// ── Chat stream ──────────────────────────────────────────────────
export function chatStreamUrl(): string {
  return `${API_BASE}/api/chat`;
}

// ── Artifacts ────────────────────────────────────────────────────
export async function getArtifactSignedUrl(
  artifactId: string,
): Promise<{ url: string; ttl_seconds: number }> {
  const res = await authedFetch(`/api/artifacts/${artifactId}/url`, {
    cache: "no-store",
  });
  return handle<{ url: string; ttl_seconds: number }>(res);
}

// ── Legacy filename-based helpers (kept for ToolCallCard backwards compat) ─
// These are no-ops in the new Supabase world but legacy components may still
// reference them; have them return safe placeholder URLs.
export function staticOutputUrl(filename: string): string {
  return `${API_BASE}/api/_legacy_unavailable/${encodeURIComponent(filename)}`;
}
export function staticReportUrl(filename: string): string {
  return staticOutputUrl(filename);
}
export function staticPlotUrl(filename: string): string {
  return staticOutputUrl(filename);
}
export function downloadUrl(filename: string): string {
  return staticOutputUrl(filename);
}