import { useEffect, useRef, useState } from "react";
import { Upload, FileText, Trash2, RefreshCw, Database } from "lucide-react";
import { listFiles, uploadFile, triggerIngest } from "../lib/api";
import type { KbFile } from "../lib/types";

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 ** 2).toFixed(1)} MB`;
}

function formatDate(ts: number) {
  return new Date(ts * 1000).toLocaleDateString("es-AR", {
    day: "2-digit", month: "short", year: "numeric",
  });
}

export default function KnowledgeView() {
  const [files, setFiles] = useState<KbFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try { setFiles(await listFiles()); } catch { setFiles([]); }
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadFile(file);
      showToast(`Uploaded: ${file.name}`);
      await load();
    } catch (err) {
      showToast(`Upload failed: ${err}`);
    }
    setUploading(false);
    e.target.value = "";
  }

  async function handleIngest() {
    setIngesting(true);
    try {
      const res = await triggerIngest();
      showToast(res.message || "Ingestion complete");
    } catch (err) {
      showToast(`Ingestion failed: ${err}`);
    }
    setIngesting(false);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-accent" />
          <span className="text-sm font-medium text-primary">Knowledge Base</span>
          <span className="text-xs text-muted bg-raised px-2 py-0.5 rounded-full">{files.length} files</span>
        </div>
        <div className="flex gap-2">
          <button
            className="btn-ghost text-xs px-3 py-1.5 flex items-center gap-1.5"
            onClick={load}
            disabled={loading}
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
          <button
            className="btn-ghost text-xs px-3 py-1.5 flex items-center gap-1.5"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            <Upload size={12} />
            {uploading ? "Uploading…" : "Upload"}
          </button>
          <button
            className="btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5"
            onClick={handleIngest}
            disabled={ingesting}
          >
            {ingesting ? (
              <div className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
            ) : (
              <Database size={12} />
            )}
            {ingesting ? "Indexing…" : "Index all"}
          </button>
          <input ref={fileInputRef} type="file" className="hidden" accept=".pdf,.txt,.md" onChange={handleUpload} />
        </div>
      </div>

      {/* File list */}
      <div className="flex-1 overflow-y-auto p-4">
        {files.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-muted">
            <FileText size={36} className="opacity-30" />
            <p className="text-sm">No files in knowledge base</p>
            <p className="text-xs opacity-60">Upload PDFs or text files to get started</p>
          </div>
        ) : (
          <div className="space-y-2">
            {files.map((f) => (
              <div
                key={f.name}
                className="flex items-center gap-3 px-4 py-3 bg-raised border border-border rounded-xl hover:border-accent/30 transition-colors group"
              >
                <FileText size={16} className="text-accent shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-primary truncate font-medium">{f.name}</p>
                  <p className="text-xs text-muted">{formatBytes(f.size)} · {formatDate(f.modified)}</p>
                </div>
                <button className="opacity-0 group-hover:opacity-100 transition-opacity text-muted hover:text-red-400">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-raised border border-border px-4 py-2 rounded-lg text-xs text-primary shadow-xl animate-fadeIn">
          {toast}
        </div>
      )}
    </div>
  );
}
