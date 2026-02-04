import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const ENV_PATH = path.join(process.cwd(), '..', '.env');

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
         updateEnvVar(key, body[key]);
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
     return NextResponse.json({});
   }
   
   const envContent = fs.readFileSync(ENV_PATH, 'utf-8');
   const config: Record<string, string> = {};
   
   envContent.split('\n').forEach(line => {
     const [key, ...rest] = line.split('=');
     if (key && rest) config[key.trim()] = rest.join('=').trim();
   });

   return NextResponse.json(config);
}
