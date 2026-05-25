export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface ToolCallRecord {
  name: string;
  arguments: Record<string, unknown>;
  result: unknown;
  error: string | null;
  duration_ms: number;
}

export interface ChatResponse {
  answer: string;
  tool_calls: ToolCallRecord[];
  iterations: number;
}

export interface UploadResponse {
  filename: string;
  size_bytes: number;
  rows: number;
  columns: number;
  column_names: string[];
}

export interface DatasetItem {
  filename: string;
  size_kb: number;
  modified_unix: number;
}

export interface DatasetListResponse {
  count: number;
  files: DatasetItem[];
}

export interface UiMessage {
  id: string;
  role: ChatRole;
  content: string;
  toolCalls?: ToolCallRecord[];
  iterations?: number;
  pending?: boolean;
  errored?: boolean;
}
