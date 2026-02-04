import { NextResponse } from 'next/server';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';

// Use global to persist process across hot-reloads in dev
declare global {
  var mcpProcess: ChildProcess | undefined;
}

const SERVER_SCRIPT = path.join(process.cwd(), '..', 'mcp_server.py');

export async function POST(req: Request) {
  try {
    const { action } = await req.json();

    if (action === 'start') {
      if (global.mcpProcess && !global.mcpProcess.killed) {
        return NextResponse.json({ status: 'running', message: 'Server already running' });
      }

      console.log('Spawning MCP Server:', SERVER_SCRIPT);
      // Spawn python process
      // Ensure python is in path or use specific path
      global.mcpProcess = spawn('python', ['-u', SERVER_SCRIPT], { // -u for unbuffered output
        cwd: path.dirname(SERVER_SCRIPT),
        stdio: 'ignore' // or 'pipe' to log to file
      });
      
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
      const isRunning = global.mcpProcess && !global.mcpProcess.killed;
      return NextResponse.json({ status: isRunning ? 'running' : 'stopped' });
    }

  } catch (error) {
    console.error('System Control Error:', error);
    return NextResponse.json({ error: 'Failed to control system' }, { status: 500 });
  }
}
