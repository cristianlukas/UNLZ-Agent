import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Terminal,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import {
  devClearTraces,
  devGetLog,
  devGetTrace,
  devListTraces,
  devStreamLog,
} from "../lib/api";
import type { DevTrace, DevTraceSummary } from "../lib/api";

// ─── Log line coloring ────────────────────────────────────────────────────────

function colorLine(line: string): string {
  const l = line.toLowerCase();
  if (l.startsWith("[trace]")) return "text-cyan-300";
  if (l.includes("error") || l.includes("exception") || l.includes("traceback")) return "text-red-400";
  if (l.includes("warn")) return "text-amber-400";
  if (l.includes("[unlz]")) return "text-accent-light";
  if (l.startsWith("provider") || l.startsWith("model") || l.startsWith("harness")) return "text-blue-300";
  return "text-secondary";
}

// ─── Trace event row ──────────────────────────────────────────────────────────

function TraceEventRow({ ev }: { ev: Record<string, unknown> }) {
  const type = String(ev.type ?? "?");
  const text = String(ev.text ?? "");
  const args = ev.args as Record<string, unknown> | undefined;
  const dt = typeof ev.dt_ms_from_start === "number" ? Number(ev.dt_ms_from_start) : null;
  const duration = typeof ev.duration_ms === "number" ? Number(ev.duration_ms) : null;

  const typeColor: Record<string, string> = {
    run:        "text-violet-400",
    step:       "text-blue-400",
    chunk:      "text-emerald-400/70",
    error:      "text-red-400",
    confidence: "text-amber-400",
    done:       "text-emerald-400",
  };

  return (
    <div className={`flex items-start gap-2 text-[11px] font-mono py-0.5 ${type === "error" ? "bg-red-400/5 rounded px-1" : ""}`}>
      <span className="shrink-0 w-14 text-[10px] text-muted text-right">{dt != null ? `${dt}ms` : ""}</span>
      <span className={`shrink-0 w-20 ${typeColor[type] ?? "text-muted"}`}>{type}</span>
      <span className="flex-1 text-secondary break-all leading-relaxed">
        {text}
        {duration != null && (
          <span className="text-muted ml-2">({duration}ms)</span>
        )}
        {args && Object.keys(args).length > 0 && (
          <span className="text-muted ml-2">{JSON.stringify(args)}</span>
        )}
      </span>
    </div>
  );
}

// ─── Trace card ───────────────────────────────────────────────────────────────

function TraceCard({
  summary,
  onExpand,
}: {
  summary: DevTraceSummary;
  onExpand: (id: string) => void;
}) {
  const hasErrors = summary.error_count > 0;
  const dur = (() => {
    const fromTiming = Number(summary.timing?.total_ms ?? 0);
    if (fromTiming > 0) return fromTiming > 1000 ? `${(fromTiming / 1000).toFixed(1)}s` : `${fromTiming}ms`;
    if (!summary.started_at || !summary.finished_at) return null;
    const s = new Date(summary.started_at).getTime();
    const e = new Date(summary.finished_at).getTime();
    const ms = e - s;
    return ms > 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
  })();

  return (
    <div
      className={`rounded-xl border px-4 py-3 cursor-pointer transition-colors hover:border-border-strong ${
        hasErrors ? "border-red-400/25 bg-red-400/5" : "border-border bg-raised"
      }`}
      onClick={() => onExpand(summary.run_id)}
    >
      <div className="flex items-start gap-3">
        {hasErrors
          ? <AlertTriangle size={14} className="text-red-400 shrink-0 mt-0.5" />
          : <Zap size={14} className="text-emerald-400 shrink-0 mt-0.5" />
        }
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-mono text-primary">{summary.run_id}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-muted border border-border">
              {summary.mode}
            </span>
            {summary.mode_effective && summary.mode_effective !== summary.mode && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/25">
                → {summary.mode_effective}
              </span>
            )}
            {hasErrors && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-400/10 text-red-400 border border-red-400/20">
                {summary.error_count} error{summary.error_count > 1 ? "es" : ""}
              </span>
            )}
            <span className="text-[10px] text-muted">{summary.event_count} eventos</span>
            {dur && <span className="text-[10px] text-muted">{dur}</span>}
            {typeof summary.timing?.ttft_ms === "number" && (
              <span className="text-[10px] text-muted">TTFT {summary.timing.ttft_ms}ms</span>
            )}
          </div>
          {summary.input_preview && (
            <p className="text-[11px] text-muted mt-1 truncate">{summary.input_preview}</p>
          )}
          {hasErrors && summary.errors[0] && (
            <p className="text-[11px] text-red-300 mt-1 truncate">{summary.errors[0]}</p>
          )}
          <p className="text-[10px] text-muted mt-0.5">{summary.started_at}</p>
        </div>
        <ChevronRight size={13} className="text-muted shrink-0 mt-0.5" />
      </div>
    </div>
  );
}

// ─── Trace detail modal ───────────────────────────────────────────────────────

function TraceModal({
  runId,
  onClose,
}: {
  runId: string;
  onClose: () => void;
}) {
  const [trace, setTrace] = useState<DevTrace | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    devGetTrace(runId)
      .then(setTrace)
      .catch((e) => setErr(String(e)));
  }, [runId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fadeIn">
      <div className="w-full max-w-2xl mx-4 rounded-2xl glass border border-border shadow-2xl flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <Terminal size={14} className="text-accent" />
            <span className="text-sm font-mono font-semibold text-primary">{runId}</span>
            {trace && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-muted border border-border">
                {trace.mode}
              </span>
            )}
            {trace?.mode_effective && trace.mode_effective !== trace.mode && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/25">
                → {trace.mode_effective}
              </span>
            )}
          </div>
          <button onClick={onClose} className="p-1 rounded text-muted hover:text-primary">
            <X size={15} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto custom-scroll p-5">
          {err ? (
            <p className="text-red-400 text-sm">{err}</p>
          ) : !trace ? (
            <p className="text-muted text-sm">Cargando…</p>
          ) : (
            <>
              <div className="flex gap-4 text-xs text-muted mb-4 flex-wrap">
                <span>Inicio: <span className="text-secondary">{trace.started_at}</span></span>
                <span>Fin: <span className="text-secondary">{trace.finished_at || "—"}</span></span>
                <span>Input: <span className="text-secondary">{trace.input?.message?.slice(0, 80)}</span></span>
              </div>
              {trace.timing && Object.keys(trace.timing).length > 0 && (
                <div className="mb-4 flex flex-wrap gap-2">
                  {Object.entries(trace.timing).map(([k, v]) => (
                    <span
                      key={k}
                      className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 border border-border text-muted"
                    >
                      {k}: {typeof v === "number" ? `${v}ms` : String(v)}
                    </span>
                  ))}
                </div>
              )}
              <div className="space-y-0.5">
                {trace.events.map((ev, i) => (
                  <TraceEventRow key={i} ev={ev as Record<string, unknown>} />
                ))}
                {trace.events.length === 0 && (
                  <p className="text-muted text-xs">Sin eventos.</p>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Tab ─────────────────────────────────────────────────────────────────────

type Tab = "log" | "traces";

// ─── Main view ────────────────────────────────────────────────────────────────

export default function DevLogView() {
  const [tab, setTab] = useState<Tab>("log");

  // Log tab
  const [logLines, setLogLines] = useState<string[]>([]);
  const [logLive, setLogLive] = useState(true);
  const [logError, setLogError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const sseRef = useRef<AbortController | null>(null);

  // Traces tab
  const [traces, setTraces] = useState<DevTraceSummary[]>([]);
  const [tracesLoading, setTracesLoading] = useState(false);
  const [expandedTrace, setExpandedTrace] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  // ── Live log SSE ─────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!logLive) return;
    const ctrl = new AbortController();
    sseRef.current = ctrl;
    setLogError(null);

    (async () => {
      try {
        for await (const ev of devStreamLog(200)) {
          if (ctrl.signal.aborted) break;
          if (ev.init) {
            setLogLines([]);  // will be replaced by initials
          }
          setLogLines((prev) => {
            const next = ev.init ? [...prev, ev.line] : [...prev, ev.line];
            return next.length > 2000 ? next.slice(-2000) : next;
          });
        }
      } catch (e) {
        if (!ctrl.signal.aborted) setLogError(String(e));
      }
    })();

    return () => ctrl.abort();
  }, [logLive]);

  // Auto-scroll log to bottom
  useEffect(() => {
    if (logLive) logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logLines, logLive]);

  async function refreshLog() {
    setLogError(null);
    try {
      const data = await devGetLog(400);
      setLogLines(data.lines);
    } catch (e) {
      setLogError(String(e));
    }
  }

  // ── Traces ────────────────────────────────────────────────────────────────────

  async function loadTraces() {
    setTracesLoading(true);
    try {
      setTraces(await devListTraces(50));
    } catch { /* backend offline */ }
    setTracesLoading(false);
  }

  useEffect(() => {
    if (tab === "traces") loadTraces();
  }, [tab]);

  async function clearTraces() {
    setClearing(true);
    try {
      await devClearTraces();
      setTraces([]);
    } catch { /* ignore */ }
    setClearing(false);
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-6 pt-5 pb-3 border-b border-border shrink-0">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Terminal size={16} className="text-accent" />
            <h2 className="text-base font-semibold text-primary">Dev Log</h2>
          </div>
          <div className="flex items-center gap-2">
            {tab === "log" && (
              <>
                <label className="flex items-center gap-1.5 text-xs text-muted cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={logLive}
                    onChange={(e) => setLogLive(e.target.checked)}
                    className="accent-accent"
                  />
                  Live
                </label>
                {!logLive && (
                  <button
                    onClick={refreshLog}
                    className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-raised transition-colors"
                  >
                    <RefreshCw size={14} />
                  </button>
                )}
              </>
            )}
            {tab === "traces" && (
              <>
                <button
                  onClick={loadTraces}
                  className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-raised transition-colors"
                >
                  <RefreshCw size={14} />
                </button>
                <button
                  onClick={clearTraces}
                  disabled={clearing || traces.length === 0}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs btn-ghost text-muted hover:text-red-400 disabled:opacity-40"
                >
                  <Trash2 size={13} /> Limpiar
                </button>
              </>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-base/60 rounded-xl p-1 w-fit">
          {(["log", "traces"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                tab === t
                  ? "bg-accent/15 text-accent border border-accent/25"
                  : "text-muted hover:text-secondary"
              }`}
            >
              {t === "log" ? "Server Log" : `Trazas${traces.length > 0 ? ` (${traces.length})` : ""}`}
            </button>
          ))}
        </div>
      </div>

      {/* ── Log panel ────────────────────────────────────────────────────────── */}
      {tab === "log" && (
        <div className="flex-1 overflow-y-auto custom-scroll p-4 font-mono text-[11px] leading-relaxed bg-[#07070f]">
          {logError && (
            <div className="mb-3 px-3 py-2 rounded-lg bg-red-400/10 border border-red-400/25 text-red-300 text-xs">
              {logError} — backend offline o log no existe
            </div>
          )}
          {logLines.length === 0 && !logError && (
            <p className="text-muted text-xs">Esperando líneas de log…</p>
          )}
          {logLines.map((line, i) => (
            <div key={i} className={`leading-5 whitespace-pre-wrap break-all ${colorLine(line)}`}>
              {line}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}

      {/* ── Traces panel ─────────────────────────────────────────────────────── */}
      {tab === "traces" && (
        <div className="flex-1 overflow-y-auto custom-scroll px-6 py-4 space-y-2">
          {tracesLoading ? (
            <p className="text-muted text-sm py-8 text-center">Cargando trazas…</p>
          ) : traces.length === 0 ? (
            <div className="py-12 text-center text-muted text-sm">
              <Zap size={28} className="mx-auto mb-3 opacity-30" />
              <p>Sin trazas guardadas</p>
              <p className="text-xs mt-1 opacity-60">Aparecen acá tras cada ejecución del agente.</p>
            </div>
          ) : (
            traces.map((t) => (
              <TraceCard
                key={t.run_id}
                summary={t}
                onExpand={(id) => setExpandedTrace(id)}
              />
            ))
          )}
        </div>
      )}

      {/* Trace modal */}
      {expandedTrace && (
        <TraceModal
          runId={expandedTrace}
          onClose={() => setExpandedTrace(null)}
        />
      )}
    </div>
  );
}
