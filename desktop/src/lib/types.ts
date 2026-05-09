// ─── Navigation ───────────────────────────────────────────────────────────────

export type View = "chat" | "behaviors" | "folders" | "settings" | "devlog";

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
  content: string;
  icon?: string;
  model?: string;
  harness?: string;
  defaultInternetEnabled?: boolean;
  defaultToolsMode?: "auto" | "with_tools" | "without_tools";
  localOnly?: boolean;
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
  behaviorId?: string;
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

export type UiMode = "simple" | "advanced";

export interface OnboardingCheck {
  id: string;
  name: string;
  status: "ok" | "warning" | "error";
  details: string;
  action: string;
}

export interface OnboardingStatus {
  status: "ready" | "needs_attention";
  checks: OnboardingCheck[];
  first_prompt_examples: string[];
}

export interface TaskTemplate {
  id: string;
  title: string;
  description: string;
  prompt_template: string;
}
