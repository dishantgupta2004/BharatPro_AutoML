export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface ToolCallRecord {
  name: string;
  service?: string | null;
  arguments: Record<string, unknown>;
  result: unknown;
  error: string | null;
  duration_ms: number;
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

// ---- Service network ----
export type ServiceStatus = "online" | "offline" | "processing" | "error";

export interface ServiceState {
  name: string;
  url: string;
  status: ServiceStatus;
  last_error: string | null;
  last_seen: number;
  tools: string[];
  resources: string[];
  prompts: string[];
}

export interface ServicesSnapshot {
  services: ServiceState[];
  tool_count: number;
  resource_count: number;
  prompt_count: number;
  prompts: PromptDescriptor[];
}

export interface PromptDescriptor {
  name: string;
  description: string;
  service: string;
  arguments: { name: string; description?: string; required: boolean }[];
}

// ---- SSE event union ----
export type StreamEvent =
  | { type: "meta"; conversation_id: string; title: string; prompt_name?: string | null }
  | { type: "token"; content: string }
  | {
      type: "tool_start";
      name: string;
      service?: string;
      arguments: Record<string, unknown>;
    }
  | { type: "tool_progress"; message: string; percentage: number }
  | {
      type: "tool_end";
      name: string;
      service?: string;
      result: string;
      error: string | null;
      duration_ms: number;
    }
  | { type: "done"; answer: string; tool_calls: ToolCallRecord[] }
  | { type: "error"; message: string }
  | {
      type: "service_status";
      service: { name: string; status: ServiceStatus; last_error?: string | null };
    };

export interface ActiveToolBadge {
  name: string;
  service?: string;
  message: string;
  percentage: number;
  started_at: number;
}

export interface UiMessage {
  id: string;
  role: ChatRole;
  content: string;
  toolCalls?: ToolCallRecord[];
  activeTool?: ActiveToolBadge | null;
  pending?: boolean;
  errored?: boolean;
}

export interface ConversationSummary {
  id: string;
  title: string;
  active_file: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationList {
  conversations: ConversationSummary[];
}

export interface ConversationDetail {
  id: string;
  title: string;
  active_file: string | null;
  messages: {
    id: string;
    role: string;
    content: string;
    tool_calls: ToolCallRecord[] | null;
    created_at: string;
  }[];
}

// ---- Workspace artifact tabs ----
export type ArtifactKind = "image" | "report" | "table" | "file" | "model";

export interface WorkspaceArtifact {
  id: string;
  kind: ArtifactKind;
  title: string;
  url: string;
  source_tool?: string;
  source_service?: string;
  created_at: number;
  // For tabular artifacts
  table?: { columns: string[]; rows: Record<string, unknown>[] };
}