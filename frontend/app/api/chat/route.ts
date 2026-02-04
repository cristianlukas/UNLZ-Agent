import { NextResponse } from 'next/server';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { message } = body;

    // Call n8n Webhook
    // Note: n8n local webhook URL. If n8n runs in Docker, use http://host.docker.internal:5678
    // If n8n runs natively, use http://localhost:5678
    // Using localhost here assuming the user runs "npm run dev" on the host machine.
    const N8N_WEBHOOK_URL = 'http://localhost:5678/webhook/chat';

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
    // Assuming n8n "Respond to Webhook" node returns { "response": "..." }
    return NextResponse.json(data);

  } catch (error) {
    console.error('Chat Proxy Error:', error);
    return NextResponse.json({ error: 'Internal Server Error' }, { status: 500 });
  }
}
