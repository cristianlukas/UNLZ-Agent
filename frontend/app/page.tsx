'use client';

import { useState, useEffect, useRef } from 'react';

type Message = {
  role: 'user' | 'assistant';
  content: string;
};

type Stats = {
  cpu: { usagePercent: number; model: string };
  memory: { usagePercent: number; usedGb: string; totalGb: string };
  gpu: { usagePercent: number; model: string };
};

export default function Home() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Fetch stats every 2 seconds
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch('/api/stats');
        if (res.ok) {
          const data = await res.json();
          setStats(data);
        }
      } catch (e) {
        console.error('Stats fetch error', e);
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 2000);
    return () => clearInterval(interval);
  }, []);

  const sendMessage = async () => {
    if (!input.trim()) return;

    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMsg.content }),
      });

      if (!res.ok) throw new Error('Network response was not ok');

      const data = await res.json();
      const aiMsg: Message = { role: 'assistant', content: data.response || 'No response from agent.' };
      setMessages(prev => [...prev, aiMsg]);
    } catch (error) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error connecting to Agent. Is n8n running?' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100 font-sans">
      {/* Sidebar: System Stats */}
      <div className="w-64 bg-gray-800 p-4 border-r border-gray-700 flex flex-col gap-6">
        <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
          UNLZ AI Studio
        </h1>
        
        {/* CPU Card */}
        <div className="bg-gray-700/50 p-3 rounded-lg border border-gray-600">
          <div className="text-xs text-gray-400 uppercase mb-1">CPU</div>
          <div className="text-sm font-semibold truncate" title={stats?.cpu.model}>{stats?.cpu.model || 'Loading...'}</div>
          <div className="mt-2 flex items-center gap-2">
             <div className="h-2 flex-grow bg-gray-600 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-blue-500 transition-all duration-500" 
                  style={{ width: `${stats?.cpu.usagePercent || 0}%` }}
                />
             </div>
             <span className="text-xs">{stats?.cpu.usagePercent || 0}%</span>
          </div>
        </div>

        {/* RAM Card */}
        <div className="bg-gray-700/50 p-3 rounded-lg border border-gray-600">
          <div className="text-xs text-gray-400 uppercase mb-1">RAM</div>
          <div className="text-sm font-semibold">{stats?.memory.usedGb || 0} / {stats?.memory.totalGb || 0} GB</div>
           <div className="mt-2 flex items-center gap-2">
             <div className="h-2 flex-grow bg-gray-600 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-purple-500 transition-all duration-500" 
                  style={{ width: `${stats?.memory.usagePercent || 0}%` }}
                />
             </div>
             <span className="text-xs">{stats?.memory.usagePercent || 0}%</span>
          </div>
        </div>

        {/* GPU Card */}
        <div className="bg-gray-700/50 p-3 rounded-lg border border-gray-600">
           <div className="text-xs text-gray-400 uppercase mb-1">GPU (Simulated)</div>
           <div className="text-sm font-semibold truncate">{stats?.gpu.model || 'Loading...'}</div>
           <div className="mt-2 flex items-center gap-2">
             <div className="h-2 flex-grow bg-gray-600 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-green-500 transition-all duration-500" 
                  style={{ width: `${stats?.gpu.usagePercent || 0}%` }}
                />
             </div>
             <span className="text-xs">{stats?.gpu.usagePercent || 0}%</span>
          </div>
        </div>

        <div className="mt-auto text-xs text-gray-500">
          Hardware Monitor Active via Node.js
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Chat Header */}
        <div className="h-14 border-b border-gray-700 flex items-center px-6 bg-gray-800/50 backdrop-blur">
          <span className="font-semibold text-lg">Research Agent Chat</span>
          <span className="ml-auto text-xs px-2 py-1 bg-green-900/50 text-green-400 rounded border border-green-800">
            Ollama Connected
          </span>
        </div>

        {/* Messages List */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 && (
             <div className="text-center text-gray-500 mt-20">
                <p className="text-xl">Welcome to UNLZ Research Agent</p>
                <p className="text-sm mt-2">Ask me anything about your university documents.</p>
             </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div 
                className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                  msg.role === 'user' 
                    ? 'bg-blue-600 text-white rounded-br-sm' 
                    : 'bg-gray-700 text-gray-100 rounded-bl-sm border border-gray-600'
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          {loading && (
             <div className="flex justify-start">
               <div className="bg-gray-700 rounded-2xl px-4 py-3 border border-gray-600">
                 <span className="animate-pulse">Thinking...</span>
               </div>
             </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="p-4 border-t border-gray-700 bg-gray-800">
          <div className="max-w-4xl mx-auto flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
              placeholder="Ask the researcher..."
              className="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500 transition-colors"
            />
            <button 
              onClick={sendMessage}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-500 px-6 py-2 rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
