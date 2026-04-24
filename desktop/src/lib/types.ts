// ─── Navigation ───────────────────────────────────────────────────────────────

export type View = "chat" | "behaviors" | "knowledge" | "folders" | "system" | "settings" | "hub" | "devlog";

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
  pending?: boolean;
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
  model?: string;       // optional model alias/id override for this behavior
  harness?: string;     // optional harness override for this behavior
  defaultInternetEnabled?: boolean; // per-behavior default for internet tool usage
  defaultToolsMode?: "auto" | "with_tools" | "without_tools"; // per-behavior default tool policy
  llamacpp?: {
    contextSize?: number;
    gpuLayers?: number;
    flashAttn?: boolean;
    cacheTypeK?: string;
    cacheTypeV?: string;
    extraArgs?: string;
  };
  localOnly?: boolean;  // local machine profile (not meant for sync/repo)
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
  state?: "ready" | "loading" | "not_loaded";
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

// ─── Model Hub ────────────────────────────────────────────────────────────────

export interface HubModelTasks {
  chat: number;
  code: number;
  reasoning: number;
  instruct: number;
}

export interface HubModel {
  id: string;
  family: string;
  name: string;
  version: string;
  size_label: string;
  hf_repo: string;
  filename: string;
  quant: string;
  vram_gb: number;
  ram_gb: number;
  file_gb: number;
  context: number;
  tier: "entry" | "mid" | "high" | "ultra";
  tasks: HubModelTasks;
  license: string;
  release: string;
  recommended_for: string[];
  badge: "new" | "recommended" | "popular" | null;
}

export interface HardwareProfile {
  vram_gb: number;
  ram_gb: number;
  tier: "entry" | "mid" | "high" | "ultra";
}

export interface HubRecommendations {
  tier: string;
  ideal: HubModel | null;
  balanced: HubModel | null;
  fast: HubModel | null;
  all_fitting: HubModel[];
}

export interface HubCatalogResponse {
  hardware: HardwareProfile;
  catalog: HubModel[];
  recommendations: HubRecommendations;
}

export interface HubUpdateNotification {
  type: "family_upgrade" | "same_family_upgrade" | "catalog_suggestion";
  current_family: string;
  new_family?: string;
  current_entry?: HubModel;
  recommended: HubModel;
  message: string;
}

export interface HubDownload {
  id: string;
  url: string;
  hf_repo: string;
  filename: string;
  dest_path: string;
  status: "starting" | "downloading" | "done" | "error" | "cancelled";
  progress: number;
  downloaded_gb: number;
  total_gb: number;
  speed_mbps: number;
  eta_s: number;
  error: string | null;
}

export interface HubSearchFile {
  filename: string;
  size_gb: number | null;
  quant: string;
}

export interface HubSearchResult {
  repo: string;
  title: string;
  downloads: number;
  likes: number;
  updated_at: string;
  gguf_count: number;
  recommended_filename: string | null;
  files: HubSearchFile[];
}

export interface HubSearchResponse {
  query: string;
  results: HubSearchResult[];
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
