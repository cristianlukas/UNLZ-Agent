'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { X, CheckCircle, AlertCircle } from 'lucide-react';

const dictionary: any = {
  en: { 
    title: 'Settings', back: 'Esc', save: 'Save Changes', saving: 'Saving...', saved: 'Settings Saved!',
    agentLang: 'Agent Language', vectorDb: 'Vector Database Provider', llmProvider: 'LLM Inference Provider',
    ollamaUrl: 'Ollama Base URL', n8nUrl: 'n8n Webhook URL', dockerHint: 'Use http://host.docker.internal... if running in Docker.',
    startServer: 'Start Server', stopServer: 'Stop Server', supabase: 'Supabase Configuration', openai: 'OpenAI Configuration',
    mcpPort: 'MCP Server Port', portHint: 'Restart server after changing port.'
  },
  es: { 
    title: 'Configuración', back: 'Esc', save: 'Guardar Cambios', saving: 'Guardando...', saved: '¡Configuración Guardada!',
    agentLang: 'Idioma del Agente', vectorDb: 'Proveedor de Vector DB', llmProvider: 'Proveedor de Inteligencia Artificial',
    ollamaUrl: 'URL Base de Ollama', n8nUrl: 'URL del Webhook de n8n', dockerHint: 'Usa http://host.docker.internal... si usas Docker.',
    startServer: 'Iniciar servidor MCP', stopServer: 'Detener servidor MCP', supabase: 'Configuración de Supabase', openai: 'Configuración de OpenAI',
    mcpPort: 'Puerto del Servidor MCP', portHint: 'Reinicia el servidor tras cambiar el puerto.'
  },
  zh: { 
    title: '设置', back: '退出', save: '保存更改', saving: '保存中...', saved: '设置已保存！',
    agentLang: '代理语言', vectorDb: '向量数据库提供商', llmProvider: 'LLM 推理提供商',
    ollamaUrl: 'Ollama 基础 URL', n8nUrl: 'n8n Webhook URL', dockerHint: '如果运行在 Docker 中，请使用 http://host.docker.internal...',
    startServer: '启动服务器', stopServer: '停止服务器', supabase: 'Supabase 配置', openai: 'OpenAI 配置',
    mcpPort: 'MCP 服务器端口', portHint: '更改端口后请重启服务器。'
  }
};

export default function Settings() {
  const [config, setConfig] = useState({
    N8N_WEBHOOK_URL: '',
    VECTOR_DB_PROVIDER: 'chroma',
    LLM_PROVIDER: 'ollama',
    AGENT_LANGUAGE: 'en',
    OLLAMA_BASE_URL: '',
    SUPABASE_URL: '',
    SUPABASE_KEY: '',
    OPENAI_API_KEY: '',
    MCP_PORT: '8000'
  });
  const [saving, setSaving] = useState(false);
  const [modal, setModal] = useState({ open: false, type: 'info', message: '' });

  useEffect(() => {
    fetch('/api/settings')
      .then(res => res.json())
      .then(data => setConfig(prev => ({ ...prev, ...data })));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
    setSaving(false);
    // instant feedback, no alert required for language, but maybe for server
    // alert(t.saved); 
  };
  
  const t = dictionary[config.AGENT_LANGUAGE as 'en' | 'es' | 'zh'] || dictionary.en;

  return (
    <div className="min-h-screen bg-[#09090b] text-gray-100 p-8 font-sans flex items-center justify-center">
      <div className="w-full max-w-2xl animate-fadeIn">
        
        <div className="flex items-center justify-between mb-8">
            <h1 className="text-2xl font-bold text-white tracking-tight">
              {t.title}
            </h1>
            <Link href="/" className="px-4 py-2 rounded-lg bg-[#27272a] hover:bg-[#3f3f46] text-sm text-gray-200 transition-colors">
                {t.back}
            </Link>
        </div>

        <div className="bg-[#18181b] rounded-2xl p-8 border border-[#27272a] shadow-xl space-y-8">
          
          {/* Architecture Toggles */}
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">{t.agentLang}</label>
               <div className="relative">
                <select 
                  value={config.AGENT_LANGUAGE}
                  onChange={(e) => setConfig({ ...config, AGENT_LANGUAGE: e.target.value })}
                  className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-gray-500 outline-none appearance-none transition-colors"
                >
                  <option value="en">English (English)</option>
                  <option value="es">Español (Spanish)</option>
                  <option value="zh">中文 (Chinese)</option>
                </select>
                <div className="absolute right-3 top-3.5 pointer-events-none text-gray-500">▼</div>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">{t.vectorDb}</label>
              <div className="relative">
                <select 
                  value={config.VECTOR_DB_PROVIDER}
                  onChange={(e) => setConfig({ ...config, VECTOR_DB_PROVIDER: e.target.value })}
                  className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-gray-500 outline-none appearance-none transition-colors"
                >
                  <option value="chroma">Local: ChromaDB</option>
                  <option value="supabase">Cloud: Supabase</option>
                </select>
                <div className="absolute right-3 top-3.5 pointer-events-none text-gray-500">▼</div>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">{t.llmProvider}</label>
               <div className="relative">
                <select 
                  value={config.LLM_PROVIDER}
                  onChange={(e) => setConfig({ ...config, LLM_PROVIDER: e.target.value })}
                  className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-gray-500 outline-none appearance-none transition-colors"
                >
                  <option value="ollama">Local: Ollama</option>
                  <option value="openai">Cloud: OpenAI</option>
                </select>
                <div className="absolute right-3 top-3.5 pointer-events-none text-gray-500">▼</div>
              </div>
            </div>
          </div>
          
          {config.LLM_PROVIDER === 'ollama' && (
             <div className="mt-4 animate-fadeIn">
                 <label className="block text-sm font-medium text-gray-400 mb-2">{t.ollamaUrl}</label>
                 <input 
                  type="text" 
                  value={config.OLLAMA_BASE_URL}
                  onChange={(e) => setConfig({ ...config, OLLAMA_BASE_URL: e.target.value })}
                  placeholder="http://localhost:11434"
                  className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-gray-500 outline-none transition-colors placeholder-gray-600"
                />
             </div>
          )}

          <hr className="border-[#27272a]" />

          
          {/* MCP Configuration */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">{t.mcpPort}</label>
            <input 
              type="number" 
              value={config.MCP_PORT}
              onChange={(e) => setConfig({ ...config, MCP_PORT: e.target.value })}
              className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-gray-500 outline-none transition-colors placeholder-gray-600"
            />
             <p className="text-xs text-gray-500 mt-2">{t.portHint}</p>
          </div>

          <hr className="border-[#27272a]" />

          {/* Connection Details */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">{t.n8nUrl}</label>
            <input 
              type="text" 
              value={config.N8N_WEBHOOK_URL}
              onChange={(e) => setConfig({ ...config, N8N_WEBHOOK_URL: e.target.value })}
              placeholder="http://localhost:5678/webhook/chat"
              className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-gray-500 outline-none transition-colors placeholder-gray-600"
            />
            <p className="text-xs text-gray-500 mt-2">{t.dockerHint}</p>
          </div>

          {config.VECTOR_DB_PROVIDER === 'supabase' && (
             <div className="space-y-4 animate-fadeIn bg-green-900/10 p-4 rounded-lg border border-green-900/20">
                <h3 className="text-sm font-semibold text-green-400">{t.supabase}</h3>
                <input 
                  type="text" 
                  placeholder="Supabase URL"
                  value={config.SUPABASE_URL}
                  onChange={(e) => setConfig({ ...config, SUPABASE_URL: e.target.value })}
                  className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-green-800 outline-none"
                />
                <input 
                  type="password" 
                  placeholder="Supabase Key"
                  value={config.SUPABASE_KEY}
                  onChange={(e) => setConfig({ ...config, SUPABASE_KEY: e.target.value })}
                  className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-green-800 outline-none"
                />
             </div>
          )}

          {config.LLM_PROVIDER === 'openai' && (
             <div className="space-y-4 animate-fadeIn bg-purple-900/10 p-4 rounded-lg border border-purple-900/20">
                <h3 className="text-sm font-semibold text-purple-400">{t.openai}</h3>
                <input 
                  type="password" 
                  placeholder="OpenAI API Key"
                  value={config.OPENAI_API_KEY}
                  onChange={(e) => setConfig({ ...config, OPENAI_API_KEY: e.target.value })}
                  className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-purple-800 outline-none"
                />
             </div>
          )}

          <div className="pt-2 flex justify-between items-center">
            {/* Server Control */}
            <div className="flex gap-2">
                 <button 
                  onClick={async () => {
                    setModal({ open: true, type: 'loading', message: 'Starting Server...' });
                    try {
                        const res = await fetch('/api/system/control', { method: 'POST', body: JSON.stringify({ action: 'start' }) });
                        const data = await res.json();
                        setModal({ open: true, type: 'success', message: `Server Started. PID: ${data.pid || 'Unknown'}` });
                    } catch (e: any) { 
                        setModal({ open: true, type: 'error', message: 'Error: ' + e.toString() });
                    }
                  }}
                  className="px-4 py-2 bg-green-900/30 text-green-400 border border-green-900/50 rounded-lg text-xs hover:bg-green-900/50 transition-colors"
                >
                  {t.startServer}
                </button>
                <button 
                  onClick={async () => {
                     setModal({ open: true, type: 'loading', message: 'Stopping Server...' });
                    try {
                        const res = await fetch('/api/system/control', { method: 'POST', body: JSON.stringify({ action: 'stop' }) });
                        const data = await res.json();
                         setModal({ open: true, type: 'success', message: 'Server Stopped.' });
                    } catch (e: any) { 
                        setModal({ open: true, type: 'error', message: 'Error: ' + e.toString() });
                    }
                  }}
                  className="px-4 py-2 bg-red-900/30 text-red-400 border border-red-900/50 rounded-lg text-xs hover:bg-red-900/50 transition-colors"
                >
                  {t.stopServer}
                </button>
            </div>

            <button 
              onClick={handleSave}
              disabled={saving}
              className="bg-white text-black hover:bg-gray-200 px-6 py-2.5 rounded-lg font-medium text-sm transition-all active:scale-95 disabled:opacity-50"
            >
              {saving ? t.saving : t.save}
            </button>
          </div>

        </div>
      </div>

       {/* Modal */}
      {modal.open && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 animate-fadeIn p-4">
            <div className="bg-[#18181b] border border-[#27272a] rounded-xl p-6 max-w-sm w-full shadow-2xl relative">
                <button onClick={() => setModal({ ...modal, open: false })} className="absolute top-4 right-4 text-gray-500 hover:text-white">
                    <X size={20} />
                </button>
                
                <div className="flex flex-col items-center text-center gap-4">
                    {modal.type === 'loading' && <div className="w-8 h-8 rounded-full border-2 border-white border-t-transparent animate-spin"></div>}
                    {modal.type === 'success' && <div className="w-12 h-12 rounded-full bg-green-900/30 text-green-400 flex items-center justify-center"><CheckCircle size={24}/></div>}
                    {modal.type === 'error' && <div className="w-12 h-12 rounded-full bg-red-900/30 text-red-400 flex items-center justify-center"><AlertCircle size={24}/></div>}
                    
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
