import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';

const ENV_PATH = path.join(process.cwd(), '..', '.env');
const DEFAULT_N8N_WEBHOOK_URL = 'http://127.0.0.1:5678/webhook/chat';

function loadEnv(): Record<string, string> {
  return fs.existsSync(ENV_PATH) ? dotenv.parse(fs.readFileSync(ENV_PATH)) : {};
}

function buildWebhookCandidates(rawUrl: string): string[] {
  const baseUrl = rawUrl.trim().replace(/\/+$/, '');
  const candidates = new Set<string>([baseUrl]);
  try {
    const parsed = new URL(baseUrl);
    if (parsed.hostname === 'localhost') {
      parsed.hostname = '127.0.0.1';
      candidates.add(parsed.toString().replace(/\/+$/, ''));
    } else if (parsed.hostname === '127.0.0.1') {
      parsed.hostname = 'localhost';
      candidates.add(parsed.toString().replace(/\/+$/, ''));
    }
  } catch { /* keep original */ }
  return Array.from(candidates);
}

async function fetchRagContext(mcpPort: string, message: string): Promise<string> {
  try {
    const res = await fetch(`http://127.0.0.1:${mcpPort}/tools/call`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'search_local_knowledge', arguments: { query: message } }),
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return '';
    const docs: Array<Record<string, string>> = await res.json();
    if (!Array.isArray(docs) || docs.length === 0) return '';
    return docs
      .map((d) => d.page_content || d.content || JSON.stringify(d))
      .filter(Boolean)
      .join('\n\n');
  } catch {
    return '';
  }
}

async function directChat(
  message: string,
  envConfig: Record<string, string>
): Promise<NextResponse> {
  const provider = (envConfig.LLM_PROVIDER || 'ollama').toLowerCase();
  const mcpPort = envConfig.MCP_PORT || '8000';
  const language = (envConfig.AGENT_LANGUAGE || 'en').toLowerCase();

  let baseUrl: string;
  let model: string;
  let apiKey = 'not-needed';

  if (provider === 'llamacpp') {
    const host = envConfig.LLAMACPP_HOST || '127.0.0.1';
    const port = envConfig.LLAMACPP_PORT || '8080';
    baseUrl = `http://${host}:${port}/v1`;
    model = envConfig.LLAMACPP_MODEL_ALIAS || 'local-model';
  } else if (provider === 'openai') {
    baseUrl = 'https://api.openai.com/v1';
    model = envConfig.OPENAI_MODEL || 'gpt-4o-mini';
    apiKey = envConfig.OPENAI_API_KEY || '';
  } else {
    // ollama — exposes OpenAI-compat at /v1
    const ollamaBase = (envConfig.OLLAMA_BASE_URL || 'http://localhost:11434').replace(/\/$/, '');
    baseUrl = `${ollamaBase}/v1`;
    model = envConfig.OLLAMA_MODEL || 'qwen2.5-coder:14b';
  }

  const ragContext = await fetchRagContext(mcpPort, message);

  const defaultSysPrompts: Record<string, string> = {
    en: 'You are a helpful assistant for Universidad Nacional de Lomas de Zamora.',
    es: 'Eres un asistente útil de la Universidad Nacional de Lomas de Zamora.',
    zh: '您是洛马斯·德萨莫拉国立大学的助理。',
  };
  let systemContent = defaultSysPrompts[language] || defaultSysPrompts.en;
  if (ragContext) systemContent += `\n\nRelevant context:\n${ragContext}`;

  const llmRes = await fetch(`${baseUrl}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'system', content: systemContent },
        { role: 'user', content: message },
      ],
      stream: false,
    }),
    signal: AbortSignal.timeout(120_000),
  });

  if (!llmRes.ok) {
    const text = await llmRes.text();
    return NextResponse.json(
      { error: `LLM Error (${provider}): ${llmRes.status} - ${text}` },
      { status: llmRes.status }
    );
  }

  const data = await llmRes.json();
  const response = data?.choices?.[0]?.message?.content ?? 'No response from model.';
  return NextResponse.json({ response });
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { message } = body;

    const envConfig = loadEnv();
    const n8nEnabled = (envConfig.N8N_ENABLED ?? 'true').toLowerCase() !== 'false';

    // ── Direct mode (n8n disabled) ────────────────────────────────────────
    if (!n8nEnabled) {
      return await directChat(message, envConfig);
    }

    // ── n8n proxy mode ────────────────────────────────────────────────────
    const configuredWebhookUrl = envConfig.N8N_WEBHOOK_URL || DEFAULT_N8N_WEBHOOK_URL;
    const webhookCandidates = buildWebhookCandidates(configuredWebhookUrl);
    let lastError: unknown = null;

    for (const webhookUrl of webhookCandidates) {
      try {
        const response = await fetch(webhookUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message }),
        });

        if (!response.ok) {
          const text = await response.text();
          return NextResponse.json(
            { error: `n8n Error: ${response.status} - ${text}` },
            { status: response.status }
          );
        }

        return NextResponse.json(await response.json());
      } catch (error) {
        lastError = error;
      }
    }

    const detail = lastError instanceof Error ? lastError.message : 'Unknown network error';
    return NextResponse.json(
      { error: `Cannot reach n8n webhook. Checked: ${webhookCandidates.join(', ')}. Detail: ${detail}` },
      { status: 502 }
    );
  } catch (error) {
    console.error('Chat Proxy Error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
