'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { 
  Send, 
  Bot, 
  User, 
  Settings, 
  Menu, 
  Plus, 
  MessageSquare,
  Search,
  Cpu
} from 'lucide-react';

type Message = {
  role: 'user' | 'assistant';
  content: string;
};

// Simple Translation Dictionary
const dictionary: any = {
  en: {
    welcome: 'Hello! I am the **UNLZ Agent**. I can help you research university documents, search the web, or answer general questions.\n\nHow can I help you today?',
    newChat: 'New Chat',
    history: 'History',
    noHistory: 'No recent chats',
    settings: 'Settings',
    user: 'User',
    placeholder: 'Ask anything...',
    systemOnline: 'SYSTEM ONLINE',
    systemOffline: 'SYSTEM OFFLINE',
    disclaimer: 'UNLZ Agent can make mistakes. Check important information.',
    status: 'STATUS',
    error: '⚠️ Error connecting to the agent. Please check if n8n is running.'
  },
  es: {
    welcome: '¡Hola! Soy el **Agente UNLZ**. Puedo ayudarte a investigar documentos universitarios, buscar en la web o responder preguntas generales.\n\n¿En qué puedo ayudarte hoy?',
    newChat: 'Nuevo Chat',
    history: 'Historial',
    noHistory: 'Sin chats recientes',
    settings: 'Configuración',
    user: 'Usuario',
    placeholder: 'Pregunta lo que sea...',
    systemOnline: 'SISTEMA ONLINE',
    systemOffline: 'SISTEMA OFFLINE',
    disclaimer: 'El Agente UNLZ puede cometer errores. Verifica la información importante.',
    status: 'ESTADO',
    error: '⚠️ Error al conectar con el agente. Verifica si n8n se está ejecutando.'
  },
  zh: {
    welcome: '你好！我是 **UNLZ Agent**。我可以帮你查阅大学文件、搜索网络或回答一般问题。\n\n今天有什么可以帮你的吗？',
    newChat: '新对话',
    history: '历史记录',
    noHistory: '无最近对话',
    settings: '设置',
    user: '用户',
    placeholder: '随便问...',
    systemOnline: '系统在线',
    systemOffline: '系统离线',
    disclaimer: 'UNLZ Agent 可能会犯错。请核实重要信息。',
    status: '状态',
    error: '⚠️ 连接代理时出错。请检查 n8n 是否正在运行。'
  }
};

export default function Home() {
  const [lang, setLang] = useState<'en' | 'es' | 'zh'>('en');
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '...' } // Will update with effect
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [stats, setStats] = useState<any>(null);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    // 1. Fetch Config to get Language
    fetch('/api/settings').then(res => res.json()).then(data => {
        if (data.AGENT_LANGUAGE) setLang(data.AGENT_LANGUAGE as 'en' | 'es' | 'zh');
    });

    // 2. Auto-Start MCP Server
    fetch('/api/system/control', { 
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start' })
    }).catch(console.error);

    // 3. Health Poll
    const fetchHealth = async () => {
      try {
        const res = await fetch('/api/health');
        const data = await res.json();
        setStats(data);
      } catch (e) {
        setStats({ status: 'offline', components: {} });
      }
    };
    fetchHealth();
    const interval = setInterval(fetchHealth, 10000); 
    return () => clearInterval(interval);
  }, []);

  const t = dictionary[lang] || dictionary.en;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = { role: 'user' as const, content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage.content }),
      });

      const data = await response.json();
      
      // Handle the response structure from n8n
      let botText = '';
      if (Array.isArray(data)) {
        botText = data[0]?.output || JSON.stringify(data);
      } else {
        botText = data.output || data.message || JSON.stringify(data);
      }

      setMessages(prev => [...prev, { role: 'assistant', content: botText }]);
    } catch (error) {
      console.error('Error:', error);
      setMessages(prev => [...prev, { role: 'assistant', content: t.error }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Simple Markdown Renderer
  const renderMarkdown = (text: string) => {
      // Basic replacement for demo purposes. 
      // In production, use 'react-markdown'
      let html = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br/>');
      
      return <div className="prose text-sm md:text-base leading-relaxed" dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <div className="flex h-screen bg-[#09090b] text-gray-100 font-sans overflow-hidden">
      
      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-[260px]' : 'w-0'} bg-black flex-shrink-0 transition-all duration-300 ease-in-out border-r border-[#27272a] flex flex-col overflow-hidden`}>
        <div className="p-3">
          <button 
            onClick={() => setMessages([{ role: 'assistant', content: t.welcome }])}
            className="flex items-center gap-3 w-full px-3 py-3 rounded-lg border border-[#27272a] hover:bg-[#27272a] transition-colors text-sm text-left text-white"
          >
            <Plus size={16} />
            <span>{t.newChat}</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2">
            <div className="text-xs font-semibold text-gray-500 mb-3 px-2">{t.history}</div>
            <div className="text-xs text-gray-600 px-2 italic">{t.noHistory}</div>
        </div>

        <div className="p-3 border-t border-[#27272a]">
            {stats && (
                 <div className="flex flex-col gap-1 px-3 py-2 text-xs mb-2 bg-[#18181b] rounded border border-[#27272a]">
                    <div className="flex items-center gap-2 font-mono font-bold text-gray-400 border-b border-[#27272a] pb-1 mb-1">
                        <span className={`w-2 h-2 rounded-full ${stats.status === 'online' ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></span>
                        {t.status}: {stats.status.toUpperCase()}
                    </div>
                    {stats.components && Object.entries(stats.components).map(([key, val]: any) => (
                        <div key={key} className="flex justify-between items-center">
                            <span className="opacity-70 uppercase text-[10px]">{key}</span>
                            <span className={`
                                w-1.5 h-1.5 rounded-full 
                                ${val.status === 'ok' ? 'bg-green-500' : val.status === 'warning' ? 'bg-yellow-500' : 'bg-red-500'}
                            `} title={val.details}></span>
                        </div>
                    ))}
                </div>
            )}
            <Link href="/settings" className="flex items-center gap-3 w-full px-3 py-3 rounded-lg hover:bg-[#27272a] transition-colors text-sm text-gray-200">
                <Settings size={18} />
                <span>{t.settings}</span>
            </Link>
             <div className="flex items-center gap-3 px-3 py-3 mt-1">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-xs font-bold">U</div>
                <div className="text-sm font-medium">{t.user}</div>
            </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-full relative">
        
        {/* Header (Mobile / Desktop Toggle) */}
        <div className="flex items-center justify-between p-4 md:hidden border-b border-[#27272a]">
            <button onClick={() => setSidebarOpen(!sidebarOpen)} className="text-gray-400">
                <Menu />
            </button>
            <span className="font-semibold">UNLZ Agent</span>
             <Link href="/settings"><Settings size={20} className="text-gray-400"/></Link>
        </div>
        
        {!sidebarOpen && (
            <div className="hidden md:flex absolute top-4 left-4 z-10">
                 <button onClick={() => setSidebarOpen(true)} className="text-gray-400 hover:text-white bg-black/50 p-2 rounded-md">
                    <Menu size={24} />
                 </button>
            </div>
        )}

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 scroll-smooth">
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((msg, idx) => (
              <div key={idx} className={`flex gap-4 ${msg.role === 'assistant' ? 'bg-transparent' : 'justify-end'}`}>
                
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-emerald-600 flex-shrink-0 flex items-center justify-center mt-1">
                    <Bot size={18} className="text-white" />
                  </div>
                )}

                <div className={`
                    max-w-[85%] rounded-2xl px-5 py-3 text-sm md:text-base shadow-sm
                    ${msg.role === 'user' 
                        ? 'bg-[#27272a] text-white rounded-tr-sm' 
                        : 'bg-transparent text-gray-100 pl-0'}
                `}>
                    {msg.role === 'user' ? (
                        <div>{msg.content}</div>
                    ) : (
                        renderMarkdown(msg.content)
                    )}
                </div>

                {msg.role === 'user' && (
                   <div className="w-8 h-8 rounded-full bg-[#3f3f46] flex-shrink-0 flex items-center justify-center mt-1">
                     <User size={18} className="text-white" />
                   </div>
                )}

              </div>
            ))}
            {isLoading && (
               <div className="flex gap-4 animate-pulse">
                  <div className="w-8 h-8 rounded-full bg-emerald-600 flex-shrink-0 flex items-center justify-center">
                    <Bot size={18} className="text-white" />
                  </div>
                  <div className="flex gap-1 items-center h-8">
                      <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></div>
                      <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce delay-100"></div>
                      <div className="w-2 h-2 bg-gray-500 rounded-full animate-bounce delay-200"></div>
                  </div>
               </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
        <div className="p-4 md:p-6 bg-[#09090b]">
          <div className="max-w-3xl mx-auto">
            <form onSubmit={handleSubmit} className="relative flex items-end gap-2 bg-[#18181b] border border-[#27272a] rounded-xl px-4 py-3 shadow-lg focus-within:ring-1 focus-within:ring-gray-500 transition-all">
                <button type="button" className="text-gray-400 hover:text-white p-1 pb-2">
                    <Plus size={20} />
                </button>
                <textarea 
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSubmit(e);
                        }
                    }}
                    placeholder={t.placeholder}
                    className="w-full bg-transparent text-white placeholder-gray-500 outline-none resize-none max-h-32 py-1 scrollbar-hide"
                    rows={1}
                />
                <button 
                  type="submit" 
                  disabled={isLoading || !input.trim()}
                  className={`
                    p-2 rounded-lg transition-all duration-200 mb-0.5
                    ${input.trim() ? 'bg-white text-black hover:bg-gray-200' : 'bg-[#27272a] text-gray-500 cursor-not-allowed'}
                  `}
                >
                  <Send size={16} />
                </button>
            </form>
            <div className="text-center text-xs text-gray-500 mt-2">
                {t.disclaimer}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
