# ADR 0004: Model Hub

## Status
Accepted

## Context
Local LLM users face three friction points:
1. Finding a model that fits their hardware (VRAM/RAM constraints)
2. Downloading the right GGUF quant from HuggingFace manually
3. Knowing when a better model is available

An in-app model hub removes all three friction points without requiring external tooling.

## Decision
Implement a Model Hub feature comprising:

**Hardware profiler (`hub_catalog.py`)**
- `classify_hardware(vram_gb, ram_gb)` → `entry|mid|high|ultra` tier
- `get_recommendations()` → tier-matched ideal/balanced/fast candidates

**Curated catalog**
- Static catalog of 14+ GGUF models (Qwen3, Gemma3, Llama 3.2, Mistral, DeepSeek-R1)
- Each model: task scores (chat/code/reasoning/instruct 0–100), hardware requirements, tier, HuggingFace repo + filename

**Update detector**
- `check_for_update(current_path, current_alias)` detects same-family and cross-family upgrades
- `FAMILY_DETECT` dict sorted by specificity for accurate family identification
- `FAMILY_UPGRADES` dict maps old families to recommended new families

**Download pipeline**
- `POST /hub/download` starts background thread using stdlib `urllib.request` (no new dependencies)
- Downloads to `<dest>.part` for atomic rename on completion
- SSE progress stream with speed/ETA tracking
- Cancel support with partial file cleanup

**Apply flow**
- `POST /hub/apply/{id}` writes `LLAMACPP_MODEL_PATH` + `LLAMACPP_MODEL_ALIAS` to `.env` and restarts llama.cpp

**UI**
- Hardware banner + update notification banner with skip/snooze (persisted in Zustand)
- Amber dot badge on sidebar nav item when update is available

## Consequences
- Users can go from "no model" to running in ~3 clicks with hardware-appropriate defaults.
- No pip dependencies added — download uses stdlib only.
- Catalog is static; requires manual updates when new models are released.
- Skip/snooze preferences survive app restarts via Zustand persist.
