import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

async function checkUrl(url: string, method: string = 'GET'): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);
    const res = await fetch(url, { method, signal: controller.signal });
    clearTimeout(timeoutId);
    return res.ok;
  } catch {
    return false;
  }
}

function buildAlternateUrls(baseUrl: string, suffix: string): string[] {
  const sanitized = baseUrl.trim().replace(/\/+$/, '');
  const urls = new Set<string>([`${sanitized}${suffix}`]);
  try {
    const parsed = new URL(sanitized);
    if (parsed.hostname === 'localhost') {
      parsed.hostname = '127.0.0.1';
      urls.add(`${parsed.toString().replace(/\/+$/, '')}${suffix}`);
    } else if (parsed.hostname === '127.0.0.1') {
      parsed.hostname = 'localhost';
      urls.add(`${parsed.toString().replace(/\/+$/, '')}${suffix}`);
    }
  } catch { /* keep original */ }
  return Array.from(urls);
}

export async function GET() {
  const envPath = path.join(process.cwd(), '..', '.env');
  const envContent = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf-8') : '';

  const config: Record<string, string> = {};
  envContent.split('\n').forEach((line) => {
    const [key, ...rest] = line.split('=');
    if (key && rest.length) config[key.trim()] = rest.join('=').trim();
  });

  const checks: Record<string, { status: string; details: string }> = {
    llm: { status: 'unknown', details: '' },
    vectordb: { status: 'unknown', details: '' },
    n8n: { status: 'unknown', details: '' },
    mcp: { status: 'unknown', details: '' },
  };

  // ── MCP ──────────────────────────────────────────────────────────────────
  const mcpPort = config['MCP_PORT'] || '8000';
  let mcpReachable = false;

  for (const mcpUrl of [`http://127.0.0.1:${mcpPort}/`, `http://localhost:${mcpPort}/`]) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), 1000);
    try {
      await fetch(mcpUrl, { signal: controller.signal });
      checks.mcp = { status: 'ok', details: `MCP Server active on port ${mcpPort}` };
      mcpReachable = true;
      break;
    } catch (error: unknown) {
      const e = error as { name?: string; cause?: { code?: string } };
      if (!mcpReachable) {
        if (e?.name === 'AbortError') {
          checks.mcp = { status: 'warning', details: `MCP Port ${mcpPort} open (slow)` };
        } else if (e?.cause?.code === 'ECONNREFUSED') {
          checks.mcp = { status: 'error', details: `Port ${mcpPort} connection refused` };
        } else {
          checks.mcp = { status: 'error', details: `MCP unreachable on port ${mcpPort}` };
        }
      }
    } finally {
      clearTimeout(id);
    }
  }

  // ── LLM ──────────────────────────────────────────────────────────────────
  const llmProvider = (config['LLM_PROVIDER'] || 'ollama').toLowerCase();

  if (llmProvider === 'llamacpp') {
    const host = config['LLAMACPP_HOST'] || '127.0.0.1';
    const port = config['LLAMACPP_PORT'] || '8080';
    const healthUrl = `http://${host}:${port}/health`;
    const ok = await checkUrl(healthUrl);
    const alias = config['LLAMACPP_MODEL_ALIAS'] || 'local-model';
    checks.llm = {
      status: ok ? 'ok' : 'error',
      details: ok
        ? `llama.cpp running — model: ${alias}`
        : `llama.cpp unreachable at http://${host}:${port}`,
    };
  } else if (llmProvider === 'ollama') {
    const configuredUrl = config['OLLAMA_BASE_URL']?.trim() || 'http://localhost:11434';
    const ollamaCheckUrls = buildAlternateUrls(configuredUrl, '/api/tags');
    let reachableUrl = '';
    for (const url of ollamaCheckUrls) {
      if (await checkUrl(url)) {
        reachableUrl = url.replace(/\/api\/tags$/, '');
        break;
      }
    }
    checks.llm = {
      status: reachableUrl ? 'ok' : 'error',
      details: reachableUrl
        ? `Ollama running at ${reachableUrl}`
        : `Ollama unreachable at ${configuredUrl}`,
    };
  } else {
    const hasKey = !!config['OPENAI_API_KEY'];
    checks.llm = {
      status: hasKey ? 'ok' : 'warning',
      details: hasKey ? 'OpenAI key configured' : 'OpenAI key missing',
    };
  }

  // ── Vector DB ─────────────────────────────────────────────────────────────
  const vectorProvider = (config['VECTOR_DB_PROVIDER'] || 'chroma').toLowerCase();
  if (vectorProvider === 'chroma') {
    const dataDir = path.join(process.cwd(), '..', 'data');
    if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
    checks.vectordb = {
      status: 'ok',
      details: 'Local /data folder ready',
    };
  } else {
    const hasUrl = !!config['SUPABASE_URL'];
    const hasKey = !!config['SUPABASE_KEY'];
    checks.vectordb = {
      status: hasUrl && hasKey ? 'ok' : 'error',
      details: hasUrl && hasKey ? 'Supabase credentials set' : 'Missing Supabase config',
    };
  }

  // ── n8n ───────────────────────────────────────────────────────────────────
  const n8nEnabled = (config['N8N_ENABLED'] ?? 'true').toLowerCase() !== 'false';

  if (!n8nEnabled) {
    checks.n8n = { status: 'ok', details: 'n8n disabled — using direct LLM mode' };
  } else {
    const configuredN8nWebhook = config['N8N_WEBHOOK_URL']?.trim() || 'http://127.0.0.1:5678/webhook/chat';
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
      checks.n8n = { status: 'error', details: 'Invalid webhook URL' };
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
  }

  const isHealthy = Object.values(checks).every((c) => c.status === 'ok');

  return NextResponse.json({
    status: isHealthy ? 'online' : 'degraded',
    components: checks,
  });
}
