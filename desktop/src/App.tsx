import { useEffect } from "react";
import TitleBar from "./components/TitleBar";
import ConversationSidebar from "./components/ConversationSidebar";
import ChatView from "./components/ChatView";
import KnowledgeView from "./components/KnowledgeView";
import FoldersView from "./components/FoldersView";
import SystemView from "./components/SystemView";
import SettingsView from "./components/SettingsView";
import BehaviorsView from "./components/BehaviorsView";
import ModelHubView from "./components/ModelHubView";
import DevLogView from "./components/DevLogView";
import { useStore } from "./lib/store";
import { getHealth, getLocalBehaviors } from "./lib/api";

export default function App() {
  const { view, setAgentReady, setProviderInfo, setLlmReady, setLlmStatus, upsertBehaviors } = useStore();
  const agentReady = useStore((s) => s.agentReady);
  const llmState = useStore((s) => s.llmState);
  const llmStateMessage = useStore((s) => s.llmStateMessage);

  useEffect(() => {
    let mounted = true;

    async function poll() {
      try {
        const h = await getHealth();
        if (!mounted) return;
        // Ready as long as agent_server.py is responding (llm may still be loading)
        setAgentReady(h.status === "online" || h.status === "degraded");
        const llm = h.components?.llm;
        setLlmReady(llm?.status === "ok");
        const state = llm?.state ?? (llm?.status === "ok" ? "ready" : "not_loaded");
        setLlmStatus(state, llm?.details ?? "");
        if (llm?.details) {
          const parts = llm.details.split("—").map((s) => s.trim());
          setProviderInfo(parts[0] ?? "?", parts[1] ?? "");
        }
      } catch {
        if (mounted) {
          setAgentReady(false);
          setLlmReady(false);
          setLlmStatus("not_loaded", "Modelo no cargado.");
        }
      }
    }

    poll();
    const id = setInterval(poll, 5000);
    return () => { mounted = false; clearInterval(id); };
  }, [setAgentReady, setProviderInfo, setLlmReady, setLlmStatus]);

  useEffect(() => {
    let mounted = true;
    async function loadLocalProfiles() {
      const rows = await getLocalBehaviors();
      if (!mounted || !rows?.length) return;
      upsertBehaviors(rows);
    }
    loadLocalProfiles();
    return () => {
      mounted = false;
    };
  }, [upsertBehaviors]);

  const status = (agentReady ? "online" : "offline") as "online" | "offline";
  const shouldBlockByModel = llmState !== "ready";
  const overlayTitle =
    llmState === "loading" ? "Modelo cargando, espere por favor" : "Modelo no cargado";
  const overlayDetail =
    llmStateMessage ||
    (llmState === "loading"
      ? "Estamos iniciando/cambiando el modelo de IA."
      : "Configure o cargue un modelo para continuar.");

  return (
    <div className="flex flex-col h-screen bg-base overflow-hidden">
      <TitleBar healthStatus={status} />

      <div className="flex flex-1 overflow-hidden">
        {/* Conversation sidebar — always visible */}
        <ConversationSidebar />

        {/* Main panel */}
        <main className="flex-1 overflow-hidden relative">
          {view === "chat"      && <ChatView />}
          {view === "behaviors" && <BehaviorsView />}
          {view === "knowledge" && <KnowledgeView />}
          {view === "folders"   && <FoldersView />}
          {view === "system"    && <SystemView />}
          {view === "settings"  && <SettingsView />}
          {view === "hub"       && <ModelHubView />}
          {view === "devlog"    && <DevLogView />}

          {view === "chat" && shouldBlockByModel && (
            <div className="absolute inset-0 z-40 bg-base/65 backdrop-blur-[1.5px] flex items-center justify-center p-6">
              <div className="max-w-xl w-full rounded-xl border border-border bg-panel/95 px-6 py-5 text-center shadow-lg">
                <div className="text-lg font-semibold text-primary">{overlayTitle}</div>
                <p className="text-sm text-muted mt-2">{overlayDetail}</p>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
