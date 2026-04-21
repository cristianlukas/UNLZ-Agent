import { useEffect, useState } from "react";
import { Save, Settings, RotateCcw, RefreshCw, FolderOpen, FileSearch, Download, Plus, Trash2, Search } from "lucide-react";
import {
  getSettings,
  saveSettings,
  listGgufModels,
  pickDirectory,
  pickFile,
  getLlamacppInstallerStatus,
  runLlamacppInstaller,
  getTaskRouterConfig,
  saveTaskRouterConfig,
  getTaskRouterMetrics,
  recalibrateTaskRouter,
} from "../lib/api";
import type {
  GgufModel,
  LlamacppInstallerStatus,
  TaskRouterConfig,
  TaskRouterMetrics,
} from "../lib/api";

type Config = Record<string, string>;

const DEFAULTS: Config = {
  LLM_PROVIDER: "llamacpp",
  AGENT_LANGUAGE: "es",
  AGENT_EXECUTION_MODE: "confirm",
  AGENT_COMMAND_TIMEOUT_SEC: "60",
  WEB_SEARCH_ENGINE: "google",
  MINIMIZE_TO_TRAY_ON_CLOSE: "false",
  WINDOW_CONTROLS_STYLE: "windows",
  WINDOW_CONTROLS_SIDE: "right",
  WINDOW_CONTROLS_ORDER: "minimize,maximize,close",
  VECTOR_DB_PROVIDER: "chroma",
  MCP_PORT: "8000",
  N8N_ENABLED: "false",
  OLLAMA_BASE_URL: "http://localhost:11434",
  OLLAMA_MODEL: "qwen2.5-coder:14b",
  OPENAI_MODEL: "gpt-4o-mini",
  LLAMACPP_MODELS_DIR: "",
  LLAMACPP_EXECUTABLE: "",
  LLAMACPP_MODEL_PATH: "",
  LLAMACPP_HOST: "127.0.0.1",
  LLAMACPP_PORT: "8080",
  LLAMACPP_CONTEXT_SIZE: "32768",
  LLAMACPP_N_GPU_LAYERS: "999",
  LLAMACPP_FLASH_ATTN: "true",
  LLAMACPP_MODEL_ALIAS: "local-model",
  LLAMACPP_CACHE_TYPE_K: "",
  LLAMACPP_CACHE_TYPE_V: "",
  LLAMACPP_EXTRA_ARGS: "",
};

const EMPTY_ROUTER: TaskRouterConfig = {
  version: 1,
  areas: {},
};

const ROUTER_METRICS_PREFS_KEY = "unlz.router.metrics.prefs.v1";

type RouterMetricsPrefs = {
  sortBy: "area" | "model" | "calls" | "success" | "latency" | "retries";
  sortDir: "asc" | "desc";
  pageSize: number;
};

function readRouterMetricsPrefs(): RouterMetricsPrefs {
  const fallback: RouterMetricsPrefs = { sortBy: "success", sortDir: "desc", pageSize: 10 };
  try {
    const raw = localStorage.getItem(ROUTER_METRICS_PREFS_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<RouterMetricsPrefs>;
    const sortBy = ["area", "model", "calls", "success", "latency", "retries"].includes(String(parsed.sortBy))
      ? (parsed.sortBy as RouterMetricsPrefs["sortBy"])
      : fallback.sortBy;
    const sortDir = parsed.sortDir === "asc" || parsed.sortDir === "desc" ? parsed.sortDir : fallback.sortDir;
    const pageSize = Number.isFinite(Number(parsed.pageSize)) ? Math.max(1, Number(parsed.pageSize)) : fallback.pageSize;
    return { sortBy, sortDir, pageSize };
  } catch {
    return fallback;
  }
}

// ─── Field primitives ─────────────────────────────────────────────────────────

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="block text-xs font-medium text-secondary uppercase tracking-wider">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted">{hint}</p>}
    </div>
  );
}

function Input({ value, onChange, placeholder, type = "text", mono = false, readOnly = false }: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  mono?: boolean;
  readOnly?: boolean;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      readOnly={readOnly}
      placeholder={placeholder}
      className={`input-field w-full px-3 py-2 text-sm ${mono ? "font-mono" : ""}`}
    />
  );
}

function Select({ value, onChange, options }: {
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input-field w-full px-3 py-2 text-sm appearance-none cursor-pointer"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} className="bg-surface">
            {o.label}
          </option>
        ))}
      </select>
      <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted text-xs">▼</div>
    </div>
  );
}

function Toggle({ value, onChange, label }: { value: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <label className="flex items-center gap-3 cursor-pointer">
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative w-9 h-5 rounded-full transition-colors ${value ? "bg-accent" : "bg-border"}`}
      >
        <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform shadow-sm ${value ? "translate-x-4" : ""}`} />
      </button>
      {label && <span className="text-sm text-secondary">{label}</span>}
    </label>
  );
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-4">
      <h2 className="text-xs font-semibold text-muted uppercase tracking-widest border-b border-border pb-2">
        {title}
      </h2>
      {children}
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function SettingsView() {
  const [config, setConfig] = useState<Config>({ ...DEFAULTS });
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [ggufModels, setGgufModels] = useState<GgufModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [installerStatus, setInstallerStatus] = useState<LlamacppInstallerStatus | null>(null);
  const [installerBusy, setInstallerBusy] = useState(false);
  const [routerConfig, setRouterConfig] = useState<TaskRouterConfig>(EMPTY_ROUTER);
  const [routerMetrics, setRouterMetrics] = useState<TaskRouterMetrics | null>(null);
  const [routerBusy, setRouterBusy] = useState(false);
  const [routerMinSamples, setRouterMinSamples] = useState("12");
  const [routerSearch, setRouterSearch] = useState("");
  const [newRouterArea, setNewRouterArea] = useState("");
  const _routerPrefs = readRouterMetricsPrefs();
  const [metricsSortBy, setMetricsSortBy] = useState<"area" | "model" | "calls" | "success" | "latency" | "retries">(_routerPrefs.sortBy);
  const [metricsSortDir, setMetricsSortDir] = useState<"asc" | "desc">(_routerPrefs.sortDir);
  const [metricsPage, setMetricsPage] = useState(1);
  const [metricsPageSize, setMetricsPageSize] = useState(_routerPrefs.pageSize);

  useEffect(() => {
    getSettings()
      .then((data) => setConfig((prev) => ({ ...prev, ...data })))
      .catch(() => { /* offline, use defaults */ });
  }, []);

  useEffect(() => {
    getTaskRouterConfig()
      .then((cfg) => setRouterConfig(cfg))
      .catch(() => { /* backend offline */ });
    getTaskRouterMetrics()
      .then((m) => setRouterMetrics(m))
      .catch(() => { /* backend offline */ });
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(
        ROUTER_METRICS_PREFS_KEY,
        JSON.stringify({
          sortBy: metricsSortBy,
          sortDir: metricsSortDir,
          pageSize: metricsPageSize,
        })
      );
    } catch {
      /* ignore storage errors */
    }
  }, [metricsSortBy, metricsSortDir, metricsPageSize]);

  useEffect(() => {
    if ((config.LLM_PROVIDER || "llamacpp") !== "llamacpp") return;
    refreshGgufModels();
  }, [config.LLM_PROVIDER, config.LLAMACPP_MODELS_DIR, config.LLAMACPP_MODEL_PATH]);

  useEffect(() => {
    if ((config.LLM_PROVIDER || "llamacpp") !== "llamacpp") return;
    refreshInstallerStatus();
  }, [config.LLM_PROVIDER, config.LLAMACPP_EXECUTABLE]);

  async function refreshGgufModels() {
    setLoadingModels(true);
    const models = await listGgufModels();
    setGgufModels(models);
    setLoadingModels(false);
  }

  async function refreshInstallerStatus() {
    try {
      const status = await getLlamacppInstallerStatus();
      setInstallerStatus(status);
    } catch {
      setInstallerStatus(null);
    }
  }

  const set = (key: string, val: string) => setConfig((c) => ({ ...c, [key]: val }));

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  }

  async function handleSave() {
    setSaving(true);
    try {
      await saveSettings(config);
      showToast("Settings saved — restart agent to apply changes");
    } catch (e) {
      showToast(`Save failed: ${e}`);
    }
    setSaving(false);
  }

  async function chooseModelsDir() {
    const picked = await pickDirectory();
    if (!picked) return;
    set("LLAMACPP_MODELS_DIR", picked);
  }

  async function chooseLlamaServerExe() {
    const picked = await pickFile("Executables", ["exe"]);
    if (!picked) return;
    set("LLAMACPP_EXECUTABLE", picked);
  }

  async function installOrUpdateLlamacpp() {
    setInstallerBusy(true);
    try {
      const result = await runLlamacppInstaller();
      setConfig((prev) => ({
        ...prev,
        LLM_PROVIDER: "llamacpp",
        LLAMACPP_EXECUTABLE: result.executable || prev.LLAMACPP_EXECUTABLE || "",
        LLAMACPP_MODELS_DIR: result.models_dir || prev.LLAMACPP_MODELS_DIR || "",
        LLAMACPP_MODEL_PATH: result.model_path || prev.LLAMACPP_MODEL_PATH || "",
        LLAMACPP_MODEL_ALIAS: result.model_alias || prev.LLAMACPP_MODEL_ALIAS || "local-model",
      }));
      const next = await getSettings();
      setConfig((prev) => ({ ...prev, ...next }));
      await refreshInstallerStatus();
      showToast(`llama.cpp listo (${result.installed_version || "latest"})`);
    } catch (e) {
      showToast(`No se pudo instalar/actualizar llama.cpp: ${e}`);
    } finally {
      setInstallerBusy(false);
    }
  }

  function updateRouterArea(area: string, patch: Partial<TaskRouterConfig["areas"][string]>) {
    setRouterConfig((prev) => ({
      ...prev,
      areas: {
        ...prev.areas,
        [area]: {
          primary_model: prev.areas[area]?.primary_model ?? "",
          fallback_models: prev.areas[area]?.fallback_models ?? [],
          profile: prev.areas[area]?.profile ?? "",
          keywords: prev.areas[area]?.keywords ?? [],
          ...patch,
        },
      },
    }));
  }

  function addRouterArea() {
    const raw = (newRouterArea || "").trim().toLowerCase();
    if (!raw) return;
    const area = raw.replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
    if (!area) return;
    if (routerConfig.areas[area]) {
      showToast("Esa área ya existe");
      return;
    }
    updateRouterArea(area, {
      primary_model: "",
      fallback_models: [],
      profile: "",
      keywords: [],
    });
    setNewRouterArea("");
  }

  function removeRouterArea(area: string) {
    setRouterConfig((prev) => {
      const nextAreas = { ...prev.areas };
      delete nextAreas[area];
      return { ...prev, areas: nextAreas };
    });
  }

  async function refreshRouterMetrics() {
    try {
      const m = await getTaskRouterMetrics();
      setRouterMetrics(m);
      setMetricsPage(1);
    } catch (e) {
      showToast(`No se pudo leer métricas del router: ${e}`);
    }
  }

  async function handleSaveRouterConfig() {
    setRouterBusy(true);
    try {
      const normalized: TaskRouterConfig = {
        version: Number(routerConfig.version || 1),
        areas: Object.fromEntries(
          Object.entries(routerConfig.areas || {}).map(([area, cfg]) => [
            area,
            {
              primary_model: String(cfg.primary_model || "").trim(),
              fallback_models: (cfg.fallback_models || []).map((x) => String(x).trim()).filter(Boolean),
              profile: String(cfg.profile || "").trim(),
              keywords: (cfg.keywords || []).map((x) => String(x).trim().toLowerCase()).filter(Boolean),
            },
          ])
        ),
      };
      await saveTaskRouterConfig(normalized);
      showToast("Task Router guardado");
      await refreshRouterMetrics();
    } catch (e) {
      showToast(`No se pudo guardar Task Router: ${e}`);
    } finally {
      setRouterBusy(false);
    }
  }

  async function handleRecalibrateRouter() {
    setRouterBusy(true);
    try {
      const minSamples = Math.max(4, Number(routerMinSamples || "12"));
      const out = await recalibrateTaskRouter(minSamples);
      const cfg = await getTaskRouterConfig();
      setRouterConfig(cfg);
      await refreshRouterMetrics();
      showToast(out.count > 0 ? `Recalibrado: ${out.count} áreas ajustadas` : "Sin cambios en recalibración");
    } catch (e) {
      showToast(`No se pudo recalibrar router: ${e}`);
    } finally {
      setRouterBusy(false);
    }
  }

  const provider = config.LLM_PROVIDER || "ollama";
  const resolvedLlamacppExecutable = (config.LLAMACPP_EXECUTABLE || installerStatus?.executable || "").trim();
  const controlsOrder = config.WINDOW_CONTROLS_ORDER || "minimize,maximize,close";
  const filteredRouterAreas = Object.entries(routerConfig.areas || {}).filter(([area, cfg]) => {
    const q = routerSearch.trim().toLowerCase();
    if (!q) return true;
    return (
      area.toLowerCase().includes(q) ||
      String(cfg.primary_model || "").toLowerCase().includes(q) ||
      String(cfg.profile || "").toLowerCase().includes(q) ||
      (cfg.keywords || []).some((k) => String(k).toLowerCase().includes(q))
    );
  });
  const metricsRows = (() => {
    const rows: Array<{ area: string; model: string; calls: number; success: number; latency: number; retries: number }> = [];
    for (const [area, models] of Object.entries(routerMetrics?.areas || {})) {
      for (const [model, m] of Object.entries(models || {})) {
        rows.push({
          area,
          model,
          calls: Number(m.calls || 0),
          success: Number(m.success_rate || 0),
          latency: Number(m.avg_latency_ms || 0),
          retries: Number(m.avg_retries || 0),
        });
      }
    }
    rows.sort((a, b) => (b.success - a.success) || (a.latency - b.latency) || (b.calls - a.calls));
    return rows;
  })();
  const sortedMetricsRows = (() => {
    const rows = [...metricsRows];
    rows.sort((a, b) => {
      let cmp = 0;
      if (metricsSortBy === "area" || metricsSortBy === "model") {
        cmp = String(a[metricsSortBy]).localeCompare(String(b[metricsSortBy]));
      } else {
        cmp = Number(a[metricsSortBy]) - Number(b[metricsSortBy]);
      }
      return metricsSortDir === "asc" ? cmp : -cmp;
    });
    return rows;
  })();
  const metricsTotalPages = Math.max(1, Math.ceil(sortedMetricsRows.length / metricsPageSize));
  const metricsCurrentPage = Math.min(metricsPage, metricsTotalPages);
  const metricsPageRows = sortedMetricsRows.slice(
    (metricsCurrentPage - 1) * metricsPageSize,
    metricsCurrentPage * metricsPageSize
  );

  function toggleMetricsSort(col: "area" | "model" | "calls" | "success" | "latency" | "retries") {
    if (metricsSortBy === col) {
      setMetricsSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setMetricsSortBy(col);
      setMetricsSortDir(col === "area" || col === "model" ? "asc" : "desc");
    }
    setMetricsPage(1);
  }
  const modelOptions = (() => {
    const opts = ggufModels.map((m) => ({
      value: m.path,
      label: `${m.folder}/${m.name} (${m.size_gb} GB)`,
    }));
    const current = config.LLAMACPP_MODEL_PATH || "";
    if (current && !opts.some((o) => o.value === current)) {
      opts.unshift({ value: current, label: `Actual: ${current}` });
    }
    if (opts.length === 0) {
      opts.push({ value: "", label: "— sin modelos detectados (usar ↻) —" });
    }
    return opts;
  })();

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <Settings size={16} className="text-accent" />
          <span className="text-sm font-medium text-primary">Configuration</span>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-ghost text-xs px-3 py-1.5 flex items-center gap-1.5"
            onClick={() => { setConfig({ ...DEFAULTS }); showToast("Reset to defaults"); }}
          >
            <RotateCcw size={12} />
            Reset
          </button>
          <button
            className="btn-primary text-xs px-4 py-1.5 flex items-center gap-1.5"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? (
              <div className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
            ) : (
              <Save size={12} />
            )}
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {/* Form */}
      <div className="flex-1 overflow-y-auto px-5 py-5 space-y-8">

        {/* General */}
        <Section title="General">
          <Field label="Language">
            <Select
              value={config.AGENT_LANGUAGE}
              onChange={(v) => set("AGENT_LANGUAGE", v)}
              options={[
                { value: "es", label: "Español" },
                { value: "en", label: "English" },
                { value: "zh", label: "中文" },
              ]}
            />
          </Field>
          <Field label="Vector Database">
            <Select
              value={config.VECTOR_DB_PROVIDER}
              onChange={(v) => set("VECTOR_DB_PROVIDER", v)}
              options={[
                { value: "chroma", label: "Local — ChromaDB" },
                { value: "supabase", label: "Cloud — Supabase" },
              ]}
            />
          </Field>
          <Field label="Web Search Engine">
            <Select
              value={config.WEB_SEARCH_ENGINE || "google"}
              onChange={(v) => set("WEB_SEARCH_ENGINE", v)}
              options={[
                { value: "google", label: "Google (preferido)" },
                { value: "duckduckgo", label: "DuckDuckGo" },
                { value: "auto", label: "Auto (Google + fallback)" },
              ]}
            />
          </Field>
          <Field label="Cerrar a bandeja" hint="Si está activo, al cerrar la ventana se oculta en la bandeja del sistema en lugar de salir.">
            <Toggle
              value={(config.MINIMIZE_TO_TRAY_ON_CLOSE || "false") === "true"}
              onChange={(v) => set("MINIMIZE_TO_TRAY_ON_CLOSE", v ? "true" : "false")}
              label={(config.MINIMIZE_TO_TRAY_ON_CLOSE || "false") === "true" ? "activo" : "inactivo"}
            />
          </Field>
        </Section>

        <Section title="Agent Actions">
          <Field label="Execution mode" hint="confirm: pregunta antes de ejecutar comandos. autonomous: ejecuta directamente.">
            <Select
              value={config.AGENT_EXECUTION_MODE || "confirm"}
              onChange={(v) => set("AGENT_EXECUTION_MODE", v)}
              options={[
                { value: "confirm", label: "Preguntar antes de ejecutar" },
                { value: "autonomous", label: "Agente autónomo" },
              ]}
            />
          </Field>
          <Field label="Command timeout (seconds)">
            <Input
              value={config.AGENT_COMMAND_TIMEOUT_SEC || "60"}
              onChange={(v) => set("AGENT_COMMAND_TIMEOUT_SEC", v)}
              placeholder="60"
              type="number"
              mono
            />
          </Field>
        </Section>

        <Section title="Task Router">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2 min-w-[240px]">
              <div className="relative flex-1">
                <Input
                  value={routerSearch}
                  onChange={setRouterSearch}
                  placeholder="Buscar área/modelo/keyword..."
                />
                <Search size={12} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={newRouterArea}
                onChange={setNewRouterArea}
                placeholder="nueva_area"
                mono
              />
              <button
                type="button"
                onClick={addRouterArea}
                className="btn-ghost text-xs px-2.5 py-1.5 flex items-center gap-1"
              >
                <Plus size={12} />
                Agregar área
              </button>
            </div>
            <button
              type="button"
              onClick={refreshRouterMetrics}
              className="btn-ghost text-xs px-2.5 py-1.5 flex items-center gap-1"
            >
              <RefreshCw size={12} />
              Refrescar métricas
            </button>
            <button
              type="button"
              onClick={handleSaveRouterConfig}
              disabled={routerBusy}
              className="btn-ghost text-xs px-2.5 py-1.5 flex items-center gap-1 disabled:opacity-40"
            >
              <Save size={12} />
              Guardar router
            </button>
            <div className="flex items-center gap-2">
              <Input
                value={routerMinSamples}
                onChange={setRouterMinSamples}
                placeholder="12"
                type="number"
                mono
              />
              <button
                type="button"
                onClick={handleRecalibrateRouter}
                disabled={routerBusy}
                className="btn-ghost text-xs px-2.5 py-1.5 flex items-center gap-1 disabled:opacity-40"
              >
                <RotateCcw size={12} />
                Recalibrar
              </button>
            </div>
          </div>

          {Object.keys(routerConfig.areas || {}).length === 0 ? (
            <p className="text-xs text-muted">No hay áreas de router cargadas.</p>
          ) : filteredRouterAreas.length === 0 ? (
            <p className="text-xs text-muted">No hay áreas que coincidan con el filtro.</p>
          ) : (
            <div className="space-y-3">
              {filteredRouterAreas.map(([area, cfg]) => {
                const metricsByArea = routerMetrics?.areas?.[area] || {};
                return (
                  <div key={area} className="border border-border rounded-xl p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs font-semibold text-primary uppercase tracking-wide">{area}</p>
                      <button
                        type="button"
                        onClick={() => removeRouterArea(area)}
                        className="btn-ghost text-xs px-2 py-1 flex items-center gap-1 text-red-300 hover:text-red-200 border-red-900/30"
                        title="Eliminar área"
                      >
                        <Trash2 size={12} />
                        Eliminar
                      </button>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <Field label="Primary model">
                        <Input
                          value={cfg.primary_model}
                          onChange={(v) => updateRouterArea(area, { primary_model: v })}
                          placeholder="model-id"
                          mono
                        />
                      </Field>
                      <Field label="Profile">
                        <Input
                          value={cfg.profile}
                          onChange={(v) => updateRouterArea(area, { profile: v })}
                          placeholder="routing profile"
                          mono
                        />
                      </Field>
                    </div>
                    <Field label="Fallback models (coma)">
                      <Input
                        value={(cfg.fallback_models || []).join(", ")}
                        onChange={(v) =>
                          updateRouterArea(area, {
                            fallback_models: v
                              .split(",")
                              .map((x) => x.trim())
                              .filter(Boolean),
                          })
                        }
                        placeholder="model-a, model-b"
                        mono
                      />
                    </Field>
                    <Field label="Keywords (coma)">
                      <Input
                        value={(cfg.keywords || []).join(", ")}
                        onChange={(v) =>
                          updateRouterArea(area, {
                            keywords: v
                              .split(",")
                              .map((x) => x.trim().toLowerCase())
                              .filter(Boolean),
                          })
                        }
                        placeholder="keyword1, keyword2"
                      />
                    </Field>
                    {Object.keys(metricsByArea).length > 0 && (
                      <div className="text-[11px] text-muted">
                        {Object.entries(metricsByArea).map(([model, m]) => (
                          <div key={model} className="font-mono truncate">
                            {model}: calls={m.calls} success={Math.round((m.success_rate || 0) * 100)}% latency={m.avg_latency_ms}ms retries={m.avg_retries}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="border border-border rounded-xl p-3 space-y-2">
            <p className="text-xs font-semibold text-primary uppercase tracking-wide">
              Métricas comparativas (solo lectura)
            </p>
            {sortedMetricsRows.length === 0 ? (
              <p className="text-xs text-muted">Sin datos todavía.</p>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2 text-[11px] text-muted">
                  <div className="flex items-center gap-2">
                    <span>Filas por página</span>
                    <select
                      value={String(metricsPageSize)}
                      onChange={(e) => {
                        setMetricsPageSize(Math.max(1, Number(e.target.value) || 10));
                        setMetricsPage(1);
                      }}
                      className="input-field px-2 py-1 text-[11px]"
                    >
                      <option value="5">5</option>
                      <option value="10">10</option>
                      <option value="20">20</option>
                      <option value="50">50</option>
                    </select>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setMetricsPage((p) => Math.max(1, p - 1))}
                      disabled={metricsCurrentPage <= 1}
                      className="btn-ghost px-2 py-1 text-[11px] disabled:opacity-40"
                    >
                      Anterior
                    </button>
                    <span>Página {metricsCurrentPage} / {metricsTotalPages}</span>
                    <button
                      type="button"
                      onClick={() => setMetricsPage((p) => Math.min(metricsTotalPages, p + 1))}
                      disabled={metricsCurrentPage >= metricsTotalPages}
                      className="btn-ghost px-2 py-1 text-[11px] disabled:opacity-40"
                    >
                      Siguiente
                    </button>
                  </div>
                </div>
                <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-muted border-b border-border">
                      <th className="text-left py-1.5 pr-3">
                        <button type="button" onClick={() => toggleMetricsSort("area")} className="hover:text-primary">
                          Área {metricsSortBy === "area" ? (metricsSortDir === "asc" ? "▲" : "▼") : ""}
                        </button>
                      </th>
                      <th className="text-left py-1.5 pr-3">
                        <button type="button" onClick={() => toggleMetricsSort("model")} className="hover:text-primary">
                          Modelo {metricsSortBy === "model" ? (metricsSortDir === "asc" ? "▲" : "▼") : ""}
                        </button>
                      </th>
                      <th className="text-right py-1.5 pr-3">
                        <button type="button" onClick={() => toggleMetricsSort("calls")} className="hover:text-primary">
                          Calls {metricsSortBy === "calls" ? (metricsSortDir === "asc" ? "▲" : "▼") : ""}
                        </button>
                      </th>
                      <th className="text-right py-1.5 pr-3">
                        <button type="button" onClick={() => toggleMetricsSort("success")} className="hover:text-primary">
                          Success {metricsSortBy === "success" ? (metricsSortDir === "asc" ? "▲" : "▼") : ""}
                        </button>
                      </th>
                      <th className="text-right py-1.5 pr-3">
                        <button type="button" onClick={() => toggleMetricsSort("latency")} className="hover:text-primary">
                          Latency {metricsSortBy === "latency" ? (metricsSortDir === "asc" ? "▲" : "▼") : ""}
                        </button>
                      </th>
                      <th className="text-right py-1.5">
                        <button type="button" onClick={() => toggleMetricsSort("retries")} className="hover:text-primary">
                          Retries {metricsSortBy === "retries" ? (metricsSortDir === "asc" ? "▲" : "▼") : ""}
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {metricsPageRows.map((r) => (
                      <tr key={`${r.area}:${r.model}`} className="border-b border-border/40">
                        <td className="py-1.5 pr-3 text-secondary">{r.area}</td>
                        <td className="py-1.5 pr-3 font-mono text-[11px] text-secondary truncate max-w-[260px]">{r.model}</td>
                        <td className="py-1.5 pr-3 text-right">{r.calls}</td>
                        <td className="py-1.5 pr-3 text-right">{Math.round(r.success * 100)}%</td>
                        <td className="py-1.5 pr-3 text-right">{r.latency}ms</td>
                        <td className="py-1.5 text-right">{r.retries}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              </div>
            )}
          </div>
        </Section>

        <Section title="Window Controls">
          <Field label="Controls style" hint="Estilo visual de botones de ventana.">
            <Select
              value={config.WINDOW_CONTROLS_STYLE || "windows"}
              onChange={(v) => set("WINDOW_CONTROLS_STYLE", v)}
              options={[
                { value: "windows", label: "Windows" },
                { value: "mac", label: "Mac" },
              ]}
            />
          </Field>
          <Field label="Controls side" hint="Posición de los botones de ventana en la barra superior.">
            <Select
              value={config.WINDOW_CONTROLS_SIDE || "right"}
              onChange={(v) => set("WINDOW_CONTROLS_SIDE", v)}
              options={[
                { value: "right", label: "Derecha (Windows por defecto)" },
                { value: "left", label: "Izquierda" },
              ]}
            />
          </Field>
          <Field label="Controls order" hint="Orden visible de botones: minimizar, maximizar y cerrar.">
            <Select
              value={controlsOrder}
              onChange={(v) => set("WINDOW_CONTROLS_ORDER", v)}
              options={[
                { value: "minimize,maximize,close", label: "Minimizar · Maximizar · Cerrar" },
                { value: "minimize,close,maximize", label: "Minimizar · Cerrar · Maximizar" },
                { value: "maximize,minimize,close", label: "Maximizar · Minimizar · Cerrar" },
                { value: "maximize,close,minimize", label: "Maximizar · Cerrar · Minimizar" },
                { value: "close,minimize,maximize", label: "Cerrar · Minimizar · Maximizar" },
                { value: "close,maximize,minimize", label: "Cerrar · Maximizar · Minimizar" },
              ]}
            />
          </Field>
        </Section>

        {/* LLM Provider */}
        <Section title="LLM Provider">
          <Field label="Backend">
            <Select
              value={provider}
              onChange={(v) => set("LLM_PROVIDER", v)}
              options={[
                { value: "llamacpp", label: "Local — llama.cpp" },
                { value: "ollama",   label: "Local — Ollama" },
                { value: "openai",   label: "Cloud — OpenAI" },
              ]}
            />
          </Field>
        </Section>

        {/* llama.cpp config */}
        {provider === "llamacpp" && (
          <Section title="llama.cpp">
            <Field label="Directorio de modelos" hint="Raíz donde se escanean los .gguf (subdirectorios incluidos)">
              <div className="flex gap-2">
                <Input
                  value={config.LLAMACPP_MODELS_DIR ?? ""}
                  onChange={() => {}}
                  placeholder="C:\Users\...\Models\llamacpp"
                  mono
                  readOnly
                />
                <button
                  type="button"
                  onClick={chooseModelsDir}
                  className="btn-ghost px-2.5 py-2 shrink-0 flex items-center gap-1 text-xs"
                  title="Seleccionar carpeta de modelos"
                >
                  <FolderOpen size={13} />
                </button>
              </div>
            </Field>
            <Field label="llama-server.exe" hint="Path to the llama-server executable">
              <div className="flex gap-2">
                <Input
                  value={resolvedLlamacppExecutable}
                  onChange={() => {}}
                  placeholder="C:\path\to\llama-server.exe"
                  mono
                  readOnly
                />
                <button
                  type="button"
                  onClick={chooseLlamaServerExe}
                  className="btn-ghost px-2.5 py-2 shrink-0 flex items-center gap-1 text-xs"
                  title="Seleccionar llama-server.exe"
                >
                  <FileSearch size={13} />
                </button>
                <button
                  type="button"
                  onClick={installOrUpdateLlamacpp}
                  disabled={installerBusy || (installerStatus?.supported === false)}
                  className="btn-ghost px-2.5 py-2 shrink-0 flex items-center gap-1 text-xs disabled:opacity-40"
                  title={
                    installerStatus?.update_available
                      ? "Actualizar llama.cpp"
                      : "Instalar llama.cpp"
                  }
                >
                  <Download size={13} className={installerBusy ? "animate-bounce" : ""} />
                  {installerBusy
                    ? "Procesando..."
                    : installerStatus?.update_available
                      ? "Actualizar llama.cpp"
                      : "Instalar llama.cpp"}
                </button>
              </div>
              <p className="text-[10px] text-muted mt-1">
                {installerStatus?.supported === false
                  ? (installerStatus.reason || "Instalador no disponible")
                  : installerStatus?.update_available
                    ? `Nueva versión disponible: ${installerStatus.latest_version} (instalada: ${installerStatus.installed_version || "desconocida"})`
                    : installerStatus?.installed
                      ? `llama.cpp instalado${installerStatus.installed_version ? ` (${installerStatus.installed_version})` : ""}`
                      : "llama.cpp no detectado. Podés instalarlo automáticamente con el botón."}
              </p>
            </Field>
            <Field
              label="Model (.gguf)"
              hint={ggufModels.length === 0 ? "No se detectaron modelos todavía. Usá ↻ para reanalizar." : `${ggufModels.length} modelos encontrados`}
            >
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <select
                    value={config.LLAMACPP_MODEL_PATH || ""}
                    onChange={(e) => {
                      const selectedPath = e.target.value;
                      set("LLAMACPP_MODEL_PATH", selectedPath);
                      const model = ggufModels.find((m) => m.path === selectedPath);
                      if (model) set("LLAMACPP_MODEL_ALIAS", model.alias);
                    }}
                    className="input-field w-full px-3 py-2 text-xs font-mono appearance-none cursor-pointer pr-8"
                  >
                    {modelOptions.map((o) => (
                      <option key={o.value || "__empty__"} value={o.value} className="bg-surface">
                        {o.label}
                      </option>
                    ))}
                  </select>
                  <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted text-xs">▼</div>
                </div>
                <button
                  onClick={refreshGgufModels}
                  disabled={loadingModels}
                  className="btn-ghost px-2.5 py-2 shrink-0 flex items-center gap-1 text-xs"
                  title="Escanear modelos GGUF disponibles"
                >
                  <RefreshCw size={13} className={loadingModels ? "animate-spin" : ""} />
                </button>
              </div>
              <p className="text-[10px] text-muted font-mono truncate mt-1">{config.LLAMACPP_MODEL_PATH || "Sin modelo seleccionado"}</p>
            </Field>
            <Field label="Model alias" hint="Nombre corto del modelo (auto-completado al seleccionar)">
              <Input
                value={config.LLAMACPP_MODEL_ALIAS}
                onChange={(v) => set("LLAMACPP_MODEL_ALIAS", v)}
                placeholder="qwen3.5-35b-a3b"
              />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Host">
                <Input value={config.LLAMACPP_HOST} onChange={(v) => set("LLAMACPP_HOST", v)} placeholder="127.0.0.1" mono />
              </Field>
              <Field label="Port">
                <Input value={config.LLAMACPP_PORT} onChange={(v) => set("LLAMACPP_PORT", v)} placeholder="8080" type="number" mono />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Context size">
                <Input value={config.LLAMACPP_CONTEXT_SIZE} onChange={(v) => set("LLAMACPP_CONTEXT_SIZE", v)} placeholder="32768" type="number" mono />
              </Field>
              <Field label="GPU layers (-ngl)">
                <Input value={config.LLAMACPP_N_GPU_LAYERS} onChange={(v) => set("LLAMACPP_N_GPU_LAYERS", v)} placeholder="999" type="number" mono />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Field label="KV cache type K">
                <Input value={config.LLAMACPP_CACHE_TYPE_K} onChange={(v) => set("LLAMACPP_CACHE_TYPE_K", v)} placeholder="q8_0" mono />
              </Field>
              <Field label="KV cache type V">
                <Input value={config.LLAMACPP_CACHE_TYPE_V} onChange={(v) => set("LLAMACPP_CACHE_TYPE_V", v)} placeholder="q8_0" mono />
              </Field>
            </div>
            <Field label="Flash attention">
              <Toggle
                value={config.LLAMACPP_FLASH_ATTN === "true"}
                onChange={(v) => set("LLAMACPP_FLASH_ATTN", v ? "true" : "false")}
                label={config.LLAMACPP_FLASH_ATTN === "true" ? "enabled" : "disabled"}
              />
            </Field>
            <Field label="Extra args" hint="Space-separated extra flags passed to llama-server">
              <Input value={config.LLAMACPP_EXTRA_ARGS} onChange={(v) => set("LLAMACPP_EXTRA_ARGS", v)} placeholder="--threads 8" mono />
            </Field>
          </Section>
        )}

        {/* Ollama config */}
        {provider === "ollama" && (
          <Section title="Ollama">
            <Field label="Base URL">
              <Input value={config.OLLAMA_BASE_URL} onChange={(v) => set("OLLAMA_BASE_URL", v)} placeholder="http://localhost:11434" mono />
            </Field>
            <Field label="Model">
              <Input value={config.OLLAMA_MODEL} onChange={(v) => set("OLLAMA_MODEL", v)} placeholder="qwen2.5-coder:14b" mono />
            </Field>
          </Section>
        )}

        {/* OpenAI config */}
        {provider === "openai" && (
          <Section title="OpenAI">
            <Field label="API Key">
              <Input value={config.OPENAI_API_KEY ?? ""} onChange={(v) => set("OPENAI_API_KEY", v)} placeholder="sk-…" type="password" />
            </Field>
            <Field label="Model">
              <Input value={config.OPENAI_MODEL} onChange={(v) => set("OPENAI_MODEL", v)} placeholder="gpt-4o-mini" mono />
            </Field>
          </Section>
        )}

        {/* Supabase */}
        {config.VECTOR_DB_PROVIDER === "supabase" && (
          <Section title="Supabase">
            <Field label="URL">
              <Input value={config.SUPABASE_URL ?? ""} onChange={(v) => set("SUPABASE_URL", v)} placeholder="https://xxx.supabase.co" mono />
            </Field>
            <Field label="API Key">
              <Input value={config.SUPABASE_KEY ?? ""} onChange={(v) => set("SUPABASE_KEY", v)} placeholder="eyJh…" type="password" />
            </Field>
          </Section>
        )}

        {/* n8n */}
        <Section title="n8n (optional orchestration)">
          <Field label="Enable n8n">
            <Toggle
              value={config.N8N_ENABLED === "true"}
              onChange={(v) => set("N8N_ENABLED", v ? "true" : "false")}
              label={config.N8N_ENABLED === "true" ? "enabled — routes chat through n8n" : "disabled — direct LLM mode"}
            />
          </Field>
          {config.N8N_ENABLED === "true" && (
            <Field label="Webhook URL">
              <Input
                value={config.N8N_WEBHOOK_URL ?? ""}
                onChange={(v) => set("N8N_WEBHOOK_URL", v)}
                placeholder="http://127.0.0.1:5678/webhook/chat"
                mono
              />
            </Field>
          )}
        </Section>

      </div>

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-raised border border-border px-4 py-2 rounded-lg text-xs text-primary shadow-xl animate-fadeIn z-50">
          {toast}
        </div>
      )}
    </div>
  );
}
