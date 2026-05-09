import { useEffect, useMemo, useState } from "react";
import { Bot, CalendarClock, Play, Pause, Trash2, Plus, RefreshCw } from "lucide-react";
import {
  createAgentTask,
  deleteAgentTask,
  listAgentTasks,
  patchAgentTask,
  runAgentTaskNow,
  type AgentTask,
  type AgentTaskHarness,
} from "../lib/api";

export default function AgentsView() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [createdInfo, setCreatedInfo] = useState<{ name: string; schedule: string } | null>(null);
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [harness, setHarness] = useState<AgentTaskHarness>("hermes-agent");

  async function refresh() {
    try {
      setLoading(true);
      setError("");
      setTasks(await listAgentTasks());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(() => {
      refresh();
    }, 5000);
    return () => clearInterval(t);
  }, []);

  async function createTaskHandler() {
    const n = name.trim();
    const p = prompt.trim();
    if (!n || !p) return;
    const created = await createAgentTask({
      name: n,
      prompt: p,
      schedule: "auto",
      harness,
      status: "active",
    });
    setCreatedInfo({ name: created.name, schedule: created.schedule });
    setName("");
    setPrompt("");
    await refresh();
  }

  async function toggleTask(task: AgentTask) {
    await patchAgentTask(task.id, { status: task.status === "active" ? "paused" : "active" });
    await refresh();
  }

  async function removeTask(task: AgentTask) {
    await deleteAgentTask(task.id);
    await refresh();
  }

  async function runNow(task: AgentTask) {
    await runAgentTaskNow(task.id);
    await refresh();
  }

  const sorted = useMemo(
    () => [...tasks].sort((a, b) => Number(b.updatedAt) - Number(a.updatedAt)),
    [tasks]
  );

  return (
    <div className="h-full overflow-auto custom-scroll p-4 space-y-4">
      <section className="bg-surface border border-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <Bot size={16} className="text-accent" />
          <h2 className="text-sm font-semibold text-primary">Agentes</h2>
        </div>
        <p className="text-xs text-muted">
          Programá tareas de agente por perfil. Las tareas se ejecutan automáticamente en backend según su schedule.
        </p>
      </section>

      <section className="bg-surface border border-border rounded-xl p-4 space-y-3">
        <h3 className="text-xs font-semibold text-muted uppercase tracking-wider">Nueva tarea</h3>
        {createdInfo && (
          <div className="text-xs rounded border border-green-500/30 bg-green-500/10 text-green-300 px-3 py-2">
            Schedule inferido para <span className="font-semibold">{createdInfo.name}</span>:{" "}
            <code>{createdInfo.schedule}</code>
          </div>
        )}
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nombre de la tarea"
          className="w-full bg-base border border-border rounded px-3 py-2 text-sm text-primary outline-none"
        />
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Prompt/instrucción del agente…"
          rows={4}
          className="w-full bg-base border border-border rounded px-3 py-2 text-sm text-primary outline-none resize-y"
        />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <select
            value={harness}
            onChange={(e) => setHarness(e.target.value as AgentTaskHarness)}
            className="bg-base border border-border rounded px-3 py-2 text-sm text-primary outline-none"
          >
            <option value="hermes-agent">Hermes Agent</option>
            <option value="opencode">opencode</option>
          </select>
          <button
            onClick={createTaskHandler}
            className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded bg-accent text-white text-sm hover:bg-accent/90"
          >
            <Plus size={14} />
            Crear tarea
          </button>
        </div>
        <p className="text-[11px] text-muted">
          El schedule se infiere automáticamente desde el prompt usando LLM. Luego podés editarlo en backend (manual/API) si lo necesitás.
        </p>
      </section>

      <section className="bg-surface border border-border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold text-muted uppercase tracking-wider">Tareas programadas</h3>
          <button
            onClick={refresh}
            className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded border border-border text-muted hover:text-primary"
          >
            <RefreshCw size={12} />
            Refresh
          </button>
        </div>
        {loading && <p className="text-xs text-muted mb-2">Cargando tareas…</p>}
        {error && <p className="text-xs text-red-400 mb-2">{error}</p>}
        {sorted.length === 0 ? (
          <p className="text-xs text-muted">No hay tareas todavía.</p>
        ) : (
          <div className="space-y-2">
            {sorted.map((t) => (
              <div key={t.id} className="border border-border rounded-lg p-3 bg-panel">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-primary truncate">{t.name}</p>
                    <p className="text-xs text-muted mt-1">{t.prompt}</p>
                    <div className="flex items-center gap-3 mt-2 text-[11px] text-secondary">
                      <span className="inline-flex items-center gap-1">
                        <CalendarClock size={12} /> {t.schedule}
                      </span>
                      <span className="px-1.5 py-0.5 rounded border border-border text-muted">
                        {t.harness}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded ${t.status === "active" ? "bg-green-500/10 text-green-400" : "bg-amber-500/10 text-amber-400"}`}>
                        {t.status}
                      </span>
                      {!!t.running && (
                        <span className="px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-300">running</span>
                      )}
                    </div>
                    <div className="mt-2 text-[11px] text-muted">
                      <div>Próxima ejecución: {t.nextRunAt ? new Date(Number(t.nextRunAt) * 1000).toLocaleString() : "—"}</div>
                      <div>Última ejecución: {t.lastRunAt ? new Date(Number(t.lastRunAt)).toLocaleString() : "—"} {t.lastStatus ? `(${t.lastStatus})` : ""}</div>
                      {t.lastError ? <div className="text-red-400">Error: {t.lastError}</div> : null}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => runNow(t)}
                      className="p-1.5 rounded border border-border text-muted hover:text-primary hover:bg-surface-2"
                      title="Ejecutar ahora"
                    >
                      <Play size={14} />
                    </button>
                    <button
                      onClick={() => toggleTask(t)}
                      className="p-1.5 rounded border border-border text-muted hover:text-primary hover:bg-surface-2"
                      title={t.status === "active" ? "Pausar" : "Activar"}
                    >
                      {t.status === "active" ? <Pause size={14} /> : <Play size={14} />}
                    </button>
                    <button
                      onClick={() => removeTask(t)}
                      className="p-1.5 rounded border border-border text-muted hover:text-red-400 hover:bg-surface-2"
                      title="Eliminar"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
