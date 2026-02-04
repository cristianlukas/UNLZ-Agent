import { NextResponse } from 'next/server';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';

// Use global to persist process across hot-reloads in dev
declare global {
  var mcpProcess: ChildProcess | undefined;
}

const SERVER_SCRIPT = path.join(process.cwd(), '..', 'mcp_server.py');

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

    if (action === 'start') {
      // Check if process exists AND hasn't exited
      if (global.mcpProcess && global.mcpProcess.exitCode === null && !global.mcpProcess.killed) {
        return NextResponse.json({ status: 'running', message: 'Server already running' });
      }

      // Try to determine python command
      const pythonCommand = process.platform === 'win32' ? 'python' : 'python3';
      const port = process.env.MCP_PORT || '8000';
      
      console.log(`Spawning MCP Server with: ${pythonCommand} ${SERVER_SCRIPT} (Port: ${port})`);
      
      global.mcpProcess = spawn(pythonCommand, ['-u', SERVER_SCRIPT], { 
        cwd: path.dirname(SERVER_SCRIPT),
        stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, MCP_PORT: port } 
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
      const isRunning = global.mcpProcess && global.mcpProcess.exitCode === null && !global.mcpProcess.killed;
      return NextResponse.json({ status: isRunning ? 'running' : 'stopped' });
    }

  } catch (error) {
    console.error('System Control Error:', error);
    return NextResponse.json({ error: 'Failed to control system' }, { status: 500 });
  }
}
