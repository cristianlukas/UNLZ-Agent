# Next Steps & Roadmap

Now that the core structure is in place, follow this roadmap to finalize the project for your portfolio.

## Phase 1: Integration (Getting it Running)

- [ ] **Install Dependencies on Local Machine**
      Run `pip install -r requirements.txt` in this directory.

- [ ] **Connect UNLZ Studio to the Web**
      Your n8n instance (if running in Docker or cloud) cannot see `localhost:5000` directly.
  - Install [Cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/).
  - Run: `cloudflared tunnel --url http://localhost:5000`
  - Save the generated URL (e.g., `https://random-name.trycloudflare.com`).

- [ ] **Configure n8n**
  - Import `n8n_workflow.json` into your n8n instance.
  - Update the "Local LLM" node with your Cloudflare URL.
  - Set up the Supabase credentials in n8n.

- [ ] **Test the Loop**
  - Trigger the n8n workflow manually.
  - Verify it correctly calls the `get_system_stats` tool from your running `mcp_server.py`.

## Phase 2: Technical Enhancements (The "Senior" Features)

- [ ] **Real GPU Monitoring**
      Currently `mcp_server.py` uses simulated data for `gpu_stats`.
  - **Action**: Modify `get_system_stats` to use `shutil.which('nvidia-smi')` and run the command to get real VRAM usage.
  - _Why_: Shows you can handle real hardware interop.

- [ ] **Implement Vector Storage (RAG)**
  - **Action**: Create a Python script (or n8n workflow) that:
    1. Reads PDFs from `UNLZ-AI-STUDIO/system/data`.
    2. Chunks them.
    3. Generates embeddings (use Qwen or a small embedding model).
    4. Upserts them to Supabase `vector` table.
  - _Why_: Essential for the "Research" part of the agent.

- [ ] **Add "Search" Tool**
  - **Action**: Add a new tool to `mcp_server.py` called `search_local_files(query: str)`.
  - It should filter the file list or grep contents to find relevant files before reading them.

## Phase 3: Portfolio Polish (The Presentation)

- [ ] **Record a Demo Video**
  - Screen record a full flow:
    1. You asking: "How is the server load?" -> Agent checks MCP -> Returns real stats.
    2. You asking: "Summarize the research on X" -> Agent checks Supabase -> Returns answer.
  - Upload to YouTube/Loom and embed in `README.md`.

- [ ] **Architecture Diagram**
  - Ensure the Mermaid diagram in `README.md` matches your final setup (e.g., if you added Cloudflare).

- [ ] **Push to GitHub**
  - `git push origin master`
