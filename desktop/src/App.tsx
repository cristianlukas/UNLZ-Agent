import { useEffect } from "react";
import TitleBar from "./components/TitleBar";
import ConversationSidebar from "./components/ConversationSidebar";
import ChatView from "./components/ChatView";
import KnowledgeView from "./components/KnowledgeView";
import FoldersView from "./components/FoldersView";
import SystemView from "./components/SystemView";
import SettingsView from "./components/SettingsView";
import BehaviorsView from "./components/BehaviorsView";
import { useStore } from "./lib/store";
import { getHealth } from "./lib/api";

export default function App() {
  const { view, setAgentReady, setProviderInfo, setLlmReady } = useStore();
  const agentReady = useStore((s) => s.agentReady);

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
        if (llm?.details) {
          const parts = llm.details.split("—").map((s) => s.trim());
          setProviderInfo(parts[0] ?? "?", parts[1] ?? "");
        }
      } catch {
        if (mounted) setAgentReady(false);
      }
    }

    poll();
    const id = setInterval(poll, 5000);
    return () => { mounted = false; clearInterval(id); };
  }, [setAgentReady, setProviderInfo, setLlmReady]);

  const status = (agentReady ? "online" : "offline") as "online" | "offline";

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
        </main>
      </div>
    </div>
  );
}
