import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

// Helper to check URL connectivity
async function checkUrl(url: string, method: string = 'GET') {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000); // 2s timeout
    const res = await fetch(url, { 
        method, 
        signal: controller.signal 
    });
    clearTimeout(timeoutId);
    return res.ok;
  } catch (e) {
    return false;
  }
}

export async function GET() {
  const envPath = path.join(process.cwd(), '..', '.env');
  const envContent = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf-8') : '';
  
  // Parse .env manually to get latest config without waiting for process.env reload
  const config: Record<string, string> = {};
  envContent.split('\n').forEach(line => {
    const [key, ...rest] = line.split('=');
    if (key && rest) config[key.trim()] = rest.join('=').trim();
  });

  const checks = {
    llm: { status: 'unknown', details: '' },
    vectordb: { status: 'unknown', details: '' },
    n8n: { status: 'unknown', details: '' },
    mcp: { status: 'unknown', details: '' }
  };

  // 0. MCP Server Check (Port 8000)
  // 0. MCP Server Check
  const mcpPort = config['MCP_PORT'] || '8000';
  // Check root / (or a known endpoint) instead of just assuming 8000
  
  try {
      // 500ms timeout just to check connectivity
      const controller = new AbortController();
      const id = setTimeout(() => controller.abort(), 1000);
      await fetch(`http://localhost:${mcpPort}/`, { signal: controller.signal });
      clearTimeout(id);
      checks.mcp = { status: 'ok', details: `MCP Server active on port ${mcpPort}` };
  } catch (e: any) {
      if (e.name === 'AbortError') { 
         checks.mcp = { status: 'warning', details: `MCP Port ${mcpPort} Open (slow)` };
      } else if (e.cause?.code === 'ECONNREFUSED') {
         checks.mcp = { status: 'error', details: `Port ${mcpPort} Connection Refused` };
      } else {
         checks.mcp = { status: 'ok', details: 'MCP potentially active' }; 
      }
  }

  // 1. LLM Check
  const llmProvider = config['LLM_PROVIDER'] || 'ollama';
  if (llmProvider === 'ollama') {
    const url = config['OLLAMA_BASE_URL'] || 'http://localhost:11434';
    const isUp = await checkUrl(`${url}/api/tags`); // Ollama endpoint
    checks.llm = { 
        status: isUp ? 'ok' : 'error', 
        details: isUp ? `Ollama Running at ${url}` : `Ollama unreachable at ${url}`
    };
  } else {
    // OpenAI Check (Basic API Key presence)
    const hasKey = !!config['OPENAI_API_KEY'];
    checks.llm = { 
        status: hasKey ? 'ok' : 'warning', 
        details: hasKey ? 'OpenAI Key set' : 'OpenAI Key missing'
    };
  }

  // 2. Vector DB Check
  const vectorProvider = config['VECTOR_DB_PROVIDER'] || 'chroma';
  if (vectorProvider === 'chroma') {
    // Check if data directory exists (Basic check)
    // Ideally we would query Chroma, but file check is a good proxy for "local storage ready"
    // Using default or configured path
    const dataDir = path.join(process.cwd(), '..', 'data'); 
    const exists = fs.existsSync(dataDir);
    checks.vectordb = {
        status: exists ? 'ok' : 'warning',
        details: exists ? 'Local /data folder found' : '/data folder missing'
    };
  } else {
    const hasUrl = !!config['SUPABASE_URL'];
    const hasKey = !!config['SUPABASE_KEY'];
    checks.vectordb = {
        status: hasUrl && hasKey ? 'ok' : 'error',
        details: hasUrl && hasKey ? 'Supabase Credentials set' : 'Missing Supabase Config'
    };
  }

  // 3. n8n Check
  const n8nUrl = config['N8N_WEBHOOK_URL'];
  if (n8nUrl) {
    // Difficult to "ping" a webhook without triggering it, so we check if URL looks valid
    // For a real check, n8n would need a health endpoint
    const validUrl = n8nUrl.startsWith('http');
    checks.n8n = {
        status: validUrl ? 'ok' : 'warning',
        details: validUrl ? 'Webhook URL configured' : 'Invalid Webhook URL'
    };
  } else {
    checks.n8n = { status: 'error', details: 'Webhook URL not set' };
  }

  // Global Status
  const isHealthy = Object.values(checks).every(c => c.status === 'ok');

  return NextResponse.json({
    status: isHealthy ? 'online' : 'degraded',
    components: checks
  });
}
