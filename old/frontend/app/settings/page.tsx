'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { X, CheckCircle, AlertCircle } from 'lucide-react';

const DEFAULTS = {
  N8N_WEBHOOK_URL: 'http://127.0.0.1:5678/webhook/chat',
  N8N_ENABLED: 'true',
  VECTOR_DB_PROVIDER: 'chroma',
  LLM_PROVIDER: 'ollama',
  AGENT_LANGUAGE: 'en',
  OLLAMA_BASE_URL: 'http://localhost:11434',
  OLLAMA_MODEL: 'qwen2.5-coder:14b',
  SUPABASE_URL: '',
  SUPABASE_KEY: '',
  OPENAI_API_KEY: '',
  OPENAI_MODEL: 'gpt-4o-mini',
  MCP_PORT: '8000',
  LLAMACPP_EXECUTABLE: '',
  LLAMACPP_MODEL_PATH: '',
  LLAMACPP_HOST: '127.0.0.1',
  LLAMACPP_PORT: '8080',
  LLAMACPP_CONTEXT_SIZE: '32768',
  LLAMACPP_N_GPU_LAYERS: '999',
  LLAMACPP_FLASH_ATTN: 'true',
  LLAMACPP_MODEL_ALIAS: 'local-model',
  LLAMACPP_CACHE_TYPE_K: '',
  LLAMACPP_CACHE_TYPE_V: '',
  LLAMACPP_EXTRA_ARGS: '',
};

type Config = typeof DEFAULTS;

const T: Record<string, Record<string, string>> = {
  en: {
    title: 'Settings', back: 'Esc', save: 'Save Changes', saving: 'Saving...',
    agentLang: 'Agent Language', vectorDb: 'Vector Database Provider', llmProvider: 'LLM Provider',
    ollamaUrl: 'Ollama Base URL', ollamaModel: 'Ollama Model',
    n8nUrl: 'n8n Webhook URL', dockerHint: 'Use http://host.docker.internal... if running in Docker.',
    n8nEnabled: 'Use n8n (orchestration)', n8nDisabledHint: 'Direct mode — frontend calls LLM directly with optional RAG context.',
    startMcp: 'Start MCP', stopMcp: 'Stop MCP',
    startLlama: 'Start llama.cpp', stopLlama: 'Stop llama.cpp',
    supabase: 'Supabase Configuration', openai: 'OpenAI Configuration',
    llamacpp: 'llama.cpp Configuration',
    mcpPort: 'MCP Server Port', portHint: 'Restart server after changing port.',
    llamaExe: 'llama-server executable path',
    llamaModel: 'Model path (.gguf)',
    llamaHost: 'Host', llamaPort: 'Port',
    llamaCtx: 'Context size', llamaNgl: 'GPU layers (-ngl)',
    llamaAlias: 'Model alias', llamaFlash: 'Flash attention',
    llamaCacheK: 'KV cache type K (e.g. q8_0)', llamaCacheV: 'KV cache type V (e.g. q8_0)',
    llamaExtra: 'Extra args (space-separated)',
  },
  es: {
    title: 'Configuración', back: 'Esc', save: 'Guardar Cambios', saving: 'Guardando...',
    agentLang: 'Idioma del Agente', vectorDb: 'Proveedor de Vector DB', llmProvider: 'Proveedor LLM',
    ollamaUrl: 'URL Base de Ollama', ollamaModel: 'Modelo Ollama',
    n8nUrl: 'URL del Webhook de n8n', dockerHint: 'Usa http://host.docker.internal... si usas Docker.',
    n8nEnabled: 'Usar n8n (orquestación)', n8nDisabledHint: 'Modo directo — el frontend llama al LLM directamente con contexto RAG opcional.',
    startMcp: 'Iniciar MCP', stopMcp: 'Detener MCP',
    startLlama: 'Iniciar llama.cpp', stopLlama: 'Detener llama.cpp',
    supabase: 'Configuración de Supabase', openai: 'Configuración de OpenAI',
    llamacpp: 'Configuración de llama.cpp',
    mcpPort: 'Puerto del Servidor MCP', portHint: 'Reinicia el servidor tras cambiar el puerto.',
    llamaExe: 'Ruta al ejecutable llama-server',
    llamaModel: 'Ruta al modelo (.gguf)',
    llamaHost: 'Host', llamaPort: 'Puerto',
    llamaCtx: 'Tamaño de contexto', llamaNgl: 'Capas GPU (-ngl)',
    llamaAlias: 'Alias del modelo', llamaFlash: 'Flash attention',
    llamaCacheK: 'Tipo caché KV K (ej. q8_0)', llamaCacheV: 'Tipo caché KV V (ej. q8_0)',
    llamaExtra: 'Args extra (separados por espacio)',
  },
  zh: {
    title: '设置', back: '退出', save: '保存更改', saving: '保存中...',
    agentLang: '代理语言', vectorDb: '向量数据库提供商', llmProvider: 'LLM 提供商',
    ollamaUrl: 'Ollama 基础 URL', ollamaModel: 'Ollama 模型',
    n8nUrl: 'n8n Webhook URL', dockerHint: '如果运行在 Docker 中，请使用 http://host.docker.internal...',
    n8nEnabled: '使用 n8n（编排）', n8nDisabledHint: '直接模式 — 前端直接调用 LLM，可选 RAG 上下文。',
    startMcp: '启动 MCP', stopMcp: '停止 MCP',
    startLlama: '启动 llama.cpp', stopLlama: '停止 llama.cpp',
    supabase: 'Supabase 配置', openai: 'OpenAI 配置',
    llamacpp: 'llama.cpp 配置',
    mcpPort: 'MCP 服务器端口', portHint: '更改端口后请重启服务器。',
    llamaExe: 'llama-server 可执行文件路径',
    llamaModel: '模型路径 (.gguf)',
    llamaHost: '主机', llamaPort: '端口',
    llamaCtx: '上下文大小', llamaNgl: 'GPU 层数 (-ngl)',
    llamaAlias: '模型别名', llamaFlash: 'Flash attention',
    llamaCacheK: 'KV 缓存类型 K（如 q8_0）', llamaCacheV: 'KV 缓存类型 V（如 q8_0）',
    llamaExtra: '额外参数（空格分隔）',
  },
};

const inputClass =
  'w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-gray-500 outline-none transition-colors placeholder-gray-600';
const selectClass =
  'w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-gray-500 outline-none appearance-none transition-colors';

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-400 mb-2">{label}</label>
      {children}
      {hint && <p className="text-xs text-gray-500 mt-2">{hint}</p>}
    </div>
  );
}

export default function Settings() {
  const [config, setConfig] = useState<Config>({ ...DEFAULTS });
  const [saving, setSaving] = useState(false);
  const [modal, setModal] = useState({ open: false, type: 'info', message: '' });

  useEffect(() => {
    fetch('/api/settings')
      .then((r) => r.json())
      .then((data) => setConfig((prev) => ({ ...prev, ...data })));
  }, []);

  const set = (key: keyof Config, val: string) => setConfig((c) => ({ ...c, [key]: val }));

  const handleSave = async () => {
    setSaving(true);
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    setSaving(false);
  };

  const control = async (action: string, label: string) => {
    setModal({ open: true, type: 'loading', message: `${label}...` });
    try {
      const res = await fetch('/api/system/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      const detail = data.pid ? ` PID: ${data.pid}` : data.url ? ` ${data.url}` : '';
      setModal({ open: true, type: 'success', message: `${data.status}${detail}` });
    } catch (e: unknown) {
      setModal({ open: true, type: 'error', message: String(e) });
    }
  };

  const t = T[config.AGENT_LANGUAGE] || T.en;
  const n8nOn = config.N8N_ENABLED !== 'false';

  return (
    <div className="min-h-screen bg-[#09090b] text-gray-100 p-8 font-sans flex items-center justify-center">
      <div className="w-full max-w-2xl animate-fadeIn">

        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold text-white tracking-tight">{t.title}</h1>
          <Link href="/" className="px-4 py-2 rounded-lg bg-[#27272a] hover:bg-[#3f3f46] text-sm text-gray-200 transition-colors">
            {t.back}
          </Link>
        </div>

        <div className="bg-[#18181b] rounded-2xl p-8 border border-[#27272a] shadow-xl space-y-8">

          {/* ── General ───────────────────────────────────────────────── */}
          <div className="space-y-6">
            <Field label={t.agentLang}>
              <div className="relative">
                <select value={config.AGENT_LANGUAGE} onChange={(e) => set('AGENT_LANGUAGE', e.target.value)} className={selectClass}>
                  <option value="en">English</option>
                  <option value="es">Español</option>
                  <option value="zh">中文</option>
                </select>
                <div className="absolute right-3 top-3.5 pointer-events-none text-gray-500">▼</div>
              </div>
            </Field>

            <Field label={t.vectorDb}>
              <div className="relative">
                <select value={config.VECTOR_DB_PROVIDER} onChange={(e) => set('VECTOR_DB_PROVIDER', e.target.value)} className={selectClass}>
                  <option value="chroma">Local: ChromaDB</option>
                  <option value="supabase">Cloud: Supabase</option>
                </select>
                <div className="absolute right-3 top-3.5 pointer-events-none text-gray-500">▼</div>
              </div>
            </Field>

            <Field label={t.llmProvider}>
              <div className="relative">
                <select value={config.LLM_PROVIDER} onChange={(e) => set('LLM_PROVIDER', e.target.value)} className={selectClass}>
                  <option value="ollama">Local: Ollama</option>
                  <option value="llamacpp">Local: llama.cpp</option>
                  <option value="openai">Cloud: OpenAI</option>
                </select>
                <div className="absolute right-3 top-3.5 pointer-events-none text-gray-500">▼</div>
              </div>
            </Field>
          </div>

          {/* ── Ollama ─────────────────────────────────────────────────── */}
          {config.LLM_PROVIDER === 'ollama' && (
            <div className="space-y-4 animate-fadeIn">
              <Field label={t.ollamaUrl}>
                <input type="text" value={config.OLLAMA_BASE_URL} onChange={(e) => set('OLLAMA_BASE_URL', e.target.value)}
                  placeholder="http://localhost:11434" className={inputClass} />
              </Field>
              <Field label={t.ollamaModel}>
                <input type="text" value={config.OLLAMA_MODEL} onChange={(e) => set('OLLAMA_MODEL', e.target.value)}
                  placeholder="qwen2.5-coder:14b" className={inputClass} />
              </Field>
            </div>
          )}

          {/* ── OpenAI ─────────────────────────────────────────────────── */}
          {config.LLM_PROVIDER === 'openai' && (
            <div className="space-y-4 animate-fadeIn bg-purple-900/10 p-4 rounded-lg border border-purple-900/20">
              <h3 className="text-sm font-semibold text-purple-400">{t.openai}</h3>
              <Field label="API Key">
                <input type="password" placeholder="sk-..." value={config.OPENAI_API_KEY}
                  onChange={(e) => set('OPENAI_API_KEY', e.target.value)} className={inputClass} />
              </Field>
              <Field label="Model">
                <input type="text" placeholder="gpt-4o-mini" value={config.OPENAI_MODEL}
                  onChange={(e) => set('OPENAI_MODEL', e.target.value)} className={inputClass} />
              </Field>
            </div>
          )}

          {/* ── llama.cpp ──────────────────────────────────────────────── */}
          {config.LLM_PROVIDER === 'llamacpp' && (
            <div className="space-y-4 animate-fadeIn bg-orange-900/10 p-4 rounded-lg border border-orange-900/20">
              <h3 className="text-sm font-semibold text-orange-400">{t.llamacpp}</h3>

              <Field label={t.llamaExe}>
                <input type="text" value={config.LLAMACPP_EXECUTABLE}
                  onChange={(e) => set('LLAMACPP_EXECUTABLE', e.target.value)}
                  placeholder="C:\path\to\llama-server.exe" className={inputClass} />
              </Field>
              <Field label={t.llamaModel}>
                <input type="text" value={config.LLAMACPP_MODEL_PATH}
                  onChange={(e) => set('LLAMACPP_MODEL_PATH', e.target.value)}
                  placeholder="C:\Users\...\model.gguf" className={inputClass} />
              </Field>
              <Field label={t.llamaAlias}>
                <input type="text" value={config.LLAMACPP_MODEL_ALIAS}
                  onChange={(e) => set('LLAMACPP_MODEL_ALIAS', e.target.value)}
                  placeholder="local-model" className={inputClass} />
              </Field>

              <div className="grid grid-cols-2 gap-4">
                <Field label={t.llamaHost}>
                  <input type="text" value={config.LLAMACPP_HOST}
                    onChange={(e) => set('LLAMACPP_HOST', e.target.value)}
                    placeholder="127.0.0.1" className={inputClass} />
                </Field>
                <Field label={t.llamaPort}>
                  <input type="number" value={config.LLAMACPP_PORT}
                    onChange={(e) => set('LLAMACPP_PORT', e.target.value)}
                    placeholder="8080" className={inputClass} />
                </Field>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Field label={t.llamaCtx}>
                  <input type="number" value={config.LLAMACPP_CONTEXT_SIZE}
                    onChange={(e) => set('LLAMACPP_CONTEXT_SIZE', e.target.value)}
                    placeholder="32768" className={inputClass} />
                </Field>
                <Field label={t.llamaNgl}>
                  <input type="number" value={config.LLAMACPP_N_GPU_LAYERS}
                    onChange={(e) => set('LLAMACPP_N_GPU_LAYERS', e.target.value)}
                    placeholder="999" className={inputClass} />
                </Field>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Field label={t.llamaCacheK}>
                  <input type="text" value={config.LLAMACPP_CACHE_TYPE_K}
                    onChange={(e) => set('LLAMACPP_CACHE_TYPE_K', e.target.value)}
                    placeholder="q8_0" className={inputClass} />
                </Field>
                <Field label={t.llamaCacheV}>
                  <input type="text" value={config.LLAMACPP_CACHE_TYPE_V}
                    onChange={(e) => set('LLAMACPP_CACHE_TYPE_V', e.target.value)}
                    placeholder="q8_0" className={inputClass} />
                </Field>
              </div>

              <Field label={t.llamaFlash}>
                <label className="flex items-center gap-3 cursor-pointer">
                  <div
                    onClick={() => set('LLAMACPP_FLASH_ATTN', config.LLAMACPP_FLASH_ATTN === 'true' ? 'false' : 'true')}
                    className={`w-10 h-6 rounded-full transition-colors flex items-center px-1 cursor-pointer
                      ${config.LLAMACPP_FLASH_ATTN === 'true' ? 'bg-orange-500' : 'bg-gray-600'}`}
                  >
                    <div className={`w-4 h-4 bg-white rounded-full transition-transform
                      ${config.LLAMACPP_FLASH_ATTN === 'true' ? 'translate-x-4' : ''}`} />
                  </div>
                  <span className="text-sm text-gray-400">
                    {config.LLAMACPP_FLASH_ATTN === 'true' ? 'enabled' : 'disabled'}
                  </span>
                </label>
              </Field>

              <Field label={t.llamaExtra}>
                <input type="text" value={config.LLAMACPP_EXTRA_ARGS}
                  onChange={(e) => set('LLAMACPP_EXTRA_ARGS', e.target.value)}
                  placeholder="--threads 8" className={inputClass} />
              </Field>

              {/* llama.cpp server controls */}
              <div className="flex gap-2 pt-2">
                <button onClick={() => control('start_llamacpp', t.startLlama)}
                  className="px-4 py-2 bg-orange-900/30 text-orange-400 border border-orange-900/50 rounded-lg text-xs hover:bg-orange-900/50 transition-colors">
                  {t.startLlama}
                </button>
                <button onClick={() => control('stop_llamacpp', t.stopLlama)}
                  className="px-4 py-2 bg-red-900/30 text-red-400 border border-red-900/50 rounded-lg text-xs hover:bg-red-900/50 transition-colors">
                  {t.stopLlama}
                </button>
              </div>
            </div>
          )}

          <hr className="border-[#27272a]" />

          {/* ── MCP Port ───────────────────────────────────────────────── */}
          <Field label={t.mcpPort} hint={t.portHint}>
            <input type="number" value={config.MCP_PORT}
              onChange={(e) => set('MCP_PORT', e.target.value)} className={inputClass} />
          </Field>

          <hr className="border-[#27272a]" />

          {/* ── n8n toggle + URL ───────────────────────────────────────── */}
          <div className="space-y-4">
            <Field label={t.n8nEnabled}>
              <label className="flex items-center gap-3 cursor-pointer">
                <div
                  onClick={() => set('N8N_ENABLED', n8nOn ? 'false' : 'true')}
                  className={`w-10 h-6 rounded-full transition-colors flex items-center px-1 cursor-pointer
                    ${n8nOn ? 'bg-blue-500' : 'bg-gray-600'}`}
                >
                  <div className={`w-4 h-4 bg-white rounded-full transition-transform ${n8nOn ? 'translate-x-4' : ''}`} />
                </div>
                <span className="text-sm text-gray-400">{n8nOn ? 'enabled' : 'disabled'}</span>
              </label>
              {!n8nOn && (
                <p className="text-xs text-blue-400 mt-2">{t.n8nDisabledHint}</p>
              )}
            </Field>

            {n8nOn && (
              <Field label={t.n8nUrl} hint={t.dockerHint}>
                <input type="text" value={config.N8N_WEBHOOK_URL}
                  onChange={(e) => set('N8N_WEBHOOK_URL', e.target.value)}
                  placeholder={DEFAULTS.N8N_WEBHOOK_URL} className={inputClass} />
              </Field>
            )}
          </div>

          {/* ── Supabase ───────────────────────────────────────────────── */}
          {config.VECTOR_DB_PROVIDER === 'supabase' && (
            <div className="space-y-4 animate-fadeIn bg-green-900/10 p-4 rounded-lg border border-green-900/20">
              <h3 className="text-sm font-semibold text-green-400">{t.supabase}</h3>
              <input type="text" placeholder="Supabase URL" value={config.SUPABASE_URL}
                onChange={(e) => set('SUPABASE_URL', e.target.value)} className={inputClass} />
              <input type="password" placeholder="Supabase Key" value={config.SUPABASE_KEY}
                onChange={(e) => set('SUPABASE_KEY', e.target.value)} className={inputClass} />
            </div>
          )}

          {/* ── Footer: MCP controls + Save ────────────────────────────── */}
          <div className="pt-2 flex justify-between items-center">
            <div className="flex gap-2">
              <button onClick={() => control('start', t.startMcp)}
                className="px-4 py-2 bg-green-900/30 text-green-400 border border-green-900/50 rounded-lg text-xs hover:bg-green-900/50 transition-colors">
                {t.startMcp}
              </button>
              <button onClick={() => control('stop', t.stopMcp)}
                className="px-4 py-2 bg-red-900/30 text-red-400 border border-red-900/50 rounded-lg text-xs hover:bg-red-900/50 transition-colors">
                {t.stopMcp}
              </button>
            </div>

            <button onClick={handleSave} disabled={saving}
              className="bg-white text-black hover:bg-gray-200 px-6 py-2.5 rounded-lg font-medium text-sm transition-all active:scale-95 disabled:opacity-50">
              {saving ? t.saving : t.save}
            </button>
          </div>

        </div>
      </div>

      {/* ── Modal ─────────────────────────────────────────────────────────── */}
      {modal.open && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 animate-fadeIn p-4">
          <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-6 max-w-sm w-full shadow-2xl relative">
            <button onClick={() => setModal({ ...modal, open: false })}
              className="absolute top-4 right-4 text-gray-500 hover:text-white">
              <X size={20} />
            </button>
            <div className="flex flex-col items-center text-center gap-4">
              {modal.type === 'loading' && (
                <div className="w-8 h-8 rounded-full border-2 border-white border-t-transparent animate-spin" />
              )}
              {modal.type === 'success' && (
                <div className="w-12 h-12 rounded-full bg-green-900/30 text-green-400 flex items-center justify-center">
                  <CheckCircle size={24} />
                </div>
              )}
              {modal.type === 'error' && (
                <div className="w-12 h-12 rounded-full bg-red-900/30 text-red-400 flex items-center justify-center">
                  <AlertCircle size={24} />
                </div>
              )}
              <h3 className="text-lg font-semibold text-white">
                {modal.type === 'loading' ? 'Processing...' : modal.type === 'success' ? 'Success' : 'Error'}
              </h3>
              <div className="text-sm text-gray-400 break-words w-full font-mono bg-black/50 p-2 rounded">
                {modal.message}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
