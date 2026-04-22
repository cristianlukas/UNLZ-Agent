import { invoke } from "@tauri-apps/api/core";
import type { AgentStep, HealthResponse, KbFile, LlamacppStatus, SystemStats } from "./types";

const BASE = "http://127.0.0.1:7719";

// ─── Chat streaming ──────────────────────────────────────────────────────────

export type StreamEvent =
  | { type: "run"; run_id: string }
  | { type: "step"; text: string; args?: Record<string, unknown> }
  | { type: "chunk"; text: string }
  | { type: "confidence"; score: number; tool_calls: number }
  | { type: "error"; text: string }
  | { type: "done" };

export async function* streamChat(
  message: string,
  history: Array<{ role: string; content: string }>,
  systemPrompt?: string,
  modelOverride?: string,
  harnessOverride?: string,
  folderId?: string,
  sandboxRoot?: string,
  mode: "normal" | "plan" | "iterate" | "simple" = "normal",
  conversationId = "",
  dryRun = false,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      history,
      system_prompt: systemPrompt ?? "",
      model_override: modelOverride ?? "",
      harness_override: harnessOverride ?? "",
      folder_id: folderId ?? "",
      sandbox_root: sandboxRoot ?? "",
      mode,
      conversation_id: conversationId,
      dry_run: dryRun,
    }),
  });

  if (!res.ok || !res.body) {
    yield { type: "error", text: `Server error: ${res.status}` };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    const lines = buf.split("\n");
    buf = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw || raw === "[DONE]") continue;
      try {
        yield JSON.parse(raw) as StreamEvent;
      } catch { /* malformed chunk, skip */ }
    }
  }
}

// ─── Health ──────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BASE}/health`);
  return res.json();
}

// ─── Settings (Tauri-native, works without backend) ──────────────────────────

export async function getSettings(): Promise<Record<string, string>> {
  // Try Tauri command first (always works), fall back to HTTP
  try {
    return await invoke<Record<string, string>>("get_settings");
  } catch {
    const res = await fetch(`${BASE}/settings`);
    return res.json();
  }
}

export async function saveSettings(payload: Record<string, string>): Promise<void> {
  // Always write via Tauri (filesystem access, no backend needed)
  await invoke<void>("save_settings", { payload });
  window.dispatchEvent(new CustomEvent("unlz-settings-updated", { detail: payload }));
  // Also notify running backend to reload (best-effort)
  fetch(`${BASE}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).catch(() => { /* backend may be offline, ignore */ });
}

export async function pickDirectory(): Promise<string | null> {
  try {
    return await invoke<string | null>("pick_directory");
  } catch {
    return null;
  }
}

export async function pickFile(
  filterName?: string,
  extensions?: string[]
): Promise<string | null> {
  try {
    return await invoke<string | null>("pick_file", {
      filterName: filterName ?? null,
      extensions: extensions ?? null,
    });
  } catch {
    return null;
  }
}

// ─── Knowledge base ──────────────────────────────────────────────────────────

export async function listFiles(): Promise<KbFile[]> {
  const res = await fetch(`${BASE}/files`);
  return res.json();
}

export async function uploadFile(file: File): Promise<{ success: boolean; filename: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/upload`, { method: "POST", body: form });
  return res.json();
}

export async function listFolderFiles(folderId: string): Promise<KbFile[]> {
  const res = await fetch(`${BASE}/folders/${encodeURIComponent(folderId)}/files`);
  return res.json();
}

export async function uploadFolderFile(
  folderId: string,
  file: File
): Promise<{ success: boolean; filename: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/folders/${encodeURIComponent(folderId)}/upload`, {
    method: "POST",
    body: form,
  });
  return res.json();
}

export async function triggerIngest(): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${BASE}/ingest`, { method: "POST" });
  return res.json();
}

// ─── System stats ─────────────────────────────────────────────────────────────

export async function getStats(): Promise<SystemStats> {
  const res = await fetch(`${BASE}/stats`);
  return res.json();
}

// ─── GGUF model discovery ─────────────────────────────────────────────────────

export interface GgufModel {
  path: string;
  name: string;
  stem: string;
  alias: string;
  size_gb: number;
  folder: string;
}

export async function listGgufModels(): Promise<GgufModel[]> {
  try {
    const res = await fetch(`${BASE}/models/gguf`);
    return res.json();
  } catch {
    return [];
  }
}

// ─── llama.cpp control ───────────────────────────────────────────────────────

export async function llamacppStart(): Promise<{ status: string; pid?: number; url?: string }> {
  const res = await fetch(`${BASE}/llamacpp/start`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function llamacppStop(): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/llamacpp/stop`, { method: "POST" });
  return res.json();
}

export async function getLlamacppStatus(): Promise<LlamacppStatus> {
  const res = await fetch(`${BASE}/llamacpp/status`);
  return res.json();
}

export interface LlamacppInstallerStatus {
  supported: boolean;
  reason?: string;
  installed: boolean;
  installed_version: string;
  latest_version: string;
  update_available: boolean;
  executable: string;
  release_error?: string;
}

export async function getLlamacppInstallerStatus(): Promise<LlamacppInstallerStatus> {
  const res = await fetch(`${BASE}/llamacpp/installer/status`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface LlamacppInstallerRunResult {
  status: string;
  installed_version: string;
  executable: string;
  models_dir: string;
  model_path: string;
  model_alias: string;
}

export async function runLlamacppInstaller(): Promise<LlamacppInstallerRunResult> {
  const res = await fetch(`${BASE}/llamacpp/installer/run`, { method: "POST" });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = await res.text(); } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

export interface CommandActionResult {
  status: string;
  mode?: string;
  operation_class?: string;
  command?: string;
  cwd?: string;
  idempotency_key?: string;
  returncode?: number;
  stdout?: string;
  stderr?: string;
  error?: string;
  reason?: string;
  timeout_sec?: number;
}

export async function runApprovedWindowsCommand(payload: {
  command: string;
  cwd?: string;
  sandbox_root?: string;
  timeout_sec?: number;
  idempotency_key?: string;
}): Promise<CommandActionResult> {
  const res = await fetch(`${BASE}/actions/run_windows_command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

// ─── Harnesses ───────────────────────────────────────────────────────────────

export interface HarnessOption {
  id: string;
  label: string;
  installed: boolean;
  version?: string;
  path?: string;
}

export interface HarnessesStatus {
  active: string;
  options: HarnessOption[];
}

export interface HarnessInstallResult {
  status: string;
  harness_id: string;
  path: string;
  version?: string;
}

export async function getHarnessesStatus(): Promise<HarnessesStatus> {
  const res = await fetch(`${BASE}/harnesses/status`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function installHarness(harnessId: string): Promise<HarnessInstallResult> {
  const res = await fetch(`${BASE}/harnesses/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ harness_id: harnessId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ─── Task router ─────────────────────────────────────────────────────────────

export interface TaskRouterAreaConfig {
  primary_model: string;
  fallback_models: string[];
  profile: string;
  keywords: string[];
}

export interface TaskRouterConfig {
  version: number;
  areas: Record<string, TaskRouterAreaConfig>;
}

export interface TaskRouterMetricsModel {
  calls: number;
  success_rate: number;
  avg_latency_ms: number;
  avg_retries: number;
}

export interface TaskRouterMetrics {
  total: number;
  areas: Record<string, Record<string, TaskRouterMetricsModel>>;
}

export interface TaskRouterRecalibrateResult {
  changes: Array<{ area: string; from: string; to: string }>;
  count: number;
  min_samples: number;
}

export async function getTaskRouterConfig(): Promise<TaskRouterConfig> {
  const res = await fetch(`${BASE}/router/config`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function saveTaskRouterConfig(payload: TaskRouterConfig): Promise<void> {
  const res = await fetch(`${BASE}/router/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function getTaskRouterMetrics(): Promise<TaskRouterMetrics> {
  const res = await fetch(`${BASE}/router/metrics`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function recalibrateTaskRouter(minSamples = 12): Promise<TaskRouterRecalibrateResult> {
  const res = await fetch(`${BASE}/router/recalibrate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ min_samples: minSamples }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
