import { useEffect, useRef, useState } from "react";
import { FolderClosed, Plus, Trash2, Upload, MessageSquare, FolderOpen } from "lucide-react";
import { listFolderFiles, pickDirectory, uploadFolderFile } from "../lib/api";
import { useStore } from "../lib/store";

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 ** 2).toFixed(1)} MB`;
}

export default function FoldersView() {
  const {
    folders,
    behaviors,
    createFolder,
    updateFolder,
    deleteFolder,
    createConversation,
  } = useStore();
  const [selectedId, setSelectedId] = useState<string | null>(folders[0]?.id ?? null);
  const [newName, setNewName] = useState("");
  const [files, setFiles] = useState<Array<{ name: string; size: number; modified: number }>>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!selectedId && folders[0]?.id) setSelectedId(folders[0].id);
  }, [folders, selectedId]);

  const selected = folders.find((f) => f.id === selectedId) ?? null;

  async function loadFiles() {
    if (!selectedId) return;
    try {
      setFiles(await listFolderFiles(selectedId));
    } catch {
      setFiles([]);
    }
  }

  useEffect(() => {
    loadFiles();
  }, [selectedId]);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !selectedId) return;
    setUploading(true);
    try {
      await uploadFolderFile(selectedId, file);
      await loadFiles();
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  return (
    <div className="flex h-full overflow-hidden">
      <aside className="w-72 border-r border-border p-4 space-y-3 overflow-y-auto">
        <div className="flex items-center gap-2">
          <FolderClosed size={16} className="text-accent" />
          <h2 className="text-sm font-semibold text-primary">Carpetas</h2>
        </div>
        <div className="flex gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Nueva carpeta"
            className="flex-1 bg-raised border border-border rounded px-2 py-1.5 text-xs text-primary outline-none"
          />
          <button
            className="btn-primary px-2 py-1.5"
            onClick={() => {
              const name = newName.trim();
              if (!name) return;
              const id = createFolder(name);
              setSelectedId(id);
              setNewName("");
            }}
          >
            <Plus size={12} />
          </button>
        </div>
        <div className="space-y-1.5">
          {folders.map((f) => (
            <button
              key={f.id}
              onClick={() => setSelectedId(f.id)}
              className={`w-full text-left px-2.5 py-2 rounded-lg border text-xs ${
                selectedId === f.id
                  ? "bg-accent/10 border-accent/30 text-primary"
                  : "bg-raised border-border text-secondary hover:text-primary"
              }`}
            >
              {f.name}
            </button>
          ))}
        </div>
      </aside>

      <main className="flex-1 p-5 overflow-y-auto">
        {!selected ? (
          <div className="h-full flex items-center justify-center text-muted text-sm">
            Seleccioná una carpeta o creá una nueva.
          </div>
        ) : (
          <div className="space-y-5 max-w-3xl">
            <div className="flex items-center justify-between">
              <input
                value={selected.name}
                onChange={(e) => updateFolder(selected.id, { name: e.target.value })}
                className="bg-raised border border-border rounded px-3 py-2 text-sm text-primary outline-none w-80"
              />
              <div className="flex items-center gap-2">
                <button
                  className="btn-ghost px-3 py-1.5 text-xs flex items-center gap-1.5"
                  onClick={() => createConversation(undefined, selected.id)}
                >
                  <MessageSquare size={12} />
                  Nueva conversación en carpeta
                </button>
                <button
                  className="btn-ghost px-3 py-1.5 text-xs text-red-400 border-red-900/40 hover:bg-red-900/10 flex items-center gap-1.5"
                  onClick={() => {
                    deleteFolder(selected.id);
                    setSelectedId(null);
                  }}
                >
                  <Trash2 size={12} />
                  Eliminar carpeta
                </button>
              </div>
            </div>

            <section className="bg-surface border border-border rounded-xl p-4 space-y-3">
              <h3 className="text-xs uppercase tracking-wider text-muted font-semibold">Prompt de carpeta</h3>
              <div className="space-y-2">
                <label className="text-xs text-secondary">Carpeta sandbox (opcional)</label>
                <div className="flex gap-2">
                  <input
                    value={selected.sandboxPath ?? ""}
                    onChange={(e) => updateFolder(selected.id, { sandboxPath: e.target.value })}
                    placeholder="C:\Users\...\proyecto"
                    className="flex-1 bg-base border border-border rounded-lg px-3 py-2 text-sm text-primary outline-none focus:border-accent/50"
                  />
                  <button
                    className="btn-ghost px-2.5 py-2"
                    title="Elegir carpeta sandbox"
                    onClick={async () => {
                      const dir = await pickDirectory();
                      if (dir) updateFolder(selected.id, { sandboxPath: dir });
                    }}
                  >
                    <FolderOpen size={14} />
                  </button>
                  <button
                    className="btn-ghost px-2.5 py-2 text-xs"
                    title="Limpiar carpeta sandbox"
                    onClick={() => updateFolder(selected.id, { sandboxPath: undefined })}
                  >
                    Limpiar
                  </button>
                </div>
                <p className="text-[11px] text-muted">
                  Si está definida, el agente ejecuta comandos y operaciones de archivos dentro de este sandbox.
                  Si no está definida, pedirá confirmación explícita antes de ejecutar acciones mutantes.
                </p>
              </div>
              <div className="space-y-2">
                <label className="text-xs text-secondary">Comportamiento base (opcional)</label>
                <select
                  value={selected.behaviorId ?? ""}
                  onChange={(e) => updateFolder(selected.id, { behaviorId: e.target.value || undefined })}
                  className="input-field w-full px-3 py-2 text-sm"
                >
                  <option value="">Sin comportamiento base</option>
                  {behaviors.map((b) => (
                    <option key={b.id} value={b.id}>
                      {(b.icon ?? "🤖")} {b.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-xs text-secondary">Prompt personalizado (opcional)</label>
                <textarea
                  value={selected.customPrompt ?? ""}
                  onChange={(e) => updateFolder(selected.id, { customPrompt: e.target.value })}
                  rows={6}
                  placeholder="Instrucciones personalizadas para TODAS las conversaciones de esta carpeta…"
                  className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-primary outline-none focus:border-accent/50"
                />
              </div>
            </section>

            <section className="bg-surface border border-border rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs uppercase tracking-wider text-muted font-semibold">Documentos exclusivos</h3>
                <button
                  className="btn-ghost px-3 py-1.5 text-xs flex items-center gap-1.5"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                >
                  <Upload size={12} />
                  {uploading ? "Subiendo…" : "Subir"}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".pdf,.txt,.md,.csv,.log"
                  onChange={onUpload}
                />
              </div>
              {files.length === 0 ? (
                <p className="text-xs text-muted">No hay documentos cargados para esta carpeta.</p>
              ) : (
                <div className="space-y-2">
                  {files.map((f) => (
                    <div key={f.name} className="text-xs px-3 py-2 bg-raised border border-border rounded-lg flex justify-between">
                      <span className="truncate">{f.name}</span>
                      <span className="text-muted">{formatBytes(f.size)}</span>
                    </div>
                  ))}
                </div>
              )}
              <p className="text-[11px] text-muted">
                Estos documentos se usan solo en conversaciones que pertenezcan a esta carpeta.
              </p>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
