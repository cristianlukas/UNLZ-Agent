import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const ENV_PATH = path.join(process.cwd(), '..', '.env');
const DEFAULT_OLLAMA_BASE_URL = 'http://localhost:11434';
const DEFAULT_N8N_WEBHOOK_URL = 'http://127.0.0.1:5678/webhook/chat';

export async function POST(req: Request) {
  try {
    const body = await req.json();

    // Read existing .env if it exists
    let envContent = '';
    if (fs.existsSync(ENV_PATH)) {
      envContent = fs.readFileSync(ENV_PATH, 'utf-8');
    }

    // Helper to update or append env var
    const updateEnvVar = (key: string, value: string) => {
      const regex = new RegExp(`^${key}=.*`, 'm');
      if (regex.test(envContent)) {
        envContent = envContent.replace(regex, `${key}=${value}`);
      } else {
        envContent += `\n${key}=${value}`;
      }
    };

    // Iterate over all keys in the body and update .env
    Object.keys(body).forEach(key => {
      // Simple validation: only allow uppercase keys likely to be env vars
      if (key === key.toUpperCase() && body[key] !== undefined) {
         let value = String(body[key]);
         if (key === 'OLLAMA_BASE_URL' && !value.trim()) {
           value = DEFAULT_OLLAMA_BASE_URL;
         } else if (key === 'N8N_WEBHOOK_URL' && !value.trim()) {
           value = DEFAULT_N8N_WEBHOOK_URL;
         }
         updateEnvVar(key, value);
      }
    });

    fs.writeFileSync(ENV_PATH, envContent.trim());

    return NextResponse.json({ success: true, message: 'Settings saved to .env' });
  } catch (error) {
    console.error('Settings API Error:', error);
    return NextResponse.json({ error: 'Failed to save settings' }, { status: 500 });
  }
}

export async function GET() {
   if (!fs.existsSync(ENV_PATH)) {
     return NextResponse.json({
      OLLAMA_BASE_URL: DEFAULT_OLLAMA_BASE_URL,
      N8N_WEBHOOK_URL: DEFAULT_N8N_WEBHOOK_URL,
     });
   }
   
   const envContent = fs.readFileSync(ENV_PATH, 'utf-8');
   const config: Record<string, string> = {};
   
   envContent.split('\n').forEach(line => {
     const [key, ...rest] = line.split('=');
     if (key && rest) config[key.trim()] = rest.join('=').trim();
   });
   
   if (!config.OLLAMA_BASE_URL?.trim()) {
     config.OLLAMA_BASE_URL = DEFAULT_OLLAMA_BASE_URL;
   }
   if (!config.N8N_WEBHOOK_URL?.trim()) {
     config.N8N_WEBHOOK_URL = DEFAULT_N8N_WEBHOOK_URL;
   }

   return NextResponse.json(config);
}
