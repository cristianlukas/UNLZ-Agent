import { useEffect, useState } from "react";
import TitleBar from "./components/TitleBar";
import ConversationSidebar from "./components/ConversationSidebar";
import ChatView from "./components/ChatView";
import FoldersView from "./components/FoldersView";
import SettingsView from "./components/SettingsView";
import BehaviorsView from "./components/BehaviorsView";
import DevLogView from "./components/DevLogView";
import OnboardingModal from "./components/OnboardingModal";
import { useStore } from "./lib/store";
import { getHealth, getLocalBehaviors, getNewbieProfile, getOnboardingHealth, runOnboardingFix, saveNewbieProfile, startMcpServer, getOpencodeWarmupStatus } from "./lib/api";
import type { OnboardingStatus } from "./lib/types";

export default function App() {
  const { view, setAgentReady, setProviderInfo, setLlmReady, setLlmStatus, upsertBehaviors } = useStore();
  const agentReady = useStore((s) => s.agentReady);
  const onboardingCompleted = useStore((s) => s.onboardingCompleted);
  const setOnboardingCompleted = useStore((s) => s.setOnboardingCompleted);
  const setNewbieProfile = useStore((s) => s.setNewbieProfile);
  const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatus | null>(null);
  const [onboardingLoading, setOnboardingLoading] = useState(false);
  const [onboardingFixing, setOnboardingFixing] = useState(false);
  const [onboardingStartingMcp, setOnboardingStartingMcp] = useState(false);
  const [onboardingMcpFeedback, setOnboardingMcpFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [warmupStatus, setWarmupStatus] = useState<{ status?: string; detail?: string } | null>(null);

  useEffect(() => {
    let mounted = true;

    async function poll() {
      try {
        const h = await getHealth();
        if (!mounted) return;
        setAgentReady(h.status === "online" || h.status === "degraded");
        const llm = h.components?.llm;
        setLlmReady(llm?.status === "ok");
        const state = llm?.state ?? (llm?.status === "ok" ? "ready" : "not_loaded");
        setLlmStatus(state, llm?.details ?? "");
        if (llm?.details) {
          const parts = llm.details.split("—").map((s) => s.trim());
          setProviderInfo(parts[0] ?? "opencode", parts[1] ?? "");
        }
      } catch {
        if (mounted) {
          setAgentReady(false);
          setLlmReady(false);
          setLlmStatus("not_loaded", "opencode no disponible.");
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
    return () => { mounted = false; };
  }, [upsertBehaviors]);

  useEffect(() => {
    let mounted = true;
    async function loadOnboarding() {
      try {
        setOnboardingLoading(true);
        const [status, profile] = await Promise.all([getOnboardingHealth(), getNewbieProfile()]);
        if (!mounted) return;
        setOnboardingStatus(status);
        setNewbieProfile(profile);
      } finally {
        if (mounted) setOnboardingLoading(false);
      }
    }
    loadOnboarding();
    return () => { mounted = false; };
  }, [setNewbieProfile]);

  useEffect(() => {
    let mounted = true;
    const tick = async () => {
      const st = await getOpencodeWarmupStatus();
      if (mounted) setWarmupStatus(st ? { status: st.status, detail: st.detail } : null);
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  async function handleOnboardingFix() {
    setOnboardingFixing(true);
    try {
      await runOnboardingFix();
      const status = await getOnboardingHealth();
      setOnboardingStatus(status);
    } finally {
      setOnboardingFixing(false);
    }
  }

  async function handleOnboardingClose() {
    setOnboardingCompleted(true);
    await saveNewbieProfile({ onboarding_completed: true, completed_at: Date.now() });
  }

  async function handleStartMcp() {
    setOnboardingStartingMcp(true);
    setOnboardingMcpFeedback(null);
    try {
      const res = await startMcpServer();
      const status = await getOnboardingHealth();
      setOnboardingStatus(status);
      if (res?.status === "started" || res?.status === "already_running" || res?.status === "starting") {
        setOnboardingMcpFeedback({ type: "success", text: "MCP iniciado correctamente." });
      } else {
        setOnboardingMcpFeedback({ type: "error", text: "No se pudo confirmar el inicio de MCP." });
      }
    } catch {
      setOnboardingMcpFeedback({ type: "error", text: "Error al intentar iniciar MCP." });
    } finally {
      setOnboardingStartingMcp(false);
      window.setTimeout(() => setOnboardingMcpFeedback(null), 3000);
    }
  }

  const status = (agentReady ? "online" : "offline") as "online" | "offline";

  return (
    <div className="flex flex-col h-screen bg-base overflow-hidden">
      <TitleBar healthStatus={status} />

      <div className="flex flex-1 overflow-hidden">
        <ConversationSidebar />

        <main className="flex-1 overflow-hidden relative">
          {view === "chat"      && <ChatView />}
          {view === "behaviors" && <BehaviorsView />}
          {view === "folders"   && <FoldersView />}
          {view === "settings"  && <SettingsView />}
          {view === "devlog"    && <DevLogView />}
          <OnboardingModal
            open={!onboardingCompleted}
            status={onboardingStatus}
            loading={onboardingLoading}
            fixing={onboardingFixing}
            startingMcp={onboardingStartingMcp}
            mcpFeedback={onboardingMcpFeedback}
            warmupStatus={warmupStatus}
            onRunFix={handleOnboardingFix}
            onStartMcp={handleStartMcp}
            onClose={handleOnboardingClose}
          />
        </main>
      </div>
    </div>
  );
}
