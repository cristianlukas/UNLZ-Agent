import { NextResponse } from 'next/server';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import fs from 'fs';
import net from 'net';

// Use global to persist process across hot-reloads in dev
declare global {
  var mcpProcess: ChildProcess | undefined;
}

const SERVER_SCRIPT = path.join(process.cwd(), '..', 'mcp_server.py');
const PROJECT_ROOT = path.join(process.cwd(), '..');

function isPortOpen(port: number, host: string, timeoutMs: number = 800): Promise<boolean> {
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
  if (await isPortOpen(port, '127.0.0.1')) return true;
  return isPortOpen(port, 'localhost');
}

function resolvePythonCommand(): string {
  const fromEnv = process.env.MCP_PYTHON;
  if (fromEnv) return fromEnv;

  const candidates = process.platform === 'win32'
    ? [
        path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe'),
        path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe'),
      ]
    : [
        path.join(PROJECT_ROOT, 'venv', 'bin', 'python'),
        path.join(PROJECT_ROOT, '.venv', 'bin', 'python'),
      ];

  const venvPython = candidates.find((candidate) => fs.existsSync(candidate));
  if (venvPython) return venvPython;

  return process.platform === 'win32' ? 'python' : 'python3';
}

// Graceful Shutdown Hook
// In dev, this might be triggered by rs (restart) or stopping the server
if (process.env.NODE_ENV !== 'production') {
  const cleanup = () => {
    if (global.mcpProcess) {
      console.log('Cleaning up MCP process...');
      global.mcpProcess.kill();
    }
  };
  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);
  process.on('exit', cleanup);
} else {
  // Production cleanup logic if needed
}

export async function POST(req: Request) {
  try {
    const { action } = await req.json();
    const port = Number(process.env.MCP_PORT || '8000');

    if (action === 'start') {
      // Check if process exists AND hasn't exited
      if (global.mcpProcess && global.mcpProcess.exitCode === null && !global.mcpProcess.killed) {
        return NextResponse.json({ status: 'running', message: 'Server already running' });
      }
      if (await isMcpPortReachable(port)) {
        return NextResponse.json({ status: 'running', message: `Server already running on port ${port}` });
      }

      // Prefer the project virtualenv so Python deps (e.g., mcp) are available.
      const pythonCommand = resolvePythonCommand();
      const mcpPort = String(port);
      
      console.log(`Spawning MCP Server with: ${pythonCommand} ${SERVER_SCRIPT} (Port: ${mcpPort})`);
      
      global.mcpProcess = spawn(pythonCommand, ['-u', SERVER_SCRIPT], { 
        cwd: path.dirname(SERVER_SCRIPT),
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, MCP_PORT: mcpPort } 
      });
      
      if (global.mcpProcess.stdout) {
        global.mcpProcess.stdout.on('data', (data) => console.log(`MCP STDOUT: ${data}`));
      }
      if (global.mcpProcess.stderr) {
        global.mcpProcess.stderr.on('data', (data) => console.error(`MCP STDERR: ${data}`));
      }
      
      global.mcpProcess.on('error', (err) => console.error('Failed to start MCP process:', err));
      global.mcpProcess.on('close', (code) => console.log(`MCP process exited with code ${code}`));

      console.log(`MCP Server started with PID: ${global.mcpProcess.pid}`);
      
      return NextResponse.json({ status: 'started', pid: global.mcpProcess.pid });
    }

    if (action === 'stop') {
      if (global.mcpProcess) {
        global.mcpProcess.kill();
        global.mcpProcess = undefined;
        return NextResponse.json({ status: 'stopped' });
      }
      return NextResponse.json({ status: 'not_running' });
    }
    
    // Status Check (Check port 8000 typically better, but pid is okay for local spawn)
    if (action === 'status') {
      const isRunning =
        (global.mcpProcess && global.mcpProcess.exitCode === null && !global.mcpProcess.killed) ||
        (await isMcpPortReachable(port));
      return NextResponse.json({ status: isRunning ? 'running' : 'stopped' });
    }

  } catch (error) {
    console.error('System Control Error:', error);
    return NextResponse.json({ error: 'Failed to control system' }, { status: 500 });
  }
}
