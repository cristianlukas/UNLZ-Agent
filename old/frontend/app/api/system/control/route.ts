import { NextResponse } from 'next/server';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import fs from 'fs';
import net from 'net';
import dotenv from 'dotenv';

declare global {
  var mcpProcess: ChildProcess | undefined;
  var llamacppProcess: ChildProcess | undefined;
}

const SERVER_SCRIPT = path.join(process.cwd(), '..', 'mcp_server.py');
const PROJECT_ROOT = path.join(process.cwd(), '..');
const ENV_PATH = path.join(PROJECT_ROOT, '.env');

function loadEnv(): Record<string, string> {
  return fs.existsSync(ENV_PATH) ? dotenv.parse(fs.readFileSync(ENV_PATH)) : {};
}

function isPortOpen(port: number, host: string, timeoutMs = 800): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let settled = false;
    const finish = (result: boolean) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(result);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
    socket.connect(port, host);
  });
}

async function isMcpPortReachable(port: number) {
  return (await isPortOpen(port, '127.0.0.1')) || isPortOpen(port, 'localhost');
}

function resolvePythonCommand(): string {
  const fromEnv = process.env.MCP_PYTHON;
  if (fromEnv) return fromEnv;
  const candidates =
    process.platform === 'win32'
      ? [
          path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe'),
          path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe'),
        ]
      : [
          path.join(PROJECT_ROOT, 'venv', 'bin', 'python'),
          path.join(PROJECT_ROOT, '.venv', 'bin', 'python'),
        ];
  return candidates.find((c) => fs.existsSync(c)) ?? (process.platform === 'win32' ? 'python' : 'python3');
}

if (process.env.NODE_ENV !== 'production') {
  const cleanup = () => {
    if (global.mcpProcess) { global.mcpProcess.kill(); }
    if (global.llamacppProcess) { global.llamacppProcess.kill(); }
  };
  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);
  process.on('exit', cleanup);
}

function buildLlamacppArgs(env: Record<string, string>): string[] {
  const exe = env.LLAMACPP_EXECUTABLE || '';
  const model = env.LLAMACPP_MODEL_PATH || '';
  const alias = env.LLAMACPP_MODEL_ALIAS || 'local-model';
  const host = env.LLAMACPP_HOST || '127.0.0.1';
  const port = env.LLAMACPP_PORT || '8080';
  const ctx = env.LLAMACPP_CONTEXT_SIZE || '32768';
  const ngl = env.LLAMACPP_N_GPU_LAYERS || '999';
  const flashAttn = (env.LLAMACPP_FLASH_ATTN ?? 'true').toLowerCase() !== 'false';
  const cacheK = env.LLAMACPP_CACHE_TYPE_K || '';
  const cacheV = env.LLAMACPP_CACHE_TYPE_V || '';
  const extra = env.LLAMACPP_EXTRA_ARGS || '';

  if (!exe) throw new Error('LLAMACPP_EXECUTABLE not configured');
  if (!model) throw new Error('LLAMACPP_MODEL_PATH not configured');

  const args = [
    '-m', model,
    '--alias', alias,
    '--host', host,
    '--port', port,
    '-c', ctx,
    '-ngl', ngl,
  ];
  if (flashAttn) args.push('--flash-attn');
  if (cacheK) args.push('--cache-type-k', cacheK);
  if (cacheV) args.push('--cache-type-v', cacheV);
  if (extra) args.push(...extra.split(' ').filter(Boolean));

  return [exe, ...args];
}

export async function POST(req: Request) {
  try {
    const { action } = await req.json();
    const envConfig = loadEnv();
    const port = Number(envConfig.MCP_PORT || process.env.MCP_PORT || '8000');

    // ── MCP start ─────────────────────────────────────────────────────────
    if (action === 'start') {
      if (global.mcpProcess?.exitCode === null && !global.mcpProcess.killed) {
        return NextResponse.json({ status: 'running', message: 'MCP server already running' });
      }
      if (await isMcpPortReachable(port)) {
        return NextResponse.json({ status: 'running', message: `MCP already on port ${port}` });
      }

      const pythonCommand = resolvePythonCommand();
      global.mcpProcess = spawn(pythonCommand, ['-u', SERVER_SCRIPT], {
        cwd: path.dirname(SERVER_SCRIPT),
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, MCP_PORT: String(port) },
      });

      global.mcpProcess.stdout?.on('data', (d) => console.log(`MCP STDOUT: ${d}`));
      global.mcpProcess.stderr?.on('data', (d) => console.error(`MCP STDERR: ${d}`));
      global.mcpProcess.on('error', (e) => console.error('MCP process error:', e));
      global.mcpProcess.on('close', (c) => console.log(`MCP process exited: ${c}`));

      return NextResponse.json({ status: 'started', pid: global.mcpProcess.pid });
    }

    // ── MCP stop ──────────────────────────────────────────────────────────
    if (action === 'stop') {
      if (global.mcpProcess) {
        global.mcpProcess.kill();
        global.mcpProcess = undefined;
        return NextResponse.json({ status: 'stopped' });
      }
      return NextResponse.json({ status: 'not_running' });
    }

    // ── MCP status ────────────────────────────────────────────────────────
    if (action === 'status') {
      const isRunning =
        (global.mcpProcess?.exitCode === null && !global.mcpProcess.killed) ||
        (await isMcpPortReachable(port));
      return NextResponse.json({ status: isRunning ? 'running' : 'stopped' });
    }

    // ── llama.cpp start ───────────────────────────────────────────────────
    if (action === 'start_llamacpp') {
      if (global.llamacppProcess?.exitCode === null && !global.llamacppProcess.killed) {
        return NextResponse.json({ status: 'running', message: 'llama.cpp already running', pid: global.llamacppProcess.pid });
      }

      const llamacppPort = Number(envConfig.LLAMACPP_PORT || '8080');
      const llamacppHost = envConfig.LLAMACPP_HOST || '127.0.0.1';

      if (await isPortOpen(llamacppPort, llamacppHost)) {
        return NextResponse.json({ status: 'running', message: `llama.cpp already on port ${llamacppPort}` });
      }

      const [exe, ...args] = buildLlamacppArgs(envConfig);
      global.llamacppProcess = spawn(exe, args, {
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
      });

      global.llamacppProcess.stdout?.on('data', (d) => console.log(`LLAMA STDOUT: ${d}`));
      global.llamacppProcess.stderr?.on('data', (d) => console.error(`LLAMA STDERR: ${d}`));
      global.llamacppProcess.on('error', (e) => console.error('llama.cpp process error:', e));
      global.llamacppProcess.on('close', (c) => console.log(`llama.cpp process exited: ${c}`));

      return NextResponse.json({
        status: 'started',
        pid: global.llamacppProcess.pid,
        url: `http://${llamacppHost}:${llamacppPort}/v1`,
      });
    }

    // ── llama.cpp stop ────────────────────────────────────────────────────
    if (action === 'stop_llamacpp') {
      if (global.llamacppProcess) {
        global.llamacppProcess.kill();
        global.llamacppProcess = undefined;
        return NextResponse.json({ status: 'stopped' });
      }
      return NextResponse.json({ status: 'not_running' });
    }

    // ── llama.cpp status ──────────────────────────────────────────────────
    if (action === 'status_llamacpp') {
      const llamacppPort = Number(envConfig.LLAMACPP_PORT || '8080');
      const llamacppHost = envConfig.LLAMACPP_HOST || '127.0.0.1';
      const managedRunning = global.llamacppProcess?.exitCode === null && !global.llamacppProcess.killed;
      const portOpen = await isPortOpen(llamacppPort, llamacppHost);
      return NextResponse.json({
        status: (managedRunning || portOpen) ? 'running' : 'stopped',
        pid: managedRunning ? global.llamacppProcess!.pid : null,
      });
    }

    return NextResponse.json({ error: 'Unknown action' }, { status: 400 });
  } catch (error) {
    console.error('System Control Error:', error);
    const msg = error instanceof Error ? error.message : 'Failed to control system';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
