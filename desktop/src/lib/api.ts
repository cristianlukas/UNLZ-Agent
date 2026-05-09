import { invoke } from "@tauri-apps/api/core";
import type { Behavior, HealthResponse, OnboardingStatus, TaskTemplate } from "./types";

const BASE = "http://127.0.0.1:7719";

// ─── Chat streaming ──────────────────────────────────────────────────────────

export type StreamEvent =
  | { type: "run"; run_id: string }
  | { type: "step"; text: string; args?: Record<string, unknown> }
  | { type: "chunk"; text: string }
  | { type: "timeline"; stage: string; label: string; ts?: number }
  | { type: "confidence"; score: number; tool_calls: number }
  | { type: "error"; text: string; human_message?: string; common_causes?: string[]; fix_steps?: string[] }
  | { type: "done" };

export async function* streamChat(
  message: string,
  history: Array<{ role: string; content: string }>,
  systemPrompt?: string,
  modelOverride?: string,
  harnessOverride?: string,
  llamacppOverrides?: Record<string, unknown>,
  folderId?: string,
  sandboxRoot?: string,
  mode: "normal" | "plan" | "iterate" | "simple" = "normal",
  conversationId = "",
  dryRun = false,
  internetEnabled = true,
  toolsMode: "auto" | "with_tools" | "without_tools" = "auto",
  userProfile: Record<string, unknown> = {},
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({
      message,
      history,
      system_prompt: systemPrompt ?? "",
      model_override: modelOverride ?? "",
      harness_override: harnessOverride ?? "",
      llamacpp_overrides: llamacppOverrides ?? {},
      folder_id: folderId ?? "",
      sandbox_root: sandboxRoot ?? "",
      mode,
      conversation_id: conversationId,
      dry_run: dryRun,
      internet_enabled: internetEnabled,
      tools_mode: toolsMode,
      user_profile: userProfile ?? {},
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
    let chunk;
    try {
      chunk = await reader.read();
    } catch (e) {
      const msg = String(e || "").toLowerCase();
      if (msg.includes("abort")) break;
      throw e;
    }
    const { done, value } = chunk;
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
      } catch { /* malformed chunk */ }
    }
  }
}

export async function cancelRun(runId: string): Promise<void> {
  const safe = String(runId || "").trim();
  if (!safe) return;
  await fetch(`${BASE}/runs/${encodeURIComponent(safe)}/cancel`, { method: "POST" });
}

export async function listFolderFiles(folderId: string): Promise<{ name: string; size: number; modified: number }[]> {
  try {
    const res = await fetch(`${BASE}/folders/${encodeURIComponent(folderId)}/files`);
    if (!res.ok) return [];
    return res.json();
  } catch { return []; }
}

export async function uploadFolderFile(folderId: string, file: File): Promise<{ filename: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/folders/${encodeURIComponent(folderId)}/files`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function runApprovedWindowsCommand(_payload: {
  command: string;
  cwd?: string;
  sandbox_root?: string;
  idempotency_key?: string;
}): Promise<{ status: string; command?: string; returncode?: number; stdout?: string; stderr?: string; error?: string; reason?: string; timeout_sec?: number }> {
  throw new Error("Command approval not supported in opencode-only mode.");
}

// ─── Health ──────────────────────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BASE}/health`);
  return res.json();
}

export async function getOnboardingHealth(): Promise<OnboardingStatus> {
  const res = await fetch(`${BASE}/health/onboarding`);
  return res.json();
}

export async function runOnboardingFix(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${BASE}/health/onboarding/fix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ensure_runtime: true }),
  });
  return res.json();
}

export async function startMcpServer(): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/system/mcp/start`, { method: "POST" });
  return res.json();
}

export async function getTaskTemplates(): Promise<TaskTemplate[]> {
  const res = await fetch(`${BASE}/newbie/task-templates`);
  if (!res.ok) return [];
  return res.json();
}

export async function getNewbieProfile(): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/newbie/profile`);
  if (!res.ok) return {};
  return res.json();
}

export async function saveNewbieProfile(payload: Record<string, unknown>): Promise<void> {
  await fetch(`${BASE}/newbie/profile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getHealthCenter(): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/health/center`);
  if (!res.ok) return {};
  return res.json();
}

export interface OpencodeWarmupStatus {
  status: "idle" | "running" | "ready" | "error" | string;
  detail?: string;
  started_at?: string;
  finished_at?: string;
}

export async function getOpencodeWarmupStatus(): Promise<OpencodeWarmupStatus | null> {
  try {
    const res = await fetch(`${BASE}/opencode/warmup`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

// ─── Settings ────────────────────────────────────────────────────────────────

export async function getSettings(): Promise<Record<string, string>> {
  try {
    return await invoke<Record<string, string>>("get_settings");
  } catch {
    const res = await fetch(`${BASE}/settings`);
    return res.json();
  }
}

export async function saveSettings(payload: Record<string, string>): Promise<void> {
  await invoke<void>("save_settings", { payload });
  window.dispatchEvent(new CustomEvent("unlz-settings-updated", { detail: payload }));
  fetch(`${BASE}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).catch(() => { /* backend may be offline */ });
}

export async function pickDirectory(): Promise<string | null> {
  try { return await invoke<string | null>("pick_directory"); } catch { return null; }
}

export async function pickFile(filterName?: string, extensions?: string[]): Promise<string | null> {
  try {
    return await invoke<string | null>("pick_file", {
      filterName: filterName ?? null,
      extensions: extensions ?? null,
    });
  } catch { return null; }
}

// ─── Local behaviors ─────────────────────────────────────────────────────────

export async function getLocalBehaviors(): Promise<Behavior[]> {
  try {
    const res = await fetch(`${BASE}/local/behaviors`);
    if (!res.ok) return [];
    return res.json();
  } catch { return []; }
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

export interface BootstrapStatus {
  status: "idle" | "running" | "downloading" | "ready" | "warning" | "error" | string;
  detail?: string;
  bucket?: string;
  tier?: string;
  model_path?: string;
  vram_gb?: number;
  ram_gb?: number;
  progress?: number;
  downloaded_mb?: number;
  total_mb?: number | null;
  speed_mbps?: number;
}

export async function getBootstrapStatus(): Promise<BootstrapStatus | null> {
  try {
    const res = await fetch(`${BASE}/bootstrap/status`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getHarnessesStatus(): Promise<HarnessesStatus> {
  const res = await fetch(`${BASE}/harnesses/status`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function installHarness(harnessId: string): Promise<{ status: string; path: string; version?: string }> {
  const res = await fetch(`${BASE}/harnesses/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ harness_id: harnessId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ─── Dev log ─────────────────────────────────────────────────────────────────

export interface DevLogResponse {
  lines: string[];
  path: string;
  exists: boolean;
  total?: number;
  error?: string;
}

export interface DevTraceSummary {
  run_id: string;
  conversation_id: string;
  mode: string;
  mode_effective?: string;
  started_at: string;
  finished_at: string;
  event_count: number;
  error_count: number;
  errors: string[];
  input_preview: string;
  timing?: Record<string, number>;
}

export interface DevTraceEvent {
  type: string;
  text?: string;
  args?: Record<string, unknown>;
  ts_ms?: number;
  dt_ms_from_start?: number;
  duration_ms?: number;
  [key: string]: unknown;
}

export interface DevTrace {
  run_id: string;
  conversation_id: string;
  mode: string;
  mode_effective?: string;
  started_at: string;
  finished_at: string;
  input: { message: string; history_size: number };
  timing?: Record<string, number>;
  events: DevTraceEvent[];
}

export async function devGetLog(lines = 300): Promise<DevLogResponse> {
  const res = await fetch(`${BASE}/dev/log?lines=${lines}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function* devStreamLog(lines = 100): AsyncGenerator<{ line: string; init: boolean }> {
  const res = await fetch(`${BASE}/dev/log/stream?lines=${lines}`);
  if (!res.ok || !res.body) throw new Error(`SSE error: ${res.status}`);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines2 = buf.split("\n");
    buf = lines2.pop() ?? "";
    for (const line of lines2) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      try { yield JSON.parse(raw); } catch { /* skip */ }
    }
  }
}

export async function devListTraces(limit = 30): Promise<DevTraceSummary[]> {
  const res = await fetch(`${BASE}/dev/traces?limit=${limit}`);
  if (!res.ok) return [];
  return res.json();
}

export async function devGetTrace(runId: string): Promise<DevTrace> {
  const res = await fetch(`${BASE}/dev/traces/${runId}`);
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export async function devClearTraces(): Promise<{ deleted: number }> {
  const res = await fetch(`${BASE}/dev/traces`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}
