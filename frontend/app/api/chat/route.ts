import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';

const ENV_PATH = path.join(process.cwd(), '..', '.env');
const DEFAULT_N8N_WEBHOOK_URL = 'http://127.0.0.1:5678/webhook/chat';

function buildWebhookCandidates(rawUrl: string) {
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
  } catch {
    // Keep configured URL only.
  }

  return Array.from(candidates);
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { message } = body;

    // Load dynamic config
    const envConfig = fs.existsSync(ENV_PATH)
      ? dotenv.parse(fs.readFileSync(ENV_PATH))
      : {};
    const configuredWebhookUrl = envConfig.N8N_WEBHOOK_URL || DEFAULT_N8N_WEBHOOK_URL;
    const webhookCandidates = buildWebhookCandidates(configuredWebhookUrl);

    let lastError: unknown = null;

    for (const webhookUrl of webhookCandidates) {
      try {
        const response = await fetch(webhookUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ message }),
        });

        if (!response.ok) {
          const text = await response.text();
          return NextResponse.json(
            { error: `n8n Error: ${response.status} - ${text}` },
            { status: response.status }
          );
        }

        const data = await response.json();
        return NextResponse.json(data);
      } catch (error) {
        lastError = error;
      }
    }

    const detail =
      lastError instanceof Error ? lastError.message : 'Unknown network error';
    return NextResponse.json(
      {
        error: `Cannot reach n8n webhook. Checked: ${webhookCandidates.join(', ')}. Detail: ${detail}`,
      },
      { status: 502 }
    );

  } catch (error) {
    console.error('Chat Proxy Error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
