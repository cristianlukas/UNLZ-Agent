'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

export default function Settings() {
  const [config, setConfig] = useState({
    N8N_WEBHOOK_URL: '',
    VECTOR_DB_PROVIDER: 'chroma',
    LLM_PROVIDER: 'ollama',
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
    <div className="min-h-screen bg-gray-900 text-gray-100 p-8 font-sans">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-8">
            <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            System Settings
            </h1>
            <Link href="/" className="text-gray-400 hover:text-white transition-colors">
                ← Back to Chat
            </Link>
        </div>

        <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 space-y-6">
          
          {/* Architecture Toggles */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Vector DB Provider</label>
              <select 
                value={config.VECTOR_DB_PROVIDER}
                onChange={(e) => setConfig({ ...config, VECTOR_DB_PROVIDER: e.target.value })}
                className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 focus:border-blue-500 outline-none"
              >
                <option value="chroma">Local: ChromaDB</option>
                <option value="supabase">Cloud: Supabase</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">LLM Provider</label>
              <select 
                value={config.LLM_PROVIDER}
                onChange={(e) => setConfig({ ...config, LLM_PROVIDER: e.target.value })}
                className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 focus:border-blue-500 outline-none"
              >
                <option value="ollama">Local: Ollama</option>
                <option value="openai">Cloud: OpenAI</option>
              </select>
            </div>
          </div>

          <hr className="border-gray-700" />

          {/* Connection Details */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">n8n Webhook URL</label>
            <input 
              type="text" 
              value={config.N8N_WEBHOOK_URL}
              onChange={(e) => setConfig({ ...config, N8N_WEBHOOK_URL: e.target.value })}
              placeholder="http://localhost:5678/webhook/chat"
              className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 focus:border-blue-500 outline-none"
            />
            <p className="text-xs text-gray-500 mt-1">Use <code>http://host.docker.internal:5678...</code> if n8n is in Docker.</p>
          </div>

          {config.VECTOR_DB_PROVIDER === 'supabase' && (
             <div className="space-y-4 animate-fadeIn">
                <h3 className="text-lg font-semibold text-green-400">Supabase Config</h3>
                <input 
                  type="text" 
                  placeholder="Supabase URL"
                  value={config.SUPABASE_URL}
                  onChange={(e) => setConfig({ ...config, SUPABASE_URL: e.target.value })}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3"
                />
                <input 
                  type="password" 
                  placeholder="Supabase Key"
                  value={config.SUPABASE_KEY}
                  onChange={(e) => setConfig({ ...config, SUPABASE_KEY: e.target.value })}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3"
                />
             </div>
          )}

          {config.LLM_PROVIDER === 'openai' && (
             <div className="space-y-4 animate-fadeIn">
                <h3 className="text-lg font-semibold text-purple-400">OpenAI Config</h3>
                <input 
                  type="password" 
                  placeholder="OpenAI API Key"
                  value={config.OPENAI_API_KEY}
                  onChange={(e) => setConfig({ ...config, OPENAI_API_KEY: e.target.value })}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3"
                />
             </div>
          )}

          <div className="pt-4 flex justify-end">
            <button 
              onClick={handleSave}
              disabled={saving}
              className="bg-blue-600 hover:bg-blue-500 px-8 py-3 rounded-lg font-bold transition-transform active:scale-95 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save Configuration'}
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
