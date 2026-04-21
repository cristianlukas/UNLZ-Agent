# Frontend (Legacy Web Mode)

This folder contains the legacy Next.js web UI.

## Status

- Kept for compatibility and migration scenarios.
- Not the primary recommended mode anymore.
- Current primary mode is desktop (`/desktop`) + `agent_server.py`.

## Legacy Stack Overview

- Next.js app (this folder)
- Optional orchestration through n8n webhook
- MCP server integration (`mcp_server.py`) for tools

## Run Legacy Web Mode

From repository root:

```powershell
install.bat
start.bat
```

Or manually:

```powershell
cd frontend
npm install
npm run dev
```

Default URL: [http://localhost:3000](http://localhost:3000)

## Notes

- Several docs in the root now describe desktop mode first.
- If you need the production path, use:
  - `setup-desktop.ps1`
  - `start-desktop.ps1`
