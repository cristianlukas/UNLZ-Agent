import { useState, useRef } from "react";
import {
  Plus,
  MessageSquare,
  BookOpen,
  FolderClosed,
  Activity,
  Settings,
  Trash2,
  Pencil,
  Check,
  X,
  Brain,
  Sparkles,
  Terminal,
} from "lucide-react";
import { useStore } from "../lib/store";
import type { Conversation, Folder, View } from "../lib/types";

// ─── Conversation item ────────────────────────────────────────────────────────

function ConvItem({
  conv,
  active,
  onSelect,
  onDelete,
  onRename,
}: {
  conv: Conversation;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRename: (title: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conv.title);
  const inputRef = useRef<HTMLInputElement>(null);

  function startEdit(e: React.MouseEvent) {
    e.stopPropagation();
    setDraft(conv.title);
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 10);
  }

  function commitEdit() {
    const t = draft.trim();
    if (t) onRename(t);
    setEditing(false);
  }

  function cancelEdit(e?: React.MouseEvent) {
    e?.stopPropagation();
    setEditing(false);
    setDraft(conv.title);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") commitEdit();
    if (e.key === "Escape") cancelEdit();
  }

  const date = new Date(conv.updatedAt);
  const timeStr = date.toLocaleDateString("es-AR", { month: "short", day: "numeric" });

  return (
    <div
      className={`group relative flex items-start gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors text-sm
        ${active
          ? "bg-raised border border-border-strong text-primary"
          : "hover:bg-surface-2 border border-transparent text-secondary hover:text-primary"
        }`}
      onClick={() => !editing && onSelect()}
    >
      <MessageSquare
        size={13}
        className={`shrink-0 mt-0.5 ${active ? "text-secondary" : "text-muted"}`}
      />

      <div className="flex-1 min-w-0">
        {editing ? (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={handleKeyDown}
              className="flex-1 bg-base border border-accent/40 rounded px-1.5 py-0.5 text-xs text-primary outline-none min-w-0"
            />
            <button onClick={commitEdit} className="text-accent hover:text-accent-light">
              <Check size={12} />
            </button>
            <button onClick={cancelEdit} className="text-muted hover:text-secondary">
              <X size={12} />
            </button>
          </div>
        ) : (
          <>
            <p className="text-xs font-medium leading-snug truncate">{conv.title}</p>
            <p className={`text-[10px] mt-0.5 ${active ? "text-secondary" : "text-muted"}`}>{timeStr}</p>
          </>
        )}
      </div>

      {!editing && (
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button
            onClick={startEdit}
            className="p-0.5 rounded text-muted hover:text-primary"
            title="Renombrar"
          >
            <Pencil size={11} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="p-0.5 rounded text-muted hover:text-red-400"
            title="Eliminar"
          >
            <Trash2 size={11} />
          </button>
        </div>
      )}
    </div>
  );
}

function sortConversations(convs: Conversation[]) {
  return [...convs].sort((a, b) => b.updatedAt - a.updatedAt);
}

function FolderGroup({
  folder,
  conversations,
  activeConvId,
  view,
  onSelect,
  onDelete,
  onRename,
  onNewInFolder,
}: {
  folder: Folder;
  conversations: Conversation[];
  activeConvId: string | null;
  view: View;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onNewInFolder: (folderId: string) => void;
}) {
  return (
    <div className="mb-2">
      <div className="px-2 py-1 flex items-center justify-between">
        <p className="text-[10px] font-semibold text-muted uppercase tracking-wider truncate">
          📁 {folder.name}
        </p>
        <button
          onClick={() => onNewInFolder(folder.id)}
          className="p-1 rounded text-muted hover:text-primary hover:bg-raised"
          title="Nueva conversación en carpeta"
        >
          <Plus size={11} />
        </button>
      </div>
      <div className="space-y-0.5">
        {conversations.length === 0 ? (
          <p className="px-2 py-1 text-[10px] text-muted opacity-70">Sin conversaciones</p>
        ) : (
          conversations.map((conv) => (
            <ConvItem
              key={conv.id}
              conv={conv}
              active={conv.id === activeConvId && view === "chat"}
              onSelect={() => onSelect(conv.id)}
              onDelete={() => onDelete(conv.id)}
              onRename={(title) => onRename(conv.id, title)}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ─── Nav icons (bottom) ───────────────────────────────────────────────────────

const BOTTOM_NAV: { id: View; icon: React.ReactNode; label: string }[] = [
  { id: "folders",   icon: <FolderClosed size={16} />, label: "Carpetas"        },
  { id: "behaviors", icon: <Brain size={16} />,        label: "Comportamientos" },
  { id: "knowledge", icon: <BookOpen size={16} />,     label: "Documentos"      },
  { id: "hub",       icon: <Sparkles size={16} />,     label: "Modelos"         },
  { id: "system",    icon: <Activity size={16} />,     label: "Sistema"         },
  { id: "settings",  icon: <Settings size={16} />,     label: "Configuración"   },
];

// ─── ConversationSidebar ──────────────────────────────────────────────────────

export default function ConversationSidebar() {
  const {
    view, setView,
    folders,
    conversations, activeConvId,
    createConversation, deleteConversation, renameConversation, setActiveConv,
    hubUpdateNotification, skippedHubModelIds, snoozedHubUntil,
    devMode,
  } = useStore();

  const hasHubUpdate = (() => {
    if (!hubUpdateNotification) return false;
    const isSnoozed = snoozedHubUntil !== null && Date.now() < snoozedHubUntil;
    const isSkipped = skippedHubModelIds.includes(hubUpdateNotification.recommended.id);
    return !isSnoozed && !isSkipped;
  })();
  const ungrouped = sortConversations(conversations.filter((c) => !c.folderId));
  const byFolder = folders.map((f) => ({
    folder: f,
    items: sortConversations(conversations.filter((c) => c.folderId === f.id)),
  }));

  function handleNew() {
    createConversation();
  }

  function handleSelect(id: string) {
    setActiveConv(id);
    setView("chat");
  }

  return (
    <aside className="conv-sidebar flex flex-col bg-surface border-r border-border shrink-0">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-border">
        <span className="text-xs font-semibold text-muted uppercase tracking-wider">Chats</span>
        <button
          onClick={handleNew}
          className="p-1 rounded-md text-muted hover:text-primary hover:bg-raised transition-colors"
          title="Nueva conversación"
        >
          <Plus size={15} />
        </button>
      </div>

      {/* Conversation list */}
      <div className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5 custom-scroll">
        {conversations.length === 0 ? (
          <div className="px-2 py-8 text-center">
            <MessageSquare size={24} className="text-muted mx-auto mb-2 opacity-40" />
            <p className="text-xs text-muted">Sin conversaciones</p>
            <p className="text-[10px] text-muted opacity-60 mt-1">Hacé clic en + para empezar</p>
          </div>
        ) : (
          <>
            {byFolder.map(({ folder, items }) => (
              <FolderGroup
                key={folder.id}
                folder={folder}
                conversations={items}
                activeConvId={activeConvId}
                view={view}
                onSelect={handleSelect}
                onDelete={deleteConversation}
                onRename={renameConversation}
                onNewInFolder={(folderId) => createConversation(undefined, folderId)}
              />
            ))}
            <div>
              <p className="px-2 py-1 text-[10px] font-semibold text-muted uppercase tracking-wider">
                Sin carpeta
              </p>
              {ungrouped.length === 0 ? (
                <p className="px-2 py-1 text-[10px] text-muted opacity-70">Sin conversaciones</p>
              ) : (
                ungrouped.map((conv) => (
                  <ConvItem
                    key={conv.id}
                    conv={conv}
                    active={conv.id === activeConvId && view === "chat"}
                    onSelect={() => handleSelect(conv.id)}
                    onDelete={() => deleteConversation(conv.id)}
                    onRename={(title) => renameConversation(conv.id, title)}
                  />
                ))
              )}
            </div>
          </>
        )}
      </div>

      {/* Bottom nav */}
      <div className="border-t border-border px-2 py-2 flex flex-col gap-0.5">
        {devMode && (
          <button
            onClick={() => setView("devlog")}
            title="Dev Log"
            className={`relative flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs transition-colors w-full text-left
              ${view === "devlog"
                ? "bg-accent/10 text-accent"
                : "text-amber-500/70 hover:text-amber-400 hover:bg-surface-2"
              }`}
          >
            <Terminal size={16} />
            <span className="font-medium">Dev Log</span>
          </button>
        )}
        {BOTTOM_NAV.map((item) => (
          <button
            key={item.id}
            onClick={() => setView(item.id)}
            title={item.label}
            className={`relative flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs transition-colors w-full text-left
              ${view === item.id
                ? "bg-accent/10 text-accent"
                : "text-muted hover:text-primary hover:bg-surface-2"
              }`}
          >
            <span className="relative">
              {item.icon}
              {item.id === "hub" && hasHubUpdate && (
                <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-amber-400 shadow-[0_0_4px_rgba(251,191,36,0.7)]" />
              )}
            </span>
            <span className="font-medium">{item.label}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
