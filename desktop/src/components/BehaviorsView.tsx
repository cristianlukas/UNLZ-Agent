import { useState } from "react";
import { Plus, Pencil, Trash2, Save, X, Brain } from "lucide-react";
import { useStore } from "../lib/store";
import type { Behavior } from "../lib/types";

// ─── Behavior editor ──────────────────────────────────────────────────────────

function BehaviorEditor({
  behavior,
  onSave,
  onCancel,
}: {
  behavior: Partial<Behavior>;
  onSave: (name: string, content: string, icon: string, model: string, harness: string) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(behavior.name ?? "");
  const [icon, setIcon] = useState(behavior.icon ?? "🤖");
  const [content, setContent] = useState(behavior.content ?? "");
  const [model, setModel] = useState(behavior.model ?? "");
  const [harness, setHarness] = useState(behavior.harness ?? "");

  const EMOJI_PRESETS = ["🤖", "🎓", "💻", "🔬", "📝", "🌐", "🎨", "⚙️", "📊", "🧠"];

  return (
    <div className="flex flex-col gap-4 p-5 bg-surface border border-border rounded-xl">
      {/* Name + icon */}
      <div className="flex items-center gap-3">
        <div className="relative group">
          <button className="w-10 h-10 rounded-lg bg-raised border border-border text-lg flex items-center justify-center hover:border-accent/40 transition-colors">
            {icon}
          </button>
          {/* Emoji picker */}
          <div className="absolute top-12 left-0 z-10 hidden group-focus-within:flex flex-wrap gap-1 bg-raised border border-border rounded-lg p-2 shadow-xl w-48">
            {EMOJI_PRESETS.map((e) => (
              <button
                key={e}
                onClick={() => setIcon(e)}
                className="w-7 h-7 text-base rounded hover:bg-base transition-colors"
              >
                {e}
              </button>
            ))}
          </div>
        </div>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nombre del comportamiento"
          className="flex-1 bg-raised border border-border rounded-lg px-3 py-2 text-sm text-primary outline-none focus:border-accent/50 transition-colors placeholder-muted"
        />
      </div>

      {/* Emoji quick-select row */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-muted">Ícono:</span>
        {EMOJI_PRESETS.map((e) => (
          <button
            key={e}
            onClick={() => setIcon(e)}
            className={`w-7 h-7 text-base rounded transition-colors ${
              icon === e ? "bg-accent/20 ring-1 ring-accent/50" : "hover:bg-raised"
            }`}
          >
            {e}
          </button>
        ))}
      </div>

      {/* System prompt content */}
      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">
          System prompt (Markdown soportado)
        </label>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Describí cómo debe comportarse el agente…"
          rows={10}
          className="w-full bg-base border border-border rounded-lg px-3 py-2.5 text-sm text-primary font-mono outline-none focus:border-accent/50 transition-colors resize-y placeholder-muted leading-relaxed"
        />
        <p className="text-[10px] text-muted mt-1">
          {content.length} caracteres · {content.split("\n").length} líneas
        </p>
      </div>

      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">
          Modelo (opcional)
        </label>
        <input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="ej: gemma-4-31b-it-q4_k_m"
          className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-primary font-mono outline-none focus:border-accent/50 transition-colors placeholder-muted"
        />
        <p className="text-[10px] text-muted mt-1">
          Si se completa, este comportamiento intenta usar ese modelo primero.
        </p>
      </div>

      <div>
        <label className="block text-xs font-medium text-muted mb-1.5">
          Harness (opcional)
        </label>
        <select
          value={harness}
          onChange={(e) => setHarness(e.target.value)}
          className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-primary outline-none focus:border-accent/50 transition-colors"
        >
          <option value="">Usar harness global</option>
          <option value="native">UNLZ-AGENT nativo</option>
          <option value="claude-code">claude-code</option>
          <option value="opencode">opencode</option>
          <option value="little-coder">little-coder</option>
        </select>
        <p className="text-[10px] text-muted mt-1">
          Si se define, este comportamiento fuerza ese harness para la conversación.
        </p>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-2">
        <button
          onClick={onCancel}
          className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-sm"
        >
          <X size={14} />
          Cancelar
        </button>
        <button
          onClick={() => name.trim() && content.trim() && onSave(name.trim(), content, icon, model.trim(), harness.trim())}
          disabled={!name.trim() || !content.trim()}
          className="btn-primary flex items-center gap-1.5 px-4 py-1.5 text-sm disabled:opacity-40"
        >
          <Save size={14} />
          Guardar
        </button>
      </div>
    </div>
  );
}

// ─── Behavior card ────────────────────────────────────────────────────────────

function BehaviorCard({
  behavior,
  onEdit,
  onDelete,
  onUse,
}: {
  behavior: Behavior;
  onEdit: () => void;
  onDelete: () => void;
  onUse: () => void;
}) {
  const isDefault = behavior.id.startsWith("default-");
  return (
    <div className="group flex flex-col gap-3 p-4 bg-surface border border-border rounded-xl hover:border-border-strong transition-colors hover:border-[#3a3a60]">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="text-xl">{behavior.icon ?? "🤖"}</span>
          <div>
            <h3 className="text-sm font-semibold text-primary">{behavior.name}</h3>
            {isDefault && (
              <span className="text-[10px] text-muted bg-raised px-1.5 py-0.5 rounded font-medium">
                predeterminado
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={onEdit}
            className="p-1.5 rounded-md text-muted hover:text-primary hover:bg-raised transition-colors"
            title="Editar"
          >
            <Pencil size={13} />
          </button>
          {!isDefault && (
            <button
              onClick={onDelete}
              className="p-1.5 rounded-md text-muted hover:text-red-400 hover:bg-raised transition-colors"
              title="Eliminar"
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Preview */}
      <p className="text-xs text-secondary leading-relaxed line-clamp-3 font-mono bg-base rounded-lg px-3 py-2 border border-border">
        {behavior.content}
      </p>
      {behavior.model?.trim() && (
        <p className="text-[10px] text-muted font-mono">
          Modelo: {behavior.model}
        </p>
      )}
      {behavior.harness?.trim() && (
        <p className="text-[10px] text-muted font-mono">
          Harness: {behavior.harness}
        </p>
      )}

      <button
        onClick={onUse}
        className="btn-ghost text-xs px-3 py-1.5 self-start flex items-center gap-1.5"
      >
        <Brain size={12} />
        Usar en nueva conversación
      </button>
    </div>
  );
}

// ─── BehaviorsView ────────────────────────────────────────────────────────────

type EditorState =
  | { mode: "new" }
  | { mode: "edit"; behavior: Behavior }
  | null;

export default function BehaviorsView() {
  const { behaviors, createBehavior, updateBehavior, deleteBehavior, createConversation } =
    useStore();
  const [editor, setEditor] = useState<EditorState>(null);

  function handleSaveNew(name: string, content: string, icon: string, model: string, harness: string) {
    createBehavior(name, content, icon, model, harness);
    setEditor(null);
  }

  function handleSaveEdit(id: string, name: string, content: string, icon: string, model: string, harness: string) {
    updateBehavior(id, { name, content, icon, model, harness });
    setEditor(null);
  }

  function handleUse(behaviorId: string) {
    createConversation(behaviorId);
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
        <div>
          <h2 className="text-base font-semibold text-primary">Comportamientos</h2>
          <p className="text-xs text-muted mt-0.5">
            Perfiles de system prompt — definen cómo responde el agente
          </p>
        </div>
        {!editor && (
          <button
            onClick={() => setEditor({ mode: "new" })}
            className="btn-primary flex items-center gap-1.5 px-3 py-1.5 text-sm"
          >
            <Plus size={14} />
            Nuevo
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 py-5 custom-scroll">
        {/* Editor (new or edit) */}
        {editor && (
          <div className="mb-6">
            <h3 className="text-sm font-semibold text-primary mb-3">
              {editor.mode === "new" ? "Nuevo comportamiento" : "Editar comportamiento"}
            </h3>
            {editor.mode === "new" ? (
              <BehaviorEditor
                behavior={{}}
                onSave={handleSaveNew}
                onCancel={() => setEditor(null)}
              />
            ) : (
              <BehaviorEditor
                behavior={editor.behavior}
                onSave={(name, content, icon, model, harness) =>
                  handleSaveEdit(editor.behavior.id, name, content, icon, model, harness)
                }
                onCancel={() => setEditor(null)}
              />
            )}
          </div>
        )}

        {/* Cards grid */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {behaviors.map((b) => (
            <BehaviorCard
              key={b.id}
              behavior={b}
              onEdit={() => setEditor({ mode: "edit", behavior: b })}
              onDelete={() => deleteBehavior(b.id)}
              onUse={() => handleUse(b.id)}
            />
          ))}
        </div>

        {behaviors.length === 0 && !editor && (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Brain size={36} className="text-muted opacity-30" />
            <p className="text-sm text-muted">Sin comportamientos configurados</p>
            <button
              onClick={() => setEditor({ mode: "new" })}
              className="btn-primary text-sm px-4 py-2 mt-1"
            >
              Crear el primero
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
