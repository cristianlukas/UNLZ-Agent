import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Download,
  Loader2,
  RefreshCw,
  Search,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import {
  applyHubDownload,
  cancelHubDownload,
  checkHubUpdate,
  getHubCatalog,
  listHubDownloads,
  searchHubModels,
  startHubDownload,
  streamHubDownload,
} from "../lib/api";
import type {
  HardwareProfile,
  HubCatalogResponse,
  HubDownload,
  HubModel,
  HubSearchResult,
  HubUpdateNotification,
} from "../lib/types";
import { useStore } from "../lib/store";

// ─── Constants ────────────────────────────────────────────────────────────────

const TIER_LABELS: Record<string, string> = {
  entry: "Básico",
  mid: "Intermedio",
  high: "Alto",
  ultra: "Ultra",
};

const TIER_COLORS: Record<string, string> = {
  entry: "text-emerald-400 border-emerald-400/30 bg-emerald-400/10",
  mid: "text-blue-400 border-blue-400/30 bg-blue-400/10",
  high: "text-violet-400 border-violet-400/30 bg-violet-400/10",
  ultra: "text-amber-400 border-amber-400/30 bg-amber-400/10",
};

const BADGE_STYLE: Record<string, string> = {
  new: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/25",
  recommended: "bg-violet-500/15 text-violet-300 border border-violet-500/25",
  popular: "bg-blue-500/15 text-blue-300 border border-blue-500/25",
};

const FAMILY_ICONS: Record<string, string> = {
  qwen3: "🔮",
  gemma3: "💎",
  llama3: "🦙",
  mistral: "🌪️",
  "deepseek-r1": "🧠",
};

const TAB_LABELS = ["Recomendados", "Catálogo", "Descargando"] as const;
type Tab = (typeof TAB_LABELS)[number];

// ─── Score bar ────────────────────────────────────────────────────────────────

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-muted w-14 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-accent to-accent-light transition-all duration-500"
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="text-[10px] text-muted w-6 text-right">{value}</span>
    </div>
  );
}

// ─── Hardware banner ──────────────────────────────────────────────────────────

function HardwareBanner({ hw }: { hw: HardwareProfile }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl bg-raised border border-border text-sm">
      <div className="text-lg">🖥️</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          {hw.vram_gb > 0 ? (
            <span className="text-secondary">
              GPU <span className="text-primary font-medium">{hw.vram_gb} GB VRAM</span>
            </span>
          ) : (
            <span className="text-secondary">Sin GPU dedicada</span>
          )}
          <span className="text-border">·</span>
          <span className="text-secondary">
            RAM <span className="text-primary font-medium">{hw.ram_gb.toFixed(0)} GB</span>
          </span>
        </div>
      </div>
      <span className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border ${TIER_COLORS[hw.tier]}`}>
        {TIER_LABELS[hw.tier]}
      </span>
    </div>
  );
}

// ─── Update notification banner ───────────────────────────────────────────────

function UpdateBanner({
  update,
  onUseNew,
  onSkip,
  onSnooze,
}: {
  update: HubUpdateNotification;
  onUseNew: () => void;
  onSkip: () => void;
  onSnooze: () => void;
}) {
  return (
    <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-amber-400/8 border border-amber-400/25 text-sm animate-fadeIn">
      <Sparkles size={16} className="text-amber-400 shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-primary font-medium text-sm">{update.message}</p>
        <p className="text-muted text-xs mt-0.5">
          {update.recommended.name} · {update.recommended.size_label} · {update.recommended.file_gb.toFixed(1)} GB
        </p>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <button
          onClick={onUseNew}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium btn-primary"
        >
          Descargar <ArrowRight size={11} />
        </button>
        <button
          onClick={onSnooze}
          title="Preguntar al próximo inicio"
          className="p-1.5 rounded-lg btn-ghost text-muted hover:text-primary"
        >
          <Clock size={13} />
        </button>
        <button
          onClick={onSkip}
          title="No mostrar para este modelo"
          className="p-1.5 rounded-lg btn-ghost text-muted hover:text-red-400"
        >
          <X size={13} />
        </button>
      </div>
    </div>
  );
}

// ─── Download progress modal ──────────────────────────────────────────────────

function DownloadModal({
  model,
  downloadId,
  onClose,
  onApply,
}: {
  model: HubModel;
  downloadId: string;
  onClose: () => void;
  onApply: () => void;
}) {
  const [info, setInfo] = useState<HubDownload | null>(null);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;
    (async () => {
      try {
        for await (const ev of streamHubDownload(downloadId)) {
          if (cancelled.current) break;
          setInfo(ev);
          if (ev.status === "done" || ev.status === "error" || ev.status === "cancelled") break;
        }
      } catch (e) {
        setInfo((prev) => prev ? { ...prev, status: "error", error: String(e) } : null);
      }
    })();
    return () => { cancelled.current = true; };
  }, [downloadId]);

  async function handleApply() {
    setApplying(true);
    setApplyError(null);
    try {
      await applyHubDownload(downloadId);
      onApply();
    } catch (e) {
      setApplyError(String(e));
      setApplying(false);
    }
  }

  async function handleCancel() {
    cancelled.current = true;
    await cancelHubDownload(downloadId);
    onClose();
  }

  const pct = info ? Math.round(info.progress * 100) : 0;
  const done = info?.status === "done";
  const errored = info?.status === "error";
  const isActive = info?.status === "downloading" || info?.status === "starting";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fadeIn">
      <div className="w-full max-w-md mx-4 rounded-2xl glass border border-border shadow-2xl p-6">
        {/* Header */}
        <div className="flex items-start gap-3 mb-5">
          <div className="text-2xl">{FAMILY_ICONS[model.family] ?? "📦"}</div>
          <div className="flex-1 min-w-0">
            <h3 className="text-primary font-semibold text-base">{model.name}</h3>
            <p className="text-muted text-xs mt-0.5">{model.filename}</p>
          </div>
          {!isActive && (
            <button onClick={onClose} className="p-1 rounded text-muted hover:text-primary">
              <X size={16} />
            </button>
          )}
        </div>

        {/* Progress bar */}
        <div className="mb-4">
          <div className="flex justify-between text-xs text-muted mb-1.5">
            <span>
              {done ? "Descarga completa" : errored ? "Error" : `${pct}%`}
            </span>
            {info && !done && !errored && (
              <span>
                {info.downloaded_gb.toFixed(2)} / {info.total_gb.toFixed(2)} GB
                {info.speed_mbps > 0 && ` · ${info.speed_mbps.toFixed(1)} MB/s`}
                {info.eta_s > 0 && ` · ${info.eta_s < 60 ? `${info.eta_s}s` : `${Math.round(info.eta_s / 60)}min`}`}
              </span>
            )}
          </div>
          <div className="h-2 bg-white/5 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                done
                  ? "bg-emerald-400"
                  : errored
                  ? "bg-red-400"
                  : "bg-gradient-to-r from-accent to-accent-light"
              }`}
              style={{ width: `${done ? 100 : errored ? 100 : pct}%` }}
            />
          </div>
        </div>

        {/* Error message */}
        {errored && info?.error && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-red-400/10 border border-red-400/25 text-xs text-red-300">
            {info.error}
          </div>
        )}

        {/* Apply error */}
        {applyError && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-red-400/10 border border-red-400/25 text-xs text-red-300">
            {applyError}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 justify-end">
          {isActive && (
            <button onClick={handleCancel} className="px-4 py-2 rounded-lg text-sm btn-ghost">
              Cancelar
            </button>
          )}
          {done && (
            <>
              <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm btn-ghost">
                Cerrar
              </button>
              <button
                onClick={handleApply}
                disabled={applying}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm btn-primary"
              >
                {applying ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                Usar este modelo
              </button>
            </>
          )}
          {errored && (
            <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm btn-ghost">
              Cerrar
            </button>
          )}
          {!isActive && !done && !errored && (
            <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm btn-ghost">
              Cerrar
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Model card ───────────────────────────────────────────────────────────────

function ModelCard({
  model,
  highlight,
  highlightLabel,
  onDownload,
}: {
  model: HubModel;
  highlight?: boolean;
  highlightLabel?: string;
  onDownload: (m: HubModel) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`rounded-xl border transition-all duration-150 ${
        highlight
          ? "border-accent/35 bg-accent/5 glow-accent-sm"
          : "border-border bg-raised hover:border-border-strong"
      }`}
    >
      <div className="p-4">
        {/* Top row */}
        <div className="flex items-start gap-3">
          <div className="text-xl shrink-0 mt-0.5">{FAMILY_ICONS[model.family] ?? "📦"}</div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-primary font-semibold text-sm">{model.name}</span>
              {highlightLabel && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/15 text-accent border border-accent/25 font-medium">
                  {highlightLabel}
                </span>
              )}
              {model.badge && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${BADGE_STYLE[model.badge]}`}>
                  {model.badge === "new" ? "Nuevo" : model.badge === "recommended" ? "Recomendado" : "Popular"}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span className={`text-[10px] px-2 py-0.5 rounded-full border ${TIER_COLORS[model.tier]}`}>
                {TIER_LABELS[model.tier]}
              </span>
              <span className="text-muted text-[11px]">{model.quant}</span>
              <span className="text-border">·</span>
              <span className="text-muted text-[11px]">{model.file_gb.toFixed(1)} GB</span>
              <span className="text-border">·</span>
              <span className="text-muted text-[11px]">{(model.context / 1000).toFixed(0)}k ctx</span>
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => setExpanded((v) => !v)}
              className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-white/5 transition-colors"
            >
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            <button
              onClick={() => onDownload(model)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium btn-primary"
            >
              <Download size={12} /> Descargar
            </button>
          </div>
        </div>

        {/* Scores */}
        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5">
          <ScoreBar label="Chat" value={model.tasks.chat} />
          <ScoreBar label="Código" value={model.tasks.code} />
          <ScoreBar label="Razonamiento" value={model.tasks.reasoning} />
          <ScoreBar label="Instrucción" value={model.tasks.instruct} />
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-border px-4 py-3 text-xs text-muted space-y-1">
          <div className="flex justify-between">
            <span>VRAM mínimo</span>
            <span className="text-secondary">{model.vram_gb} GB</span>
          </div>
          <div className="flex justify-between">
            <span>RAM mínima (CPU)</span>
            <span className="text-secondary">{model.ram_gb} GB</span>
          </div>
          <div className="flex justify-between">
            <span>Licencia</span>
            <span className="text-secondary">{model.license}</span>
          </div>
          <div className="flex justify-between">
            <span>Publicado</span>
            <span className="text-secondary">{model.release}</span>
          </div>
          <div className="flex justify-between">
            <span>Repositorio HF</span>
            <span className="text-accent-light truncate max-w-[200px]">{model.hf_repo}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Active download row ──────────────────────────────────────────────────────

function DownloadRow({
  dl,
  onResume,
  onApply,
}: {
  dl: HubDownload;
  onResume: () => void;
  onApply: () => void;
}) {
  const pct = Math.round(dl.progress * 100);
  const statusColors = {
    starting: "text-muted",
    downloading: "text-accent-light",
    done: "text-emerald-400",
    error: "text-red-400",
    cancelled: "text-muted",
  };

  return (
    <div className="rounded-xl border border-border bg-raised p-4">
      <div className="flex items-center gap-3 mb-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-primary font-medium truncate">{dl.filename}</p>
          <p className={`text-xs mt-0.5 ${statusColors[dl.status]}`}>
            {dl.status === "downloading" && `${pct}% · ${dl.downloaded_gb.toFixed(2)}/${dl.total_gb.toFixed(2)} GB · ${dl.speed_mbps.toFixed(1)} MB/s`}
            {dl.status === "done" && "Completado"}
            {dl.status === "error" && `Error: ${dl.error}`}
            {dl.status === "cancelled" && "Cancelado"}
            {dl.status === "starting" && "Iniciando…"}
          </p>
        </div>
        {dl.status === "error" || dl.status === "cancelled" ? (
          <button onClick={onResume} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs btn-ghost">
            <RefreshCw size={12} /> Reintentar
          </button>
        ) : dl.status === "done" ? (
          <button onClick={onApply} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs btn-primary">
            <Check size={12} /> Usar
          </button>
        ) : (
          <Loader2 size={15} className="animate-spin text-accent shrink-0" />
        )}
      </div>
      {(dl.status === "downloading" || dl.status === "starting") && (
        <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-accent to-accent-light transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

// ─── Main view ────────────────────────────────────────────────────────────────

export default function ModelHubView() {
  const {
    setHubUpdateNotification,
    hubUpdateNotification,
    skippedHubModelIds,
    snoozedHubUntil,
    skipHubModel,
    snoozeHubUpdate,
    setView,
  } = useStore();

  const [tab, setTab] = useState<Tab>("Recomendados");
  const [catalog, setCatalog] = useState<HubCatalogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [familyFilter, setFamilyFilter] = useState<string>("all");

  // Active downloads tracked locally (SSE is inside modal)
  const [downloads, setDownloads] = useState<HubDownload[]>([]);

  // Modal state
  const [activeDownloadId, setActiveDownloadId] = useState<string | null>(null);
  const [activeDownloadModel, setActiveDownloadModel] = useState<HubModel | null>(null);

  // Visible update notification (filtered by skipped/snoozed)
  const [visibleUpdate, setVisibleUpdate] = useState<HubUpdateNotification | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<HubSearchResult[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const prevDownloadStatus = useRef<Record<string, string>>({});

  // ── Load catalog ─────────────────────────────────────────────────────────────

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [catData, updateData] = await Promise.all([
        getHubCatalog(),
        checkHubUpdate().catch(() => ({ update: null, current_model: "" })),
      ]);
      setCatalog(catData);

      const upd = updateData.update;
      if (upd) {
        setHubUpdateNotification(upd);
        // Show if not skipped/snoozed
        const isSnoozed = snoozedHubUntil !== null && Date.now() < snoozedHubUntil;
        const isSkipped = skippedHubModelIds.includes(upd.recommended.id);
        if (!isSnoozed && !isSkipped) {
          setVisibleUpdate(upd);
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const rows = await listHubDownloads();
        if (!cancelled) setDownloads(rows);
      } catch {
        // ignore polling failures
      }
    };
    tick();
    const id = window.setInterval(tick, 1200);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    const nextMap: Record<string, string> = {};
    for (const dl of downloads) {
      nextMap[dl.id] = dl.status;
      const prev = prevDownloadStatus.current[dl.id];
      if (dl.status === "done" && prev !== "done") {
        setToast(`Descarga completa: ${dl.filename}`);
        window.setTimeout(() => setToast(null), 4500);
      }
    }
    prevDownloadStatus.current = nextMap;
  }, [downloads]);

  // ── Download handler ──────────────────────────────────────────────────────────

  async function beginDownload(opts: {
    hf_repo: string;
    filename: string;
    fileGb?: number;
    displayName?: string;
    family?: string;
    quant?: string;
  }) {
    const { download_id } = await startHubDownload({
      hf_repo: opts.hf_repo,
      filename: opts.filename,
    });

    const pseudoModel: HubModel = {
      id: `hf:${opts.hf_repo}:${opts.filename}`,
      family: opts.family ?? "custom",
      name: opts.displayName ?? opts.filename,
      version: "",
      size_label: "",
      hf_repo: opts.hf_repo,
      filename: opts.filename,
      quant: opts.quant ?? "unknown",
      vram_gb: 0,
      ram_gb: 0,
      file_gb: opts.fileGb ?? 0,
      context: 0,
      tier: "entry",
      tasks: { chat: 0, code: 0, reasoning: 0, instruct: 0 },
      license: "unknown",
      release: "",
      recommended_for: [],
      badge: null,
    };

    setActiveDownloadId(download_id);
    setActiveDownloadModel(pseudoModel);
  }

  async function handleDownload(model: HubModel) {
    try {
      await beginDownload({
        hf_repo: model.hf_repo,
        filename: model.filename,
        fileGb: model.file_gb,
        displayName: model.name,
        family: model.family,
        quant: model.quant,
      });
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleSearch() {
    const q = searchInput.trim();
    if (!q) return;
    setSearching(true);
    setSearchError(null);
    try {
      const data = await searchHubModels(q, 8);
      setSearchResults(data.results ?? []);
      if (!data.results || data.results.length === 0) {
        setSearchError("No encontré modelos GGUF para esa búsqueda.");
      }
    } catch (e) {
      setSearchError(String(e));
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }

  async function handleApplyFromRow(downloadId: string) {
    try {
      await applyHubDownload(downloadId);
      setToast("Modelo aplicado y servidor reiniciado.");
      window.setTimeout(() => setToast(null), 4500);
    } catch (e) {
      setError(String(e));
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3 text-muted">
          <Loader2 size={28} className="animate-spin text-accent" />
          <p className="text-sm">Cargando catálogo…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center h-full p-8">
        <div className="flex flex-col items-center gap-3 text-center max-w-sm">
          <AlertTriangle size={28} className="text-amber-400" />
          <p className="text-sm text-secondary font-medium">No se pudo cargar el catálogo</p>
          <p className="text-xs text-muted">{error}</p>
          <button onClick={load} className="mt-2 flex items-center gap-2 px-4 py-2 rounded-lg text-sm btn-ghost">
            <RefreshCw size={14} /> Reintentar
          </button>
        </div>
      </div>
    );
  }

  const hw = catalog!.hardware;
  const recs = catalog!.recommendations;
  const allModels = catalog!.catalog;

  // Family filter options
  const families = Array.from(new Set(allModels.map((m) => m.family))).sort();

  const filteredModels =
    familyFilter === "all" ? allModels : allModels.filter((m) => m.family === familyFilter);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-6 pt-5 pb-4 border-b border-border shrink-0">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-primary flex items-center gap-2">
              <Sparkles size={16} className="text-accent" />
              Model Hub
            </h2>
            <p className="text-xs text-muted mt-0.5">Descargá y gestioná modelos GGUF locales</p>
          </div>
          <button
            onClick={load}
            className="p-2 rounded-lg text-muted hover:text-primary hover:bg-raised transition-colors"
            title="Actualizar"
          >
            <RefreshCw size={15} />
          </button>
        </div>

        {/* Hardware banner */}
        <HardwareBanner hw={hw} />

        {/* Update notification */}
        {visibleUpdate && (
          <div className="mt-3">
            <UpdateBanner
              update={visibleUpdate}
              onUseNew={() => {
                setVisibleUpdate(null);
                setTab("Recomendados");
                handleDownload(visibleUpdate.recommended);
              }}
              onSkip={() => {
                skipHubModel(visibleUpdate.recommended.id);
                setVisibleUpdate(null);
              }}
              onSnooze={() => {
                snoozeHubUpdate();
                setVisibleUpdate(null);
              }}
            />
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 mt-4 bg-base/60 rounded-xl p-1">
          {TAB_LABELS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-medium transition-colors relative ${
                tab === t
                  ? "bg-accent/15 text-accent border border-accent/25"
                  : "text-muted hover:text-secondary"
              }`}
            >
              {t}
              {t === "Descargando" && downloads.length > 0 && (
                <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-accent text-[8px] font-bold text-white flex items-center justify-center">
                  {downloads.length}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scroll px-6 py-4 space-y-3">
        {/* ── Recomendados tab ── */}
        {tab === "Recomendados" && (
          <>
            {recs.all_fitting.length === 0 ? (
              <div className="py-12 text-center text-muted text-sm">
                <p>Sin modelos compatibles con tu hardware.</p>
                <p className="text-xs mt-1 opacity-70">Probá con el catálogo completo.</p>
              </div>
            ) : (
              <>
                {recs.ideal && (
                  <ModelCard
                    model={recs.ideal}
                    highlight
                    highlightLabel="⭐ Ideal"
                    onDownload={handleDownload}
                  />
                )}
                {recs.balanced && recs.balanced.id !== recs.ideal?.id && (
                  <ModelCard
                    model={recs.balanced}
                    highlightLabel="⚖️ Balanceado"
                    onDownload={handleDownload}
                  />
                )}
                {recs.fast && recs.fast.id !== recs.ideal?.id && recs.fast.id !== recs.balanced?.id && (
                  <ModelCard
                    model={recs.fast}
                    highlightLabel="⚡ Rápido"
                    onDownload={handleDownload}
                  />
                )}
              </>
            )}
          </>
        )}

        {/* ── Catálogo tab ── */}
        {tab === "Catálogo" && (
          <>
            <div className="rounded-xl border border-border bg-raised p-3 space-y-2">
              <div className="text-xs text-muted">
                Buscador Hugging Face: pegá URL (`https://huggingface.co/org/repo`) o nombre del modelo.
              </div>
              <div className="flex gap-2">
                <input
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void handleSearch();
                  }}
                  className="flex-1 bg-base border border-border rounded-lg px-3 py-2 text-sm text-primary outline-none focus:border-accent/40"
                  placeholder="Ej: qwen3.6 27b q5_k_p o https://huggingface.co/HauhauCS/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive"
                />
                <button
                  onClick={() => void handleSearch()}
                  disabled={searching || !searchInput.trim()}
                  className="px-3 py-2 rounded-lg text-sm btn-primary disabled:opacity-60"
                >
                  <span className="inline-flex items-center gap-1.5">
                    {searching ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                    Buscar
                  </span>
                </button>
              </div>
              {searchError && <div className="text-xs text-red-300">{searchError}</div>}
            </div>

            {searchResults.length > 0 && (
              <div className="rounded-xl border border-border bg-raised p-3 space-y-3">
                <div className="text-xs font-medium text-secondary">Resultados de búsqueda</div>
                {searchResults.map((r) => (
                  <div key={r.repo} className="rounded-lg border border-border p-3 bg-base/30">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="min-w-0">
                        <div className="text-sm text-primary font-medium truncate">{r.title}</div>
                        <div className="text-[11px] text-muted truncate">{r.repo}</div>
                      </div>
                      <div className="text-[11px] text-muted shrink-0">
                        {r.gguf_count} GGUF · {r.downloads.toLocaleString()} descargas
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      {r.files.slice(0, 6).map((f) => (
                        <div key={`${r.repo}:${f.filename}`} className="flex items-center gap-2 rounded-md border border-border/60 px-2 py-1.5">
                          <div className="flex-1 min-w-0">
                            <div className="text-xs text-primary truncate">{f.filename}</div>
                            <div className="text-[10px] text-muted">
                              {f.quant} {f.size_gb !== null ? `· ${f.size_gb.toFixed(2)} GB` : ""}
                            </div>
                          </div>
                          <button
                            onClick={() =>
                              void beginDownload({
                                hf_repo: r.repo,
                                filename: f.filename,
                                fileGb: f.size_gb ?? 0,
                                displayName: r.title,
                                family: "custom",
                                quant: f.quant,
                              })
                            }
                            className="px-2.5 py-1 rounded-md text-[11px] btn-primary"
                          >
                            Descargar
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Family filter */}
            <div className="flex gap-1.5 flex-wrap pb-1">
              <button
                onClick={() => setFamilyFilter("all")}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                  familyFilter === "all"
                    ? "bg-accent/15 text-accent border-accent/30"
                    : "border-border text-muted hover:text-primary"
                }`}
              >
                Todos
              </button>
              {families.map((f) => (
                <button
                  key={f}
                  onClick={() => setFamilyFilter(f)}
                  className={`flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                    familyFilter === f
                      ? "bg-accent/15 text-accent border-accent/30"
                      : "border-border text-muted hover:text-primary"
                  }`}
                >
                  {FAMILY_ICONS[f] ?? "📦"} {f}
                </button>
              ))}
            </div>

            {filteredModels.map((m) => (
              <ModelCard key={m.id} model={m} onDownload={handleDownload} />
            ))}
          </>
        )}

        {/* ── Descargando tab ── */}
        {tab === "Descargando" && (
          <>
            {downloads.length === 0 ? (
              <div className="py-12 text-center text-muted text-sm">
                <Download size={28} className="mx-auto mb-3 opacity-30" />
                <p>Sin descargas activas</p>
                <p className="text-xs mt-1 opacity-60">Las descargas aparecen acá automáticamente.</p>
              </div>
            ) : (
              downloads.map((dl) => (
                <DownloadRow
                  key={dl.id}
                  dl={dl}
                  onApply={() => void handleApplyFromRow(dl.id)}
                  onResume={() => {
                    // Find original model by filename to re-download
                    const m = allModels.find((x) => x.filename === dl.filename);
                    if (m) {
                      void handleDownload(m);
                    } else {
                      void beginDownload({
                        hf_repo: dl.hf_repo,
                        filename: dl.filename,
                        fileGb: dl.total_gb,
                        displayName: dl.filename,
                      });
                    }
                  }}
                />
              ))
            )}
          </>
        )}
      </div>

      {/* Download modal */}
      {activeDownloadId && activeDownloadModel && (
        <DownloadModal
          model={activeDownloadModel}
          downloadId={activeDownloadId}
          onClose={() => {
            setActiveDownloadId(null);
            setActiveDownloadModel(null);
          }}
          onApply={() => {
            setActiveDownloadId(null);
            setActiveDownloadModel(null);
            // Update downloads list
            setDownloads((prev) =>
              prev.map((d) => (d.id === activeDownloadId ? { ...d, status: "done" } : d))
            );
          }}
        />
      )}

      {toast && (
        <div className="fixed bottom-5 right-5 z-40 px-3 py-2 rounded-lg border border-emerald-500/25 bg-emerald-500/10 text-emerald-300 text-xs">
          {toast}
        </div>
      )}
    </div>
  );
}
