import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const ENV_PATH = path.join(process.cwd(), '..', '.env');

const DEFAULTS: Record<string, string> = {
  OLLAMA_BASE_URL: 'http://localhost:11434',
  OLLAMA_MODEL: 'qwen2.5-coder:14b',
  N8N_WEBHOOK_URL: 'http://127.0.0.1:5678/webhook/chat',
  N8N_ENABLED: 'true',
  LLAMACPP_HOST: '127.0.0.1',
  LLAMACPP_PORT: '8080',
  LLAMACPP_CONTEXT_SIZE: '32768',
  LLAMACPP_N_GPU_LAYERS: '999',
  LLAMACPP_FLASH_ATTN: 'true',
  LLAMACPP_MODEL_ALIAS: 'local-model',
  LLAMACPP_CACHE_TYPE_K: '',
  LLAMACPP_CACHE_TYPE_V: '',
  LLAMACPP_EXTRA_ARGS: '',
};

export async function POST(req: Request) {
  try {
    const body = await req.json();

    let envContent = fs.existsSync(ENV_PATH) ? fs.readFileSync(ENV_PATH, 'utf-8') : '';

    const updateEnvVar = (key: string, value: string) => {
      const regex = new RegExp(`^${key}=.*`, 'm');
      if (regex.test(envContent)) {
        envContent = envContent.replace(regex, `${key}=${value}`);
      } else {
        envContent += `\n${key}=${value}`;
      }
    };

    Object.keys(body).forEach((key) => {
      if (key === key.toUpperCase() && body[key] !== undefined) {
        let value = String(body[key]);
        if (DEFAULTS[key] !== undefined && !value.trim()) {
          value = DEFAULTS[key];
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
      OLLAMA_BASE_URL: DEFAULTS.OLLAMA_BASE_URL,
      OLLAMA_MODEL: DEFAULTS.OLLAMA_MODEL,
      N8N_WEBHOOK_URL: DEFAULTS.N8N_WEBHOOK_URL,
      N8N_ENABLED: DEFAULTS.N8N_ENABLED,
      LLAMACPP_HOST: DEFAULTS.LLAMACPP_HOST,
      LLAMACPP_PORT: DEFAULTS.LLAMACPP_PORT,
      LLAMACPP_CONTEXT_SIZE: DEFAULTS.LLAMACPP_CONTEXT_SIZE,
      LLAMACPP_N_GPU_LAYERS: DEFAULTS.LLAMACPP_N_GPU_LAYERS,
      LLAMACPP_FLASH_ATTN: DEFAULTS.LLAMACPP_FLASH_ATTN,
      LLAMACPP_MODEL_ALIAS: DEFAULTS.LLAMACPP_MODEL_ALIAS,
    });
  }

  const envContent = fs.readFileSync(ENV_PATH, 'utf-8');
  const config: Record<string, string> = {};

  envContent.split('\n').forEach((line) => {
    const [key, ...rest] = line.split('=');
    if (key && rest.length) config[key.trim()] = rest.join('=').trim();
  });

  // Apply defaults for missing keys
  Object.entries(DEFAULTS).forEach(([key, defaultVal]) => {
    if (!config[key]?.trim() && defaultVal) {
      config[key] = defaultVal;
    }
  });

  return NextResponse.json(config);
}
