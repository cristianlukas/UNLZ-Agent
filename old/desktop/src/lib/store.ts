import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Behavior, ChatMessage, Conversation, Folder, HubUpdateNotification, View } from "./types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

let _counter = Date.now();
const uid = () => (++_counter).toString(36);

function autoTitle(messages: ChatMessage[]): string {
  const first = messages.find((m) => m.role === "user");
  if (!first) return "Nueva conversación";
  const text = first.content.trim();
  return text.length > 48 ? text.slice(0, 48) + "…" : text;
}

// ─── Default behaviors ────────────────────────────────────────────────────────

const DEFAULT_BEHAVIORS: Behavior[] = [
  {
    id: "default-es",
    name: "Asistente UNLZ",
    icon: "🎓",
    content: `Eres un asistente inteligente de la Universidad Nacional de Lomas de Zamora (UNLZ).
Tenés acceso a herramientas: búsqueda de conocimiento local (RAG), búsqueda web, hora, stats del sistema.
Usá las herramientas proactivamente para responder con precisión.
Formateá las respuestas en Markdown. Sé conciso y preciso.`,
    model: "",
    harness: "",
    defaultInternetEnabled: true,
    defaultToolsMode: "auto",
    createdAt: 0,
    updatedAt: 0,
  },
  {
    id: "default-dev",
    name: "Dev / Código",
    icon: "💻",
    content: `Eres un asistente experto en programación.
Respondé siempre con código limpio, bien comentado y con explicaciones concisas.
Preferí TypeScript, Python o Rust según el contexto.
Formateá el código con bloques de código con el lenguaje indicado.`,
    model: "",
    harness: "claude-code",
    defaultInternetEnabled: true,
    defaultToolsMode: "auto",
    createdAt: 0,
    updatedAt: 0,
  },
  {
    id: "default-research",
    name: "Investigación",
    icon: "🔬",
    content: `Eres un asistente de investigación académica.
Antes de responder, buscá en la base de conocimiento local y en la web.
Citá fuentes cuando sea posible. Sé exhaustivo pero organizado.
Usá encabezados Markdown para estructurar respuestas largas.`,
    model: "",
    harness: "",
    defaultInternetEnabled: true,
    defaultToolsMode: "auto",
    createdAt: 0,
    updatedAt: 0,
  },
  {
    id: "default-chat-gemma",
    name: "Charla",
    icon: "💬",
    content: `Sos un asistente conversacional natural y cálido, optimizado para charla general en español.
Priorizá respuestas directas, claras y fluidas.
En preguntas simples, respondé sin usar herramientas.
Usá herramientas solo si el usuario pide explícitamente investigar, buscar datos actuales o verificar información.
Mantené coherencia de contexto y evitá repeticiones innecesarias.`,
    model: "gemma-4-31b-it-q4_k_m",
    harness: "",
    defaultInternetEnabled: true,
    defaultToolsMode: "without_tools",
    createdAt: 0,
    updatedAt: 0,
  },
  {
    id: "default-vision",
    name: "Visión",
    icon: "👁️",
    content: `Sos un asistente experto en análisis visual y OCR con Gemma 4 Vision.
Objetivo: extraer texto, tablas y detalles visuales finos de imágenes/documentos.
Reglas:
- Priorizá precisión literal en OCR (nombres, números, fechas, IDs, montos).
- Si el texto es ambiguo o borroso, indicá fragmentos dudosos explícitamente.
- Para documentos largos, devolvé salida estructurada: resumen + campos clave + texto extraído.
- Evitá inventar datos no visibles en la imagen.
- Cuando corresponda, proponé una segunda pasada enfocada en zonas críticas.`,
    model: "gemma-4-31b-it-q4_k_m",
    harness: "",
    defaultInternetEnabled: true,
    defaultToolsMode: "with_tools",
    createdAt: 0,
    updatedAt: 0,
  },
];

function normalizeBehaviorRecord(b: Behavior): Behavior {
  const normalizedToolsMode =
    b.defaultToolsMode === "with_tools" || b.defaultToolsMode === "without_tools" || b.defaultToolsMode === "auto"
      ? b.defaultToolsMode
      : "auto";
  const baseBehavior: Behavior = {
    ...b,
    harness: (b.harness || "").trim(),
    defaultInternetEnabled:
      typeof b.defaultInternetEnabled === "boolean" ? b.defaultInternetEnabled : true,
    defaultToolsMode: normalizedToolsMode,
  };
  const isHeretic = /heretic/i.test(String(b.id || "")) || /heretic/i.test(String(b.name || ""));
  if (b.id === "default-chat-gemma") {
    return {
      ...baseBehavior,
      name: b.name?.trim() ? b.name : "Charla",
      model: (b.model || "").trim() || "gemma-4-31b-it-q4_k_m",
      defaultToolsMode: normalizedToolsMode === "auto" ? "without_tools" : normalizedToolsMode,
    };
  }
  if (b.id === "default-dev") {
    return {
      ...baseBehavior,
      harness: (b.harness || "").trim() || "claude-code",
    };
  }
  if (isHeretic) {
    return {
      ...baseBehavior,
      defaultInternetEnabled: false,
    };
  }
  return baseBehavior;
}

function mergeDefaultBehaviors(existing?: Behavior[]): Behavior[] {
  const current = existing ? [...existing] : [];
  const normalized = current.map((b) => normalizeBehaviorRecord(b));
  const existingIds = new Set(normalized.map((b) => b.id));
  const missingDefaults = DEFAULT_BEHAVIORS.filter((b) => !existingIds.has(b.id));
  return [...normalized, ...missingDefaults];
}

// ─── Store types ──────────────────────────────────────────────────────────────

interface AppStore {
  // Navigation
  view: View;
  setView: (v: View) => void;

  // Agent status (runtime, not persisted)
  agentReady: boolean;
  setAgentReady: (v: boolean) => void;
  llmReady: boolean;
  setLlmReady: (v: boolean) => void;
  llmState: "ready" | "loading" | "not_loaded";
  llmStateMessage: string;
  setLlmStatus: (state: "ready" | "loading" | "not_loaded", message?: string) => void;
  provider: string;
  modelAlias: string;
  setProviderInfo: (provider: string, alias: string) => void;
  pendingDraftByConv: Record<string, string>;
  setPendingDraft: (convId: string, text: string) => void;
  consumePendingDraft: (convId: string) => string;

  // Conversations
  conversations: Conversation[];
  activeConvId: string | null;
  createConversation: (behaviorId?: string, folderId?: string) => string;
  deleteConversation: (id: string) => void;
  renameConversation: (id: string, title: string) => void;
  setConversationFolder: (convId: string, folderId?: string) => void;
  setActiveConv: (id: string | null) => void;
  appendMessages: (convId: string, messages: ChatMessage[]) => void;
  upsertMessage: (convId: string, msg: ChatMessage) => void;
  clearConversation: (id: string) => void;

  // Behaviors
  behaviors: Behavior[];
  createBehavior: (
    name: string,
    content: string,
    icon?: string,
    model?: string,
    harness?: string,
    defaultInternetEnabled?: boolean,
    defaultToolsMode?: Behavior["defaultToolsMode"],
    llamacpp?: Behavior["llamacpp"]
  ) => string;
  updateBehavior: (id: string, updates: Partial<Omit<Behavior, "id" | "createdAt">>) => void;
  deleteBehavior: (id: string) => void;
  upsertBehaviors: (items: Behavior[]) => void;

  // Folders
  folders: Folder[];
  createFolder: (name: string) => string;
  updateFolder: (id: string, updates: Partial<Omit<Folder, "id" | "createdAt">>) => void;
  deleteFolder: (id: string) => void;

  // Dev mode
  devMode: boolean;
  setDevMode: (v: boolean) => void;

  // Hub — update notifications (partially persisted)
  hubUpdateNotification: HubUpdateNotification | null;
  setHubUpdateNotification: (n: HubUpdateNotification | null) => void;
  skippedHubModelIds: string[];          // persisted: never show again for this model
  snoozedHubUntil: number | null;        // persisted: snooze timestamp
  skipHubModel: (modelId: string) => void;
  snoozeHubUpdate: (ms?: number) => void; // default 24 h
  clearHubSnooze: () => void;
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useStore = create<AppStore>()(
  persist(
    (set, get) => ({
      // ── Navigation ──────────────────────────────────────────────────────────
      view: "chat",
      setView: (v) => set({ view: v }),

      // ── Agent status (runtime, not stored) ──────────────────────────────────
      agentReady: false,
      setAgentReady: (v) => set({ agentReady: v }),
      llmReady: false,
      setLlmReady: (v) => set({ llmReady: v }),
      llmState: "not_loaded",
      llmStateMessage: "",
      setLlmStatus: (state, message) => set({ llmState: state, llmStateMessage: message ?? "" }),
      provider: "…",
      modelAlias: "…",
      setProviderInfo: (provider, modelAlias) => set({ provider, modelAlias }),
      pendingDraftByConv: {},
      setPendingDraft: (convId, text) =>
        set((s) => ({
          pendingDraftByConv: {
            ...s.pendingDraftByConv,
            [convId]: text,
          },
        })),
      consumePendingDraft: (convId) => {
        const current = get().pendingDraftByConv[convId] ?? "";
        set((s) => {
          const next = { ...s.pendingDraftByConv };
          delete next[convId];
          return { pendingDraftByConv: next };
        });
        return current;
      },

      // ── Conversations ────────────────────────────────────────────────────────
      conversations: [],
      activeConvId: null,

      createConversation: (behaviorId, folderId) => {
        const id = uid();
        const conv: Conversation = {
          id,
          title: "Nueva conversación",
          createdAt: Date.now(),
          updatedAt: Date.now(),
          messages: [],
          behaviorId,
          folderId,
        };
        set((s) => ({
          conversations: [conv, ...s.conversations],
          activeConvId: id,
          view: "chat",
        }));
        return id;
      },

      deleteConversation: (id) =>
        set((s) => {
          const remaining = s.conversations.filter((c) => c.id !== id);
          const nextId = s.activeConvId === id
            ? (remaining[0]?.id ?? null)
            : s.activeConvId;
          return { conversations: remaining, activeConvId: nextId };
        }),

      renameConversation: (id, title) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === id ? { ...c, title, updatedAt: Date.now() } : c
          ),
        })),

      setConversationFolder: (convId, folderId) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === convId ? { ...c, folderId, updatedAt: Date.now() } : c
          ),
        })),

      setActiveConv: (id) => set({ activeConvId: id }),

      appendMessages: (convId, messages) =>
        set((s) => ({
          conversations: s.conversations.map((c) => {
            if (c.id !== convId) return c;
            const updated = { ...c, messages: [...c.messages, ...messages], updatedAt: Date.now() };
            // Auto-title from first user message
            if (updated.title === "Nueva conversación") {
              updated.title = autoTitle(updated.messages);
            }
            return updated;
          }),
        })),

      upsertMessage: (convId, msg) =>
        set((s) => ({
          conversations: s.conversations.map((c) => {
            if (c.id !== convId) return c;
            const exists = c.messages.some((m) => m.id === msg.id);
            const messages = exists
              ? c.messages.map((m) => (m.id === msg.id ? msg : m))
              : [...c.messages, msg];
            const updated = { ...c, messages, updatedAt: Date.now() };
            if (updated.title === "Nueva conversación") {
              updated.title = autoTitle(updated.messages);
            }
            return updated;
          }),
        })),

      clearConversation: (id) =>
        set((s) => ({
          conversations: s.conversations.map((c) =>
            c.id === id
              ? { ...c, messages: [], title: "Nueva conversación", updatedAt: Date.now() }
              : c
          ),
        })),

      // ── Behaviors ────────────────────────────────────────────────────────────
      behaviors: DEFAULT_BEHAVIORS,

      createBehavior: (
        name,
        content,
        icon,
        model,
        harness,
        defaultInternetEnabled = true,
        defaultToolsMode = "auto",
        llamacpp
      ) => {
        const id = uid();
        const now = Date.now();
        set((s) => ({
          behaviors: [
            ...s.behaviors,
            {
              id,
              name,
              content,
              icon,
              model,
              harness,
              defaultInternetEnabled,
              defaultToolsMode,
              llamacpp,
              createdAt: now,
              updatedAt: now,
            },
          ],
        }));
        return id;
      },

      updateBehavior: (id, updates) =>
        set((s) => ({
          behaviors: s.behaviors.map((b) =>
            b.id === id ? { ...b, ...updates, updatedAt: Date.now() } : b
          ),
        })),

      deleteBehavior: (id) =>
        set((s) => ({
          behaviors: s.behaviors.filter((b) => b.id !== id),
          // Clear behaviorId from any conversations using it
          conversations: s.conversations.map((c) =>
            c.behaviorId === id ? { ...c, behaviorId: undefined } : c
          ),
          folders: s.folders.map((f) =>
            f.behaviorId === id ? { ...f, behaviorId: undefined, updatedAt: Date.now() } : f
          ),
        })),

      upsertBehaviors: (items) =>
        set((s) => {
          if (!items?.length) return { behaviors: s.behaviors };
          const byId = new Map(s.behaviors.map((b) => [b.id, b] as const));
          for (const it of items) {
            if (!it?.id) continue;
            const prev = byId.get(it.id);
            const merged = prev ? ({ ...prev, ...it } as Behavior) : (it as Behavior);
            byId.set(it.id, normalizeBehaviorRecord(merged));
          }
          return { behaviors: Array.from(byId.values()) };
        }),

      // ── Folders ────────────────────────────────────────────────────────────
      folders: [],

      createFolder: (name) => {
        const id = uid();
        const now = Date.now();
        set((s) => ({
          folders: [
            {
              id,
              name,
              createdAt: now,
              updatedAt: now,
            },
            ...s.folders,
          ],
        }));
        return id;
      },

      updateFolder: (id, updates) =>
        set((s) => ({
          folders: s.folders.map((f) =>
            f.id === id ? { ...f, ...updates, updatedAt: Date.now() } : f
          ),
        })),

      deleteFolder: (id) =>
        set((s) => ({
          folders: s.folders.filter((f) => f.id !== id),
          conversations: s.conversations.map((c) =>
            c.folderId === id ? { ...c, folderId: undefined, updatedAt: Date.now() } : c
          ),
        })),

      // ── Dev mode ─────────────────────────────────────────────────────────────
      devMode: false,
      setDevMode: (v) => set({ devMode: v }),

      // ── Hub ──────────────────────────────────────────────────────────────────
      hubUpdateNotification: null,
      setHubUpdateNotification: (n) => set({ hubUpdateNotification: n }),
      skippedHubModelIds: [],
      snoozedHubUntil: null,
      skipHubModel: (modelId) =>
        set((s) => ({
          skippedHubModelIds: s.skippedHubModelIds.includes(modelId)
            ? s.skippedHubModelIds
            : [...s.skippedHubModelIds, modelId],
        })),
      snoozeHubUpdate: (ms = 24 * 60 * 60 * 1000) =>
        set({ snoozedHubUntil: Date.now() + ms }),
      clearHubSnooze: () =>
        set({ snoozedHubUntil: null }),
    }),
    {
      name: "unlz-agent-store",
      // Don't persist runtime state
      partialize: (s) => ({
        view: s.view,
        conversations: s.conversations,
        activeConvId: s.activeConvId,
        behaviors: s.behaviors,
        folders: s.folders,
        skippedHubModelIds: s.skippedHubModelIds,
        snoozedHubUntil: s.snoozedHubUntil,
        devMode: s.devMode,
      }),
      merge: (persisted, current) => {
        const p = (persisted as Partial<AppStore>) || {};
        return {
          ...current,
          ...p,
          behaviors: mergeDefaultBehaviors(p.behaviors ?? current.behaviors),
        };
      },
    }
  )
);

// ─── Selectors ────────────────────────────────────────────────────────────────

export const useActiveConv = () => {
  const conversations = useStore((s) => s.conversations);
  const activeConvId = useStore((s) => s.activeConvId);
  return conversations.find((c) => c.id === activeConvId) ?? null;
};

export const useActiveBehavior = () => {
  const behaviors = useStore((s) => s.behaviors);
  const conversations = useStore((s) => s.conversations);
  const activeConvId = useStore((s) => s.activeConvId);
  const conv = conversations.find((c) => c.id === activeConvId);
  if (!conv?.behaviorId) return null;
  return behaviors.find((b) => b.id === conv.behaviorId) ?? null;
};

export const useActiveFolder = () => {
  const folders = useStore((s) => s.folders);
  const conversations = useStore((s) => s.conversations);
  const activeConvId = useStore((s) => s.activeConvId);
  const conv = conversations.find((c) => c.id === activeConvId);
  if (!conv?.folderId) return null;
  return folders.find((f) => f.id === conv.folderId) ?? null;
};
