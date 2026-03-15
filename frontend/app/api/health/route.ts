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

function buildOllamaCheckUrls(baseUrl: string) {
  const sanitizedBase = baseUrl.trim().replace(/\/+$/, '');
  const urls = new Set<string>([`${sanitizedBase}/api/tags`]);

  try {
    const parsed = new URL(sanitizedBase);
    if (parsed.hostname === 'localhost') {
      parsed.hostname = '127.0.0.1';
      urls.add(`${parsed.toString().replace(/\/+$/, '')}/api/tags`);
    } else if (parsed.hostname === '127.0.0.1') {
      parsed.hostname = 'localhost';
      urls.add(`${parsed.toString().replace(/\/+$/, '')}/api/tags`);
    }
  } catch {
    // Keep configured URL only if it cannot be parsed.
  }

  return Array.from(urls);
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
  // Check both IPv4 and localhost to avoid false negatives on some Windows setups.
  const mcpUrls = [`http://127.0.0.1:${mcpPort}/`, `http://localhost:${mcpPort}/`];
  let mcpReachable = false;
  let lastMcpError: unknown = null;

  for (const mcpUrl of mcpUrls) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), 1000);
    try {
      await fetch(mcpUrl, { signal: controller.signal });
      checks.mcp = { status: 'ok', details: `MCP Server active on port ${mcpPort}` };
      mcpReachable = true;
      break;
    } catch (error) {
      lastMcpError = error;
    } finally {
      clearTimeout(id);
    }
  }

  if (!mcpReachable) {
    const err = lastMcpError as { name?: string; cause?: { code?: string } } | null;
    if (err?.name === 'AbortError') {
      checks.mcp = { status: 'warning', details: `MCP Port ${mcpPort} Open (slow)` };
    } else if (err?.cause?.code === 'ECONNREFUSED') {
      checks.mcp = { status: 'error', details: `Port ${mcpPort} Connection Refused` };
    } else {
      checks.mcp = { status: 'error', details: `MCP unreachable on port ${mcpPort}` };
    }
  }

  // 1. LLM Check
  const llmProvider = config['LLM_PROVIDER'] || 'ollama';
  if (llmProvider === 'ollama') {
    const configuredUrl = config['OLLAMA_BASE_URL']?.trim() || 'http://localhost:11434';
    const ollamaCheckUrls = buildOllamaCheckUrls(configuredUrl);
    let reachableUrl = '';

    for (const ollamaCheckUrl of ollamaCheckUrls) {
      if (await checkUrl(ollamaCheckUrl)) {
        reachableUrl = ollamaCheckUrl.replace(/\/api\/tags$/, '');
        break;
      }
    }

    checks.llm = {
      status: reachableUrl ? 'ok' : 'error',
      details: reachableUrl
        ? `Ollama Running at ${reachableUrl}`
        : `Ollama unreachable at ${configuredUrl}`
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
    // Ensure local data folder exists for local vector storage.
    const dataDir = path.join(process.cwd(), '..', 'data');
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }
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
  const configuredN8nWebhook =
    config['N8N_WEBHOOK_URL']?.trim() || 'http://127.0.0.1:5678/webhook/chat';
  const n8nOrigins = new Set<string>();

  try {
    const parsed = new URL(configuredN8nWebhook);
    n8nOrigins.add(parsed.origin);
    if (parsed.hostname === 'localhost') {
      parsed.hostname = '127.0.0.1';
      n8nOrigins.add(parsed.origin);
    } else if (parsed.hostname === '127.0.0.1') {
      parsed.hostname = 'localhost';
      n8nOrigins.add(parsed.origin);
    }
  } catch {
    checks.n8n = { status: 'error', details: 'Invalid Webhook URL' };
  }

  if (checks.n8n.status === 'unknown') {
    let reachableOrigin = '';
    for (const origin of n8nOrigins) {
      if (await checkUrl(`${origin}/healthz`) || await checkUrl(`${origin}/rest/settings`)) {
        reachableOrigin = origin;
        break;
      }
    }

    checks.n8n = reachableOrigin
      ? { status: 'ok', details: `n8n reachable at ${reachableOrigin}` }
      : { status: 'error', details: `n8n unreachable from ${configuredN8nWebhook}` };
  }

  // Global Status
  const isHealthy = Object.values(checks).every(c => c.status === 'ok');

  return NextResponse.json({
    status: isHealthy ? 'online' : 'degraded',
    components: checks
  });
}
