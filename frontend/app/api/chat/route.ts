import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';

const ENV_PATH = path.join(process.cwd(), '..', '.env');

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { message } = body;

    // Load dynamic config
    const envConfig = dotenv.parse(fs.readFileSync(ENV_PATH));
    const N8N_WEBHOOK_URL = envConfig.N8N_WEBHOOK_URL || 'http://localhost:5678/webhook/chat';

    const response = await fetch(N8N_WEBHOOK_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json({ error: `n8n Error: ${response.status} - ${text}` }, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);

  } catch (error) {
    console.error('Chat Proxy Error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
