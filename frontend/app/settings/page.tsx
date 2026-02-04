'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

export default function Settings() {
  const [config, setConfig] = useState({
    N8N_WEBHOOK_URL: '',
    VECTOR_DB_PROVIDER: 'chroma',
    LLM_PROVIDER: 'ollama',
    AGENT_LANGUAGE: 'en',
    OLLAMA_BASE_URL: '',
    SUPABASE_URL: '',
    SUPABASE_KEY: '',
    OPENAI_API_KEY: ''
  });
  const [saving, setSaving] = useState(false);

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
    alert('Settings Saved! Restart backend services manually.');
  };

  return (
    <div className="min-h-screen bg-[#09090b] text-gray-100 p-8 font-sans flex items-center justify-center">
      <div className="w-full max-w-2xl animate-fadeIn">
        
        <div className="flex items-center justify-between mb-8">
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Settings
            </h1>
            <Link href="/" className="px-4 py-2 rounded-lg bg-[#27272a] hover:bg-[#3f3f46] text-sm text-gray-200 transition-colors">
                Esc
            </Link>
        </div>

        <div className="bg-[#18181b] rounded-2xl p-8 border border-[#27272a] shadow-xl space-y-8">
          
          {/* Architecture Toggles */}
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Agent Language</label>
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
              <label className="block text-sm font-medium text-gray-400 mb-2">Vector Database Provider</label>
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
              <label className="block text-sm font-medium text-gray-400 mb-2">LLM Inference Provider</label>
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
                 <label className="block text-sm font-medium text-gray-400 mb-2">Ollama Base URL</label>
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

          {/* Connection Details */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">n8n Webhook URL</label>
            <input 
              type="text" 
              value={config.N8N_WEBHOOK_URL}
              onChange={(e) => setConfig({ ...config, N8N_WEBHOOK_URL: e.target.value })}
              placeholder="http://localhost:5678/webhook/chat"
              className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-gray-500 outline-none transition-colors placeholder-gray-600"
            />
            <p className="text-xs text-gray-500 mt-2">Use <code>http://host.docker.internal...</code> if running in Docker.</p>
          </div>

          {config.VECTOR_DB_PROVIDER === 'supabase' && (
             <div className="space-y-4 animate-fadeIn bg-green-900/10 p-4 rounded-lg border border-green-900/20">
                <h3 className="text-sm font-semibold text-green-400">Supabase Configuration</h3>
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
                <h3 className="text-sm font-semibold text-purple-400">OpenAI Configuration</h3>
                <input 
                  type="password" 
                  placeholder="OpenAI API Key"
                  value={config.OPENAI_API_KEY}
                  onChange={(e) => setConfig({ ...config, OPENAI_API_KEY: e.target.value })}
                  className="w-full bg-[#09090b] border border-[#27272a] rounded-lg p-3 text-sm focus:border-purple-800 outline-none"
                />
             </div>
          )}

          <div className="pt-2 flex justify-end">
            <button 
              onClick={handleSave}
              disabled={saving}
              className="bg-white text-black hover:bg-gray-200 px-6 py-2.5 rounded-lg font-medium text-sm transition-all active:scale-95 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
