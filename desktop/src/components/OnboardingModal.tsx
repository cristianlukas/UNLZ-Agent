import { useMemo } from "react";
import type { OnboardingStatus } from "../lib/types";

export default function OnboardingModal({
  open,
  status,
  loading,
  fixing,
  startingMcp,
  mcpFeedback,
  warmupStatus,
  onRunFix,
  onStartMcp,
  onClose,
}: {
  open: boolean;
  status: OnboardingStatus | null;
  loading: boolean;
  fixing: boolean;
  startingMcp: boolean;
  mcpFeedback?: { type: "success" | "error"; text: string } | null;
  warmupStatus?: { status?: string; detail?: string } | null;
  onRunFix: () => void;
  onStartMcp: () => void;
  onClose: () => void;
}) {
  const ready = useMemo(() => status?.status === "ready", [status]);
  const summary = useMemo(() => {
    const checks = status?.checks || [];
    const ok = checks.filter((c) => c.status === "ok").length;
    const warn = checks.filter((c) => c.status === "warning").length;
    const err = checks.filter((c) => c.status === "error").length;
    return { total: checks.length, ok, warn, err };
  }, [status]);
  if (!open) return null;

  return (
    <div className="absolute inset-0 z-40 bg-black/40 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="w-full max-w-3xl rounded-2xl border border-border bg-surface shadow-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-raised/60">
          <h3 className="text-base font-semibold text-primary">Onboarding inicial</h3>
          <p className="text-xs text-muted mt-1">Revisamos tu equipo y te dejamos todo listo</p>
          {warmupStatus?.status && (
            <div className="mt-2">
              <span
                className={`inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full ${
                  warmupStatus.status === "ready"
                    ? "text-emerald-300 bg-emerald-500/10 border border-emerald-500/30"
                    : warmupStatus.status === "running"
                      ? "text-amber-300 bg-amber-500/10 border border-amber-500/30"
                      : warmupStatus.status === "error"
                        ? "text-red-300 bg-red-500/10 border border-red-500/30"
                        : "text-muted bg-base border border-border"
                }`}
                title={warmupStatus.detail || ""}
              >
                Warmup opencode: {warmupStatus.status}
              </span>
            </div>
          )}
        </div>
        {mcpFeedback?.text && (
          <div
            className={`mx-5 mt-3 rounded-lg border px-3 py-2 text-xs ${
              mcpFeedback.type === "success"
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                : "border-red-500/40 bg-red-500/10 text-red-300"
            }`}
          >
            {mcpFeedback.text}
          </div>
        )}
        <div className="p-5 space-y-4">
          {loading && <p className="text-sm text-muted">Cargando diagnóstico…</p>}
          {!loading && status && (
            <>
              <div className="rounded-lg border border-border bg-base/70 px-3 py-2 text-xs text-secondary">
                {summary.ok} de {summary.total} checks OK
                {summary.err > 0
                  ? " · Hay errores críticos antes de continuar"
                  : summary.warn > 0
                    ? " · Podés continuar, pero algunas funciones avanzadas no estarán disponibles"
                    : " · Todo listo para usar"}
              </div>
              <div className="space-y-2">
                {status.checks.map((c) => (
                  <div
                    key={c.id}
                    className={`rounded-lg border bg-base/70 px-3 py-2 ${
                      c.status === "ok"
                        ? "border-emerald-500/40"
                        : c.status === "warning"
                          ? "border-amber-500/40"
                          : "border-red-500/40"
                    }`}
                  >
                    <p className="text-xs text-secondary">
                      <span className={c.status === "ok" ? "text-emerald-400" : c.status === "warning" ? "text-amber-400" : "text-red-400"}>
                        {c.status === "ok" ? "✓ OK" : c.status === "warning" ? "⚠ WARNING" : "✕ ERROR"}
                      </span>{" "}
                      {c.name}
                    </p>
                    <p className="text-xs text-primary mt-1">{c.details}</p>
                    {(c.status === "warning" || c.status === "error") && <p className="text-[11px] text-muted mt-1">Sugerencia: {c.action}</p>}
                    {c.id === "mcp_port" && c.status !== "ok" && (
                      <button
                        onClick={onStartMcp}
                        disabled={startingMcp || fixing}
                        className="mt-2 text-[11px] px-2 py-1 rounded-md border border-amber-500/40 text-amber-300 hover:bg-amber-500/10 disabled:opacity-40"
                      >
                        {startingMcp ? "Iniciando MCP…" : "Iniciar MCP ahora"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <div>
                <p className="text-xs text-secondary mb-1">Ejemplos para empezar:</p>
                <ul className="text-xs text-muted space-y-1">
                  {status.first_prompt_examples.map((x, i) => <li key={i}>• {x}</li>)}
                </ul>
              </div>
            </>
          )}
        </div>
        <div className="px-5 py-3 border-t border-border bg-raised/40 flex items-center justify-end gap-2">
          {!ready && (
            <button onClick={onRunFix} disabled={fixing || loading} className="btn-primary px-3 py-1.5 text-sm disabled:opacity-40">
              {fixing ? "Aplicando…" : "Dejar todo listo"}
            </button>
          )}
          <button onClick={onClose} disabled={!status || summary.err > 0} className="btn-ghost px-3 py-1.5 text-sm">
            Continuar
          </button>
        </div>
      </div>
    </div>
  );
}
