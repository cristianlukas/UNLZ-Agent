import { useEffect, useState } from "react";
import { Cpu, HardDrive, MemoryStick, Power, Activity, RefreshCw, Terminal } from "lucide-react";
import { invoke } from "@tauri-apps/api/core";
import { getHealth, getStats, getLlamacppStatus, llamacppStart, llamacppStop } from "../lib/api";
import type { HealthResponse, LlamacppStatus, SystemStats } from "../lib/types";

function ProgressBar({ value, color = "accent" }: { value: number; color?: string }) {
  const colors: Record<string, string> = {
    accent: "bg-accent",
    green:  "bg-green-400",
    yellow: "bg-yellow-400",
    red:    "bg-red-400",
  };
  const pick = value > 90 ? "red" : value > 70 ? "yellow" : color;
  return (
    <div className="w-full h-1.5 bg-border rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all duration-700 ${colors[pick]}`}
        style={{ width: `${Math.min(value, 100)}%` }}
      />
    </div>
  );
}

function StatCard({ icon, label, value, sub, progress }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  progress?: number;
}) {
  return (
    <div className="bg-raised border border-border rounded-xl p-4 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-muted text-xs">
          {icon}
          <span className="uppercase tracking-wider">{label}</span>
        </div>
        <span className="text-sm font-semibold text-primary">{value}</span>
      </div>
      {progress !== undefined && <ProgressBar value={progress} />}
      {sub && <p className="text-[11px] text-muted">{sub}</p>}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls = status === "ok"
    ? "text-green-400 bg-green-400/10 border-green-400/20"
    : status === "warning"
    ? "text-yellow-400 bg-yellow-400/10 border-yellow-400/20"
    : "text-red-400 bg-red-400/10 border-red-400/20";
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${cls}`}>
      {status}
    </span>
  );
}

export default function SystemView() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [llama, setLlama] = useState<LlamacppStatus | null>(null);
  const [llamaLoading, setLlamaLoading] = useState(false);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<"online" | "offline">("offline");
  const [toast, setToast] = useState("");

  async function refresh() {
    try { setStats(await getStats()); } catch { /* ignore */ }
    try {
      const h = await getHealth();
      setHealth(h);
      setAgentStatus(h.status === "online" || h.status === "degraded" ? "online" : "offline");
    } catch {
      setAgentStatus("offline");
    }
    try { setLlama(await getLlamacppStatus()); } catch { /* ignore */ }
  }

  async function restartAgent() {
    setAgentLoading(true);
    try {
      const result = await invoke<string>("restart_agent");
      showToast(result.startsWith("started") ? `Agente reiniciado (${result})` : `Error: ${result}`);
      setTimeout(refresh, 1500);
    } catch (e) {
      showToast(`Tauri error: ${e}`);
    }
    setAgentLoading(false);
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, []);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  }

  async function toggleLlama() {
    setLlamaLoading(true);
    try {
      if (llama?.running) {
        await llamacppStop();
        showToast("llama.cpp stopped");
      } else {
        const res = await llamacppStart();
        showToast(`llama.cpp started — PID ${res.pid}`);
      }
      await refresh();
    } catch (e) {
      showToast(`Error: ${e}`);
    }
    setLlamaLoading(false);
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Activity size={16} className="text-accent" />
        <span className="text-sm font-medium text-primary">System</span>
      </div>

      {/* Stats */}
      {stats ? (
        <div className="grid grid-cols-2 gap-3">
          <StatCard
            icon={<Cpu size={13} />}
            label="CPU"
            value={`${stats.cpu_percent.toFixed(1)}%`}
            progress={stats.cpu_percent}
          />
          <StatCard
            icon={<MemoryStick size={13} />}
            label="RAM"
            value={`${stats.ram_used_gb.toFixed(1)} / ${stats.ram_total_gb} GB`}
            sub={`${stats.ram_percent.toFixed(1)}% used`}
            progress={stats.ram_percent}
          />
          {stats.vram_total_gb && stats.vram_total_gb > 0 && (
            <StatCard
              icon={<MemoryStick size={13} />}
              label="VRAM"
              value={`${(stats.vram_used_gb ?? 0).toFixed(1)} / ${stats.vram_total_gb.toFixed(1)} GB`}
              sub={`${(stats.vram_percent ?? 0).toFixed(1)}% used`}
              progress={stats.vram_percent ?? 0}
            />
          )}
          {(stats.disks && stats.disks.length > 0 ? stats.disks : [{
            name: "Disk",
            mountpoint: "/",
            total_gb: stats.disk_total_gb,
            used_gb: stats.disk_used_gb,
            percent: stats.disk_percent,
          }]).map((disk) => (
            <StatCard
              key={disk.mountpoint}
              icon={<HardDrive size={13} />}
              label={`Disk ${disk.name}`}
              value={`${disk.used_gb.toFixed(0)} / ${disk.total_gb.toFixed(0)} GB`}
              sub={`${disk.percent.toFixed(1)}% used`}
              progress={disk.percent}
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 bg-raised border border-border rounded-xl shimmer" />
          ))}
        </div>
      )}

      {/* Health components */}
      {health && (
        <div className="space-y-2">
          <h3 className="text-xs text-muted uppercase tracking-wider">Services</h3>
          <div className="space-y-2">
            {Object.entries(health.components).map(([key, comp]) => (
              <div key={key} className="flex items-center justify-between px-4 py-3 bg-raised border border-border rounded-xl">
                <div>
                  <p className="text-sm text-primary font-medium capitalize">{key}</p>
                  <p className="text-[11px] text-muted">{comp.details}</p>
                </div>
                <StatusBadge status={comp.status} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Agent server control */}
      <div className="bg-raised border border-border rounded-xl p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Terminal size={14} className={agentStatus === "online" ? "text-green-400" : "text-red-400"} />
            <div>
              <p className="text-sm font-medium text-primary">Agent Server</p>
              <p className="text-xs text-muted font-mono">
                {agentStatus === "online" ? "http://127.0.0.1:7719 — online" : "offline — no responde en :7719"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={refresh}
              className="btn-ghost px-2 py-1.5 text-xs flex items-center gap-1"
              title="Refrescar"
            >
              <RefreshCw size={12} />
            </button>
            <button
              onClick={restartAgent}
              disabled={agentLoading}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-accent/30 text-accent bg-accent/10 hover:bg-accent/20 transition-all"
              title="Reiniciar agent_server.py"
            >
              {agentLoading ? (
                <div className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
              ) : (
                <Power size={12} />
              )}
              Reiniciar
            </button>
          </div>
        </div>
      </div>

      {/* llama.cpp control */}
      {llama !== null && (
        <div className="bg-raised border border-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <p className="text-sm font-medium text-primary">llama.cpp Server</p>
              <p className="text-xs text-muted font-mono">
                {llama.running ? llama.url : "not running"}
              </p>
            </div>
            <button
              className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all ${
                llama.running
                  ? "border-red-900/50 text-red-400 bg-red-900/10 hover:bg-red-900/20"
                  : "border-green-900/50 text-green-400 bg-green-900/10 hover:bg-green-900/20"
              }`}
              onClick={toggleLlama}
              disabled={llamaLoading}
            >
              {llamaLoading ? (
                <div className="w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
              ) : (
                <Power size={12} />
              )}
              {llama.running ? "Stop" : "Start"}
            </button>
          </div>
          {llama.model && (
            <p className="text-[11px] text-muted font-mono truncate">{llama.model}</p>
          )}
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-raised border border-border px-4 py-2 rounded-lg text-xs text-primary shadow-xl animate-fadeIn">
          {toast}
        </div>
      )}
    </div>
  );
}
