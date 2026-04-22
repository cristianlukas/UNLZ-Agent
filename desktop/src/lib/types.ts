// ─── Navigation ───────────────────────────────────────────────────────────────

export type View = "chat" | "behaviors" | "knowledge" | "folders" | "system" | "settings";

// ─── Agent / Chat ─────────────────────────────────────────────────────────────

export interface AgentStep {
  tool: string;
  args?: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  technicalDetails?: string;
  steps?: AgentStep[];
  error?: boolean;
  confidence?: number;
  runId?: string;
  ts: number;
}

// ─── Behaviors (system prompt profiles) ──────────────────────────────────────

export interface Behavior {
  id: string;
  name: string;
  content: string;      // Markdown / plain text — the system prompt
  icon?: string;        // emoji shorthand
  createdAt: number;
  updatedAt: number;
}

// ─── Conversations ────────────────────────────────────────────────────────────

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
  behaviorId?: string;  // linked behavior (system prompt)
  folderId?: string;
}

export interface Folder {
  id: string;
  name: string;
  behaviorId?: string;
  customPrompt?: string;
  sandboxPath?: string;
  createdAt: number;
  updatedAt: number;
}

// ─── Health ───────────────────────────────────────────────────────────────────

export interface HealthComponent {
  status: "ok" | "warning" | "error";
  details: string;
}

export interface HealthResponse {
  status: "online" | "degraded";
  components: Record<string, HealthComponent>;
}

// ─── Knowledge base ───────────────────────────────────────────────────────────

export interface KbFile {
  name: string;
  size: number;
  modified: number;
}

// ─── System stats ─────────────────────────────────────────────────────────────

export interface SystemStats {
  cpu_percent: number;
  ram_total_gb: number;
  ram_used_gb: number;
  ram_percent: number;
  vram_total_gb?: number;
  vram_used_gb?: number;
  vram_percent?: number;
  gpus?: Array<{
    name: string;
    total_gb: number;
    used_gb: number;
    percent: number;
  }>;
  disk_total_gb: number;
  disk_used_gb: number;
  disk_percent: number;
  disks?: Array<{
    name: string;
    mountpoint: string;
    total_gb: number;
    used_gb: number;
    percent: number;
  }>;
}

// ─── llama.cpp status ─────────────────────────────────────────────────────────

export interface LlamacppStatus {
  running: boolean;
  managed: boolean;
  pid: number | null;
  url: string;
  model: string;
  alias: string;
}
