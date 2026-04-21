import { useCallback, useEffect, useRef, useState } from "react";
import { Send, RefreshCw, Wrench, ChevronDown, Brain, Plus, Pencil, Check, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { streamChat } from "../lib/api";
import type { AgentStep, ChatMessage } from "../lib/types";
import { useStore, useActiveConv, useActiveBehavior, useActiveFolder } from "../lib/store";
import unlzLogo from "../assets/unlz-logo.png";

let _msgId = Date.now();
const uid = () => String(++_msgId);
type SendMode = "normal" | "plan" | "iterate";

// ─── Tool step ────────────────────────────────────────────────────────────────

const TOOL_ICONS: Record<string, string> = {
  search_local_knowledge: "📚",
  web_search: "🌐",
  get_current_time: "🕐",
  get_system_stats: "📊",
  list_knowledge_base_files: "📁",
  search_folder_documents: "📂",
  run_windows_command: "🖥️",
};

function ToolStep({ step }: { step: AgentStep }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-muted italic py-0.5 animate-fadeIn">
      <span>{TOOL_ICONS[step.tool] ?? "🔧"}</span>
      <span className="text-secondary">{step.tool.replace(/_/g, " ")}</span>
      {step.args && Object.keys(step.args).length > 0 && (
        <span className="text-border truncate max-w-[200px]">
          — {String(Object.values(step.args)[0])}
        </span>
      )}
    </div>
  );
}

// ─── Message bubble ───────────────────────────────────────────────────────────

function Message({
  msg,
  isStreaming,
  onEdit,
  canEdit,
}: {
  msg: ChatMessage;
  isStreaming: boolean;
  onEdit?: () => void;
  canEdit?: boolean;
}) {
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end mb-4 animate-fadeIn">
        <div className="group flex flex-col items-end gap-1 max-w-[72%]">
          <div
            className="w-full px-4 py-2.5 rounded-2xl rounded-tr-sm text-sm"
            style={{ background: "linear-gradient(135deg, #7c6af5 0%, #6d5ce8 100%)", color: "white" }}
          >
            <p className="leading-relaxed selectable whitespace-pre-wrap">{msg.content}</p>
          </div>
          {canEdit && onEdit && (
            <button
              onClick={onEdit}
              className="opacity-0 group-hover:opacity-100 transition-opacity text-[11px] text-muted hover:text-primary flex items-center gap-1"
              title="Editar mensaje y recalcular"
            >
              <Pencil size={11} />
              Editar
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 mb-4 animate-fadeIn">
      {/* Avatar */}
      <div className="shrink-0 w-7 h-7 rounded-lg bg-accent-dim flex items-center justify-center mt-0.5">
        <img src={unlzLogo} alt="UNLZ" className="w-4 h-4 object-contain" />
      </div>

      <div className="flex-1 min-w-0 group">
        {/* Tool steps */}
        {msg.steps && msg.steps.length > 0 && (
          <div className="mb-2 pl-2 border-l border-border space-y-0.5">
            {msg.steps.map((s, i) => (
              <ToolStep key={i} step={s} />
            ))}
          </div>
        )}

        {/* Content */}
        <div
          className={`px-4 py-3 rounded-2xl rounded-tl-sm text-sm ${
            msg.error
              ? "bg-red-900/20 border border-red-900/40 text-red-300"
              : "bg-raised border border-border"
          }`}
        >
          {msg.content ? (
            <div className="prose-chat selectable">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className ?? "");
                    return match ? (
                      <SyntaxHighlighter
                        style={oneDark as never}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{ margin: 0, borderRadius: 6, fontSize: "0.78em" }}
                      >
                        {String(children).replace(/\n$/, "")}
                      </SyntaxHighlighter>
                    ) : (
                      <code className={className} {...props}>{children}</code>
                    );
                  },
                }}
              >
                {msg.content}
              </ReactMarkdown>
            </div>
          ) : isStreaming ? (
            <div className="flex items-center gap-2 text-muted">
              <span className="shimmer inline-block w-20 h-3 rounded" />
              <span className="shimmer inline-block w-12 h-3 rounded" />
            </div>
          ) : (
            <p className="text-xs text-muted">
              Acción completada sin texto de respuesta.
            </p>
          )}

          {isStreaming && msg.content && (
            <span className="inline-block w-0.5 h-3.5 bg-accent-light ml-0.5 animate-blink align-middle" />
          )}
          {typeof msg.confidence === "number" && !isStreaming && !msg.error && (
            <p className="mt-2 text-[10px] text-muted">Confianza estimada: {(msg.confidence * 100).toFixed(0)}%</p>
          )}
        </div>
        {canEdit && onEdit && (
          <button
            onClick={onEdit}
            className="mt-1 opacity-0 group-hover:opacity-100 transition-opacity text-[11px] text-muted hover:text-primary flex items-center gap-1"
            title="Editar mensaje y recalcular"
          >
            <Pencil size={11} />
            Editar
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Behavior badge ───────────────────────────────────────────────────────────

function BehaviorBadge() {
  const { behaviors, activeConvId, conversations } = useStore();
  const behavior = useActiveBehavior();
  const conv = conversations.find((c) => c.id === activeConvId);

  const [open, setOpen] = useState(false);

  if (!conv) return null;

  function assignBehavior(behaviorId: string | undefined) {
    if (!activeConvId) return;
    useStore.getState().upsertMessage; // touch to re-render
    // Update conv's behaviorId directly via store
    useStore.setState((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === activeConvId ? { ...c, behaviorId, updatedAt: Date.now() } : c
      ),
    }));
    setOpen(false);
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((p) => !p)}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border transition-colors
          ${behavior
            ? "bg-accent/10 border-accent/25 text-accent hover:bg-accent/15"
            : "bg-raised border-border text-muted hover:text-primary hover:border-border-strong"
          }`}
        title="Comportamiento activo"
      >
        <Brain size={11} />
        <span>{behavior ? `${behavior.icon ?? "🤖"} ${behavior.name}` : "Sin comportamiento"}</span>
        <ChevronDown size={10} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute top-8 left-0 z-20 bg-raised border border-border rounded-xl shadow-xl w-56 py-1">
          <button
            onClick={() => assignBehavior(undefined)}
            className={`w-full text-left px-3 py-2 text-xs hover:bg-base transition-colors ${
              !conv.behaviorId ? "text-accent" : "text-secondary"
            }`}
          >
            Sin comportamiento
          </button>
          <div className="border-t border-border my-1" />
          {behaviors.map((b) => (
            <button
              key={b.id}
              onClick={() => assignBehavior(b.id)}
              className={`w-full text-left px-3 py-2 text-xs hover:bg-base transition-colors ${
                conv.behaviorId === b.id ? "text-accent" : "text-secondary"
              }`}
            >
              {b.icon ?? "🤖"} {b.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Welcome screen ───────────────────────────────────────────────────────────

function Welcome() {
  const { provider, modelAlias, createConversation, setPendingDraft } = useStore();
  const SUGGESTIONS = [
    "¿Qué documentos hay en la base de conocimiento?",
    "Buscá información sobre la UNLZ",
    "¿Qué hora es?",
    "Mostrá las estadísticas del sistema",
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 px-8 animate-fadeIn">
      <div className="text-center space-y-2">
        <div className="w-14 h-14 rounded-2xl bg-accent-dim flex items-center justify-center mx-auto mb-4 glow-accent-sm">
          <img src={unlzLogo} alt="UNLZ" className="w-8 h-8 object-contain" />
        </div>
        <h1 className="text-xl font-semibold text-primary">UNLZ Agent</h1>
        <p className="text-sm text-muted">
          {provider} · <span className="font-mono text-secondary">{modelAlias}</span>
        </p>
      </div>

      <button
        onClick={() => createConversation()}
        className="btn-primary flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm"
      >
        <Plus size={15} />
        Nueva conversación
      </button>

      <div className="grid grid-cols-2 gap-2 w-full max-w-md">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            className="btn-ghost text-left text-xs px-3 py-2.5 leading-snug"
            onClick={() => {
              const id = createConversation();
              setPendingDraft(id, s);
            }}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Active conversation view ─────────────────────────────────────────────────

function ActiveChat({ convId }: { convId: string }) {
  const {
    agentReady,
    llmReady,
    upsertMessage,
    clearConversation,
    consumePendingDraft,
    setConversationFolder,
  } = useStore();
  const behaviors = useStore((s) => s.behaviors);
  const folders = useStore((s) => s.folders);
  const conv = useStore((s) => s.conversations.find((c) => c.id === convId));
  const behavior = useActiveBehavior();
  const activeFolder = useActiveFolder();

  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [iteratorMode, setIteratorMode] = useState(false);
  const [planArmed, setPlanArmed] = useState(false);
  const [planWorkflowActive, setPlanWorkflowActive] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const initializedConvRef = useRef<string | null>(null);

  const messages = conv?.messages ?? [];

  function buildSystemPrompt(): string {
    const chunks: string[] = [];
    if (behavior?.content) chunks.push(behavior.content);
    if (activeFolder) {
      if (activeFolder.behaviorId) {
        const fb = behaviors.find((b) => b.id === activeFolder.behaviorId);
        if (fb?.content) chunks.push(`Instrucciones de carpeta (${activeFolder.name}):\n${fb.content}`);
      }
      if (activeFolder.customPrompt?.trim()) {
        chunks.push(`Prompt personalizado de carpeta (${activeFolder.name}):\n${activeFolder.customPrompt.trim()}`);
      }
      chunks.push(
        `Contexto de documentos: si necesitás buscar en documentos exclusivos de esta conversación, usá la herramienta search_folder_documents.`
      );
    }
    return chunks.join("\n\n");
  }

  const scrollToBottom = useCallback((smooth = true) => {
    bottomRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "auto" });
  }, []);

  useEffect(() => {
    if (isStreaming) scrollToBottom();
  }, [messages, isStreaming, scrollToBottom]);

  // Reset scroll on conv change
  useEffect(() => {
    if (initializedConvRef.current === convId) return;
    initializedConvRef.current = convId;
    scrollToBottom(false);
    setEditingId(null);
    setEditingText("");
    setIteratorMode(false);
    setPlanArmed(false);
    setPlanWorkflowActive(false);
    const draft = consumePendingDraft(convId);
    setInput(draft);
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
        textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
        if (draft) textareaRef.current.focus();
      }
    }, 0);
  }, [convId, scrollToBottom, consumePendingDraft]);

  function setConversationMessages(nextMessages: ChatMessage[]) {
    useStore.setState((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === convId ? { ...c, messages: nextMessages, updatedAt: Date.now() } : c
      ),
    }));
  }

  async function streamAssistantReply(
    prompt: string,
    historyForModel: Array<{ role: string; content: string }>,
    mode: SendMode = "normal"
  ) {
    const assistantId = uid();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      steps: [],
      ts: Date.now(),
    };

    upsertMessage(convId, assistantMsg);
    setIsStreaming(true);
    setTimeout(() => scrollToBottom(false), 0);

    try {
      for await (const event of streamChat(
        prompt,
        historyForModel,
        buildSystemPrompt(),
        conv?.folderId,
        mode,
        convId,
        false
      )) {
        if (event.type === "run") {
          const current = useStore
            .getState()
            .conversations.find((c) => c.id === convId)
            ?.messages.find((m) => m.id === assistantId);
          upsertMessage(convId, {
            ...(current ?? assistantMsg),
            runId: event.run_id,
          });
        } else if (event.type === "step") {
          upsertMessage(convId, {
            ...assistantMsg,
            steps: [
              ...(useStore.getState().conversations.find((c) => c.id === convId)
                ?.messages.find((m) => m.id === assistantId)?.steps ?? []),
              { tool: event.text, args: event.args as Record<string, unknown> | undefined },
            ],
          });
        } else if (event.type === "chunk") {
          const current = useStore
            .getState()
            .conversations.find((c) => c.id === convId)
            ?.messages.find((m) => m.id === assistantId);
          upsertMessage(convId, {
            ...(current ?? assistantMsg),
            content: (current?.content ?? "") + event.text,
          });
        } else if (event.type === "confidence") {
          const current = useStore
            .getState()
            .conversations.find((c) => c.id === convId)
            ?.messages.find((m) => m.id === assistantId);
          upsertMessage(convId, {
            ...(current ?? assistantMsg),
            confidence: event.score,
          });
        } else if (event.type === "error") {
          const current = useStore
            .getState()
            .conversations.find((c) => c.id === convId)
            ?.messages.find((m) => m.id === assistantId);
          upsertMessage(convId, {
            ...(current ?? assistantMsg),
            content: event.text,
            error: true,
          });
          break;
        } else if (event.type === "done") {
          break;
        }
      }
    } catch (e) {
      const current = useStore
        .getState()
        .conversations.find((c) => c.id === convId)
        ?.messages.find((m) => m.id === assistantId);
      upsertMessage(convId, {
        ...(current ?? assistantMsg),
        content: `Error de conexión: ${e}`,
        error: true,
      });
    }

    setIsStreaming(false);
  }

  function handleScroll() {
    const el = listRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setShowScrollBtn(!nearBottom);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || isStreaming) return;

    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const userMsg: ChatMessage = { id: uid(), role: "user", content: text, ts: Date.now() };
    upsertMessage(convId, userMsg);
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const low = text.toLowerCase();
    let mode: SendMode = "normal";
    if (planArmed && messages.length === 0) {
      mode = "plan";
      setPlanArmed(false);
      setPlanWorkflowActive(true);
    } else if (planWorkflowActive) {
      if (low.includes("descartar")) {
        setPlanWorkflowActive(false);
        mode = "normal";
      } else if (low.includes("ejecutar plan")) {
        setPlanWorkflowActive(false);
        mode = "iterate";
      } else if (low.includes("editar plan")) {
        mode = "plan";
      } else {
        mode = "plan";
      }
    } else if (iteratorMode) {
      mode = "iterate";
    }
    await streamAssistantReply(text, history, mode);
  }

  function startEdit(msg: ChatMessage) {
    if (isStreaming) return;
    setEditingId(msg.id);
    setEditingText(msg.content);
  }

  async function saveEditAndRecalculate(msg: ChatMessage) {
    const newText = editingText.trim();
    if (!newText || isStreaming) return;

    const currentConv = useStore.getState().conversations.find((c) => c.id === convId);
    if (!currentConv) return;

    const idx = currentConv.messages.findIndex((m) => m.id === msg.id);
    if (idx < 0) return;

    setEditingId(null);
    setEditingText("");

    if (msg.role === "user") {
      const editedUser: ChatMessage = { ...msg, content: newText, error: false };
      const prefix = currentConv.messages.slice(0, idx);
      const nextMessages = [...prefix, editedUser];
      setConversationMessages(nextMessages);

      if (!agentReady || !llmReady) {
        const errMsg: ChatMessage = {
          id: uid(),
          role: "assistant",
          content: !agentReady
            ? "No puedo recalcular porque el Agent Server no está online."
            : "No puedo recalcular todavía: el modelo LLM se está cargando.",
          error: true,
          ts: Date.now(),
        };
        upsertMessage(convId, errMsg);
        return;
      }

      const history = prefix.map((m) => ({ role: m.role, content: m.content }));
      await streamAssistantReply(editedUser.content, history);
      return;
    }

    const editedAssistant: ChatMessage = { ...msg, content: newText, error: false };
    const prefixThroughAssistant = [...currentConv.messages.slice(0, idx), editedAssistant];
    // Assistant edits are authoritative: trim all later messages so the user can continue manually.
    setConversationMessages(prefixThroughAssistant);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }

  const userTurns = messages.filter((m) => m.role === "user").length;

  function setConversationBehavior(behaviorId: string | undefined) {
    useStore.setState((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === convId ? { ...c, behaviorId, updatedAt: Date.now() } : c
      ),
    }));
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-2.5 border-b border-border shrink-0 gap-3">
        <div className="flex items-center gap-2 text-xs text-muted min-w-0">
          <Wrench size={12} className="text-accent shrink-0" />
          <span className="truncate">{userTurns > 0 ? `${userTurns} turnos` : "Nueva conversación"}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <select
            value={conv?.folderId ?? ""}
            onChange={(e) => setConversationFolder(convId, e.target.value || undefined)}
            className="bg-raised border border-border rounded-lg px-2 py-1 text-xs text-secondary"
            title="Carpeta de la conversación"
          >
            <option value="">Sin carpeta</option>
            {folders.map((f) => (
              <option key={f.id} value={f.id}>
                📁 {f.name}
              </option>
            ))}
          </select>
          {messages.length > 0 && <BehaviorBadge />}
          {messages.length > 0 && (
            <button
              className="btn-ghost text-xs px-2.5 py-1 flex items-center gap-1.5"
              onClick={() => clearConversation(convId)}
            >
              <RefreshCw size={11} />
              Limpiar
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div
        ref={listRef}
        className="flex-1 overflow-y-auto px-4 py-4 relative custom-scroll"
        onScroll={handleScroll}
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-8 animate-fadeIn">
            <Brain size={28} className="text-accent opacity-50" />
            <div>
              <p className="text-sm text-secondary font-medium">
                {behavior ? `${behavior.icon ?? "🤖"} ${behavior.name}` : "Sin comportamiento"}
              </p>
              <p className="text-xs text-muted mt-1">
                {behavior
                  ? "Listo para responder según este perfil"
                  : "Sin comportamiento, haga clic abajo si quiere cambiar el comportamiento"}
              </p>
            </div>
            {!behavior && (
              <div className="w-full max-w-2xl pt-2">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
                  {behaviors.map((b) => (
                    <button
                      key={b.id}
                      onClick={() => setConversationBehavior(b.id)}
                      className="text-left bg-raised border border-border rounded-xl px-3 py-2.5 hover:border-accent/40 hover:bg-accent/5 transition-colors"
                    >
                      <p className="text-sm text-primary font-medium">
                        {b.icon ?? "🤖"} {b.name}
                      </p>
                      <p className="text-[11px] text-muted mt-1 line-clamp-2">
                        {b.content}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          messages.map((msg, i) => (
            editingId === msg.id ? (
              <div key={msg.id} className={`mb-4 ${msg.role === "user" ? "flex justify-end" : ""}`}>
                <div className={`bg-raised border border-border rounded-xl p-3 space-y-2 ${msg.role === "user" ? "w-[72%]" : "ml-10"}`}>
                  <textarea
                    value={editingText}
                    onChange={(e) => setEditingText(e.target.value)}
                    rows={4}
                    className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-primary outline-none focus:border-accent/50 resize-y"
                  />
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => { setEditingId(null); setEditingText(""); }}
                      className="btn-ghost text-xs px-3 py-1.5 flex items-center gap-1"
                    >
                      <X size={12} />
                      Cancelar
                    </button>
                    <button
                      onClick={() => saveEditAndRecalculate(msg)}
                      disabled={msg.role === "user" && (!agentReady || !llmReady || isStreaming)}
                      className="btn-primary text-xs px-3 py-1.5 flex items-center gap-1 disabled:opacity-40"
                    >
                      <Check size={12} />
                      Guardar y recalcular
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <Message
                key={msg.id}
                msg={msg}
                isStreaming={isStreaming && i === messages.length - 1 && msg.role === "assistant"}
                canEdit={!isStreaming}
                onEdit={() => startEdit(msg)}
              />
            )
          ))
        )}
        <div ref={bottomRef} />

        {showScrollBtn && (
          <button
            className="sticky bottom-2 float-right mr-2 w-8 h-8 rounded-full bg-raised border border-border flex items-center justify-center text-muted hover:text-primary transition-colors shadow-md"
            onClick={() => scrollToBottom()}
          >
            <ChevronDown size={16} />
          </button>
        )}
      </div>

      {/* Input */}
      <div className="px-4 pb-4 pt-2 shrink-0">
        <div className="flex items-center gap-2 mb-2">
          <button
            onClick={() => setPlanArmed((p) => !p)}
            aria-pressed={planArmed}
            className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
              planArmed
                ? "border-accent/50 text-accent bg-accent/15"
                : "border-border text-muted hover:text-primary hover:bg-surface-2"
            }`}
            title="Afecta solo al primer envío de esta conversación"
          >
            Modo Plan
          </button>
          <button
            onClick={() => setIteratorMode((p) => !p)}
            aria-pressed={iteratorMode}
            className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
              iteratorMode
                ? "border-accent/50 text-accent bg-accent/15"
                : "border-border text-muted hover:text-primary hover:bg-surface-2"
            }`}
            title="Modo agente iterador"
          >
            Iterador
          </button>
          {planWorkflowActive && (
            <>
              <button
                onClick={async () => {
                  if (isStreaming) return;
                  const txt = "ejecutar plan";
                  const userMsg: ChatMessage = { id: uid(), role: "user", content: txt, ts: Date.now() };
                  upsertMessage(convId, userMsg);
                  const history = [...messages, userMsg].slice(0, -1).map((m) => ({ role: m.role, content: m.content }));
                  setPlanWorkflowActive(false);
                  await streamAssistantReply(txt, history, "iterate");
                }}
                className="btn-ghost text-xs px-2.5 py-1 border-green-900/40 text-green-400 hover:bg-green-900/10"
              >
                Ejecutar plan
              </button>
              <button
                onClick={() => setInput("editar plan: ")}
                className="btn-ghost text-xs px-2.5 py-1"
              >
                Editar plan
              </button>
              <button
                onClick={() => { setPlanWorkflowActive(false); setInput("descartar plan"); }}
                className="btn-ghost text-xs px-2.5 py-1 border-red-900/40 text-red-400 hover:bg-red-900/10"
              >
                Descartar
              </button>
            </>
          )}
        </div>
        <div className="flex items-end gap-2 bg-raised border border-border rounded-xl p-2 focus-within:border-accent/50 focus-within:shadow-[0_0_0_3px_rgba(124,106,245,0.08)] transition-all">
          <textarea
            id="chat-input"
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={
              !agentReady ? "Esperando al agente…" :
              !llmReady  ? "Cargando modelo LLM… (puede tardar 1-2 min)" :
                           "Escribí tu consulta… (Enter para enviar)"
            }
            disabled={!agentReady || !llmReady || isStreaming}
            className="flex-1 bg-transparent text-sm text-primary placeholder-muted outline-none resize-none leading-relaxed py-1 px-1 selectable disabled:opacity-40"
            style={{ minHeight: 24, maxHeight: 160 }}
          />
          <button
            onClick={handleSend}
            disabled={!agentReady || !llmReady || isStreaming || !input.trim()}
            className="btn-primary shrink-0 w-8 h-8 flex items-center justify-center rounded-lg"
          >
            {isStreaming ? (
              <div className="w-3.5 h-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
            ) : (
              <Send size={14} />
            )}
          </button>
        </div>
        <p className="text-[10px] text-muted mt-1.5 text-center">
          Shift+Enter para nueva línea · las respuestas pueden incluir pasos de herramientas
        </p>
      </div>
    </div>
  );
}

// ─── ChatView (router) ────────────────────────────────────────────────────────

export default function ChatView() {
  const activeConvId = useStore((s) => s.activeConvId);
  return activeConvId ? <ActiveChat convId={activeConvId} /> : <Welcome />;
}
