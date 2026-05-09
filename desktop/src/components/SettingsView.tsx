import { useEffect, useState } from "react";
import { Save, RotateCcw, Terminal, CheckCircle2, AlertTriangle } from "lucide-react";
import { useStore } from "../lib/store";
import {
  getSettings,
  saveSettings,
  getHarnessesStatus,
  getHealthCenter,
  getOpencodeWarmupStatus,
} from "../lib/api";
import type { HarnessesStatus, OpencodeWarmupStatus } from "../lib/api";

type Config = Record<string, string>;

const DEFAULTS: Config = {
  AGENT_LANGUAGE: "es",
  HARNESS_OPENCODE_BIN: "",
  AGENT_EXECUTION_MODE: "autonomous",
  WINDOW_CONTROLS_STYLE: "windows",
  WINDOW_CONTROLS_SIDE: "right",
  WINDOW_CONTROLS_ORDER: "minimize,maximize,close",
};

function field(cfg: Config, key: string): string {
  return cfg[key] ?? DEFAULTS[key] ?? "";
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-surface overflow-hidden">
      <div className="px-4 py-3 border-b border-border bg-raised/50">
        <h3 className="text-sm font-semibold text-primary">{title}</h3>
      </div>
      <div className="p-4 space-y-4">{children}</div>
    </div>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-4">
      <div className="w-44 shrink-0 pt-1.5">
        <p className="text-xs font-medium text-secondary">{label}</p>
        {hint && <p className="text-[10px] text-muted mt-0.5 leading-snug">{hint}</p>}
      </div>
      <div className="flex-1">{children}</div>
    </div>
  );
}

// ─── Harness status badge ─────────────────────────────────────────────────────

function HarnessBadge({ status }: { status: HarnessesStatus | null }) {
  if (!status) return null;
  const oc = status.options.find((o) => o.id === "opencode");
  if (!oc) return null;
  if (oc.installed) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-green-400 bg-green-400/10 px-2 py-0.5 rounded-full">
        <CheckCircle2 size={10} /> instalado {oc.version ? `v${oc.version}` : ""}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full">
      <AlertTriangle size={10} /> no encontrado
    </span>
  );
}

// ─── SettingsView ─────────────────────────────────────────────────────────────

export default function SettingsView() {
  const { devMode, setDevMode, uiMode, setUiMode } = useStore();
  const [cfg, setCfg] = useState<Config>(DEFAULTS);
  const [saved, setSaved] = useState(false);
  const [harness, setHarness] = useState<HarnessesStatus | null>(null);
  const [healthCenter, setHealthCenter] = useState<Record<string, unknown> | null>(null);
  const [warmup, setWarmup] = useState<OpencodeWarmupStatus | null>(null);

  useEffect(() => {
    getSettings().then((s) => setCfg({ ...DEFAULTS, ...s }));
    getHarnessesStatus().then(setHarness).catch(() => {});
    getHealthCenter().then(setHealthCenter).catch(() => {});
    getOpencodeWarmupStatus().then(setWarmup).catch(() => {});
    const id = window.setInterval(() => { getOpencodeWarmupStatus().then(setWarmup).catch(() => {}); }, 3000);
    return () => window.clearInterval(id);
  }, []);

  function set(key: string, value: string) {
    setCfg((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    await saveSettings(cfg);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  function handleReset() {
    setCfg(DEFAULTS);
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
        <div>
          <h2 className="text-base font-semibold text-primary">Configuración</h2>
          <p className="text-xs text-muted mt-0.5">Ajustes del agente opencode</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleReset} className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-sm">
            <RotateCcw size={13} /> Restaurar
          </button>
          <button
            onClick={handleSave}
            className={`flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-lg font-medium transition-colors ${
              saved ? "bg-green-500/20 text-green-400 border border-green-500/30" : "btn-primary"
            }`}
          >
            <Save size={13} /> {saved ? "Guardado" : "Guardar"}
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5 custom-scroll">

        {/* opencode section */}
        <Section title="opencode">
          <Row
            label="Binario opencode"
            hint="Definido por el desarrollador. Solo lectura en esta build."
          >
            <div className="flex gap-2">
              <input
                value={field(cfg, "HARNESS_OPENCODE_BIN")}
                readOnly
                placeholder="opencode (auto-detectado)"
                className="flex-1 bg-base border border-border rounded-lg px-3 py-1.5 text-xs text-primary font-mono outline-none focus:border-accent/50 transition-colors placeholder-muted"
              />
            </div>
            <div className="flex items-center gap-3 mt-2">
              <HarnessBadge status={harness} />
            </div>
          </Row>

          <Row
            label="Modo de ejecución"
            hint="Bloqueado en autonomous por diseño de esta app."
          >
            <input
              value="autonomous"
              readOnly
              className="w-full bg-base border border-border rounded-lg px-3 py-1.5 text-xs text-primary font-mono outline-none"
            />
          </Row>
        </Section>

        {/* General section */}
        <Section title="General">
          <Row label="Modo de interfaz" hint="Simple para principiantes, Avanzado para controles completos.">
            <select
              value={uiMode}
              onChange={(e) => setUiMode((e.target.value as "simple" | "advanced"))}
              className="w-full bg-base border border-border rounded-lg px-3 py-1.5 text-xs text-primary outline-none focus:border-accent/50 transition-colors"
            >
              <option value="simple">Simple (recomendado)</option>
              <option value="advanced">Avanzado</option>
            </select>
          </Row>

          <Row label="Idioma del agente">
            <select
              value={field(cfg, "AGENT_LANGUAGE")}
              onChange={(e) => set("AGENT_LANGUAGE", e.target.value)}
              className="w-full bg-base border border-border rounded-lg px-3 py-1.5 text-xs text-primary outline-none focus:border-accent/50 transition-colors"
            >
              <option value="es">Español</option>
              <option value="en">English</option>
            </select>
          </Row>

          <Row label="Modo desarrollador" hint="Habilita la vista Dev Log en el panel lateral.">
            <label className="flex items-center gap-2 text-xs text-secondary cursor-pointer">
              <input
                type="checkbox"
                checked={devMode}
                onChange={(e) => setDevMode(e.target.checked)}
                className="accent-accent"
              />
              <Terminal size={12} className="text-muted" />
              Habilitar Dev Log
            </label>
          </Row>
        </Section>

        <Section title="Estado del agente">
          <Row label="Provider / versión">
            <p className="text-xs text-primary">
              {String(healthCenter?.provider || "opencode")} {healthCenter?.opencode_version ? `— ${String(healthCenter.opencode_version)}` : ""}
            </p>
          </Row>
          <Row label="Modelo activo">
            <p className="text-xs text-primary">{String(healthCenter?.model_alias || "(sin alias)")}</p>
          </Row>
          <Row label="RAG">
            <p className="text-xs text-primary">{healthCenter?.rag_index_ready ? "Índice listo" : "Índice no inicializado"}</p>
          </Row>
          <Row label="Warmup opencode">
            <p className="text-xs text-primary">
              {warmup?.status || "desconocido"}
              {warmup?.detail ? ` — ${warmup.detail}` : ""}
            </p>
          </Row>
        </Section>

        {/* Window controls */}
        <Section title="Controles de ventana">
          <Row label="Estilo">
            <select
              value={field(cfg, "WINDOW_CONTROLS_STYLE")}
              onChange={(e) => set("WINDOW_CONTROLS_STYLE", e.target.value)}
              className="w-full bg-base border border-border rounded-lg px-3 py-1.5 text-xs text-primary outline-none focus:border-accent/50 transition-colors"
            >
              <option value="windows">Windows</option>
              <option value="macos">macOS</option>
              <option value="minimal">Minimal</option>
            </select>
          </Row>

          <Row label="Posición">
            <select
              value={field(cfg, "WINDOW_CONTROLS_SIDE")}
              onChange={(e) => set("WINDOW_CONTROLS_SIDE", e.target.value)}
              className="w-full bg-base border border-border rounded-lg px-3 py-1.5 text-xs text-primary outline-none focus:border-accent/50 transition-colors"
            >
              <option value="right">Derecha</option>
              <option value="left">Izquierda</option>
            </select>
          </Row>

          <Row label="Orden" hint="Separado por comas.">
            <input
              value={field(cfg, "WINDOW_CONTROLS_ORDER")}
              onChange={(e) => set("WINDOW_CONTROLS_ORDER", e.target.value)}
              placeholder="minimize,maximize,close"
              className="w-full bg-base border border-border rounded-lg px-3 py-1.5 text-xs text-primary font-mono outline-none focus:border-accent/50 transition-colors placeholder-muted"
            />
          </Row>
        </Section>

      </div>
    </div>
  );
}
