"""
UNLZ Agent — Model Hub catalog.
Curated SOTA GGUF models with hardware-based recommendations.
"""
from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

# ─── Catalog ──────────────────────────────────────────────────────────────────

CATALOG: list[dict[str, Any]] = [
    # ── Qwen 3.6 ─────────────────────────────────────────────────────────────
    {
        "id": "qwen3.6-35b-a3b-unsloth-q4km",
        "family": "qwen3.6",
        "name": "Qwen3.6 35B-A3B",
        "version": "3.6",
        "size_label": "35B-A3B",
        "hf_repo": "unsloth/Qwen3.6-35B-A3B-GGUF",
        "filename": "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 22.5,
        "ram_gb": 48.0,
        "file_gb": 20.5,
        "context": 262144,
        "tier": "ultra",
        "tasks": {"chat": 93, "code": 94, "reasoning": 94, "instruct": 92},
        "license": "Apache 2.0",
        "release": "2026-04",
        "recommended_for": ["ultra"],
        "badge": "new",
    },
    # ── Qwen 3 ────────────────────────────────────────────────────────────────
    {
        "id": "qwen3-0.6b-q4km",
        "family": "qwen3",
        "name": "Qwen3 0.6B",
        "version": "3.0",
        "size_label": "0.6B",
        "hf_repo": "bartowski/Qwen3-0.6B-GGUF",
        "filename": "Qwen3-0.6B-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 1.0,
        "ram_gb": 4.0,
        "file_gb": 0.5,
        "context": 32768,
        "tier": "entry",
        "tasks": {"chat": 60, "code": 44, "reasoning": 40, "instruct": 57},
        "license": "Apache 2.0",
        "release": "2025-04",
        "recommended_for": ["entry"],
        "badge": None,
    },
    {
        "id": "qwen3-1.7b-q4km",
        "family": "qwen3",
        "name": "Qwen3 1.7B",
        "version": "3.0",
        "size_label": "1.7B",
        "hf_repo": "bartowski/Qwen3-1.7B-GGUF",
        "filename": "Qwen3-1.7B-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 1.5,
        "ram_gb": 6.0,
        "file_gb": 1.1,
        "context": 32768,
        "tier": "entry",
        "tasks": {"chat": 70, "code": 57, "reasoning": 52, "instruct": 67},
        "license": "Apache 2.0",
        "release": "2025-04",
        "recommended_for": ["entry"],
        "badge": None,
    },
    {
        "id": "qwen3-4b-q4km",
        "family": "qwen3",
        "name": "Qwen3 4B",
        "version": "3.0",
        "size_label": "4B",
        "hf_repo": "bartowski/Qwen3-4B-GGUF",
        "filename": "Qwen3-4B-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 3.0,
        "ram_gb": 8.0,
        "file_gb": 2.5,
        "context": 32768,
        "tier": "entry",
        "tasks": {"chat": 78, "code": 70, "reasoning": 65, "instruct": 76},
        "license": "Apache 2.0",
        "release": "2025-04",
        "recommended_for": ["entry", "mid"],
        "badge": "popular",
    },
    {
        "id": "qwen3-8b-q4km",
        "family": "qwen3",
        "name": "Qwen3 8B",
        "version": "3.0",
        "size_label": "8B",
        "hf_repo": "bartowski/Qwen3-8B-GGUF",
        "filename": "Qwen3-8B-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 5.5,
        "ram_gb": 12.0,
        "file_gb": 5.2,
        "context": 131072,
        "tier": "mid",
        "tasks": {"chat": 84, "code": 80, "reasoning": 79, "instruct": 83},
        "license": "Apache 2.0",
        "release": "2025-04",
        "recommended_for": ["mid"],
        "badge": "recommended",
    },
    {
        "id": "qwen3-14b-q4km",
        "family": "qwen3",
        "name": "Qwen3 14B",
        "version": "3.0",
        "size_label": "14B",
        "hf_repo": "bartowski/Qwen3-14B-GGUF",
        "filename": "Qwen3-14B-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 9.5,
        "ram_gb": 20.0,
        "file_gb": 9.0,
        "context": 131072,
        "tier": "high",
        "tasks": {"chat": 88, "code": 85, "reasoning": 84, "instruct": 87},
        "license": "Apache 2.0",
        "release": "2025-04",
        "recommended_for": ["high"],
        "badge": None,
    },
    {
        "id": "qwen3-30b-a3b-q4km",
        "family": "qwen3",
        "name": "Qwen3 30B-A3B",
        "version": "3.0",
        "size_label": "30B-A3B",
        "hf_repo": "bartowski/Qwen3-30B-A3B-GGUF",
        "filename": "Qwen3-30B-A3B-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 18.0,
        "ram_gb": 40.0,
        "file_gb": 18.5,
        "context": 131072,
        "tier": "ultra",
        "tasks": {"chat": 90, "code": 88, "reasoning": 91, "instruct": 89},
        "license": "Apache 2.0",
        "release": "2025-04",
        "recommended_for": ["ultra"],
        "badge": "new",
    },
    {
        "id": "qwen3-32b-q4km",
        "family": "qwen3",
        "name": "Qwen3 32B",
        "version": "3.0",
        "size_label": "32B",
        "hf_repo": "bartowski/Qwen3-32B-GGUF",
        "filename": "Qwen3-32B-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 20.0,
        "ram_gb": 48.0,
        "file_gb": 19.8,
        "context": 131072,
        "tier": "ultra",
        "tasks": {"chat": 91, "code": 89, "reasoning": 91, "instruct": 90},
        "license": "Apache 2.0",
        "release": "2025-04",
        "recommended_for": ["ultra"],
        "badge": "new",
    },
    # ── Gemma 3 ───────────────────────────────────────────────────────────────
    {
        "id": "gemma3-4b-q4km",
        "family": "gemma3",
        "name": "Gemma 3 4B",
        "version": "3.0",
        "size_label": "4B",
        "hf_repo": "bartowski/gemma-3-4b-it-GGUF",
        "filename": "gemma-3-4b-it-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 3.0,
        "ram_gb": 8.0,
        "file_gb": 2.6,
        "context": 128000,
        "tier": "entry",
        "tasks": {"chat": 77, "code": 65, "reasoning": 68, "instruct": 75},
        "license": "Gemma ToS",
        "release": "2025-03",
        "recommended_for": ["entry", "mid"],
        "badge": None,
    },
    {
        "id": "gemma3-12b-q4km",
        "family": "gemma3",
        "name": "Gemma 3 12B",
        "version": "3.0",
        "size_label": "12B",
        "hf_repo": "bartowski/gemma-3-12b-it-GGUF",
        "filename": "gemma-3-12b-it-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 8.0,
        "ram_gb": 20.0,
        "file_gb": 7.6,
        "context": 128000,
        "tier": "mid",
        "tasks": {"chat": 83, "code": 76, "reasoning": 78, "instruct": 82},
        "license": "Gemma ToS",
        "release": "2025-03",
        "recommended_for": ["mid", "high"],
        "badge": None,
    },
    {
        "id": "gemma3-27b-q4km",
        "family": "gemma3",
        "name": "Gemma 3 27B",
        "version": "3.0",
        "size_label": "27B",
        "hf_repo": "bartowski/gemma-3-27b-it-GGUF",
        "filename": "gemma-3-27b-it-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 17.0,
        "ram_gb": 40.0,
        "file_gb": 16.8,
        "context": 128000,
        "tier": "ultra",
        "tasks": {"chat": 88, "code": 82, "reasoning": 84, "instruct": 87},
        "license": "Gemma ToS",
        "release": "2025-03",
        "recommended_for": ["ultra"],
        "badge": None,
    },
    # ── Gemma 4 ───────────────────────────────────────────────────────────────
    {
        "id": "gemma4-31b-it-q4km",
        "family": "gemma4",
        "name": "Gemma 4 31B",
        "version": "4.0",
        "size_label": "31B",
        "hf_repo": "bartowski/gemma-4-31b-it-GGUF",
        "filename": "gemma-4-31b-it-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 22.0,
        "ram_gb": 48.0,
        "file_gb": 20.8,
        "context": 131072,
        "tier": "ultra",
        "tasks": {"chat": 94, "code": 88, "reasoning": 90, "instruct": 93},
        "license": "Gemma ToS",
        "release": "2026-04",
        "recommended_for": ["ultra"],
        "badge": "new",
    },
    # ── Llama 3.2 ─────────────────────────────────────────────────────────────
    {
        "id": "llama32-1b-q4km",
        "family": "llama3",
        "name": "Llama 3.2 1B",
        "version": "3.2",
        "size_label": "1B",
        "hf_repo": "bartowski/Llama-3.2-1B-Instruct-GGUF",
        "filename": "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 1.0,
        "ram_gb": 4.0,
        "file_gb": 0.8,
        "context": 131072,
        "tier": "entry",
        "tasks": {"chat": 60, "code": 42, "reasoning": 38, "instruct": 57},
        "license": "Llama 3.2",
        "release": "2024-09",
        "recommended_for": ["entry"],
        "badge": None,
    },
    {
        "id": "llama32-3b-q4km",
        "family": "llama3",
        "name": "Llama 3.2 3B",
        "version": "3.2",
        "size_label": "3B",
        "hf_repo": "bartowski/Llama-3.2-3B-Instruct-GGUF",
        "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 2.5,
        "ram_gb": 6.0,
        "file_gb": 2.0,
        "context": 131072,
        "tier": "entry",
        "tasks": {"chat": 68, "code": 56, "reasoning": 50, "instruct": 65},
        "license": "Llama 3.2",
        "release": "2024-09",
        "recommended_for": ["entry"],
        "badge": None,
    },
    # ── Mistral ───────────────────────────────────────────────────────────────
    {
        "id": "mistral-7b-v03-q4km",
        "family": "mistral",
        "name": "Mistral 7B v0.3",
        "version": "0.3",
        "size_label": "7B",
        "hf_repo": "bartowski/Mistral-7B-Instruct-v0.3-GGUF",
        "filename": "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 4.5,
        "ram_gb": 10.0,
        "file_gb": 4.4,
        "context": 32768,
        "tier": "mid",
        "tasks": {"chat": 75, "code": 68, "reasoning": 64, "instruct": 74},
        "license": "Apache 2.0",
        "release": "2024-05",
        "recommended_for": ["mid"],
        "badge": None,
    },
    # ── DeepSeek R1 distills ──────────────────────────────────────────────────
    {
        "id": "deepseek-r1-7b-q4km",
        "family": "deepseek-r1",
        "name": "DeepSeek-R1 7B",
        "version": "R1",
        "size_label": "7B",
        "hf_repo": "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF",
        "filename": "DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 5.0,
        "ram_gb": 12.0,
        "file_gb": 4.8,
        "context": 131072,
        "tier": "mid",
        "tasks": {"chat": 76, "code": 78, "reasoning": 91, "instruct": 72},
        "license": "MIT",
        "release": "2025-01",
        "recommended_for": ["mid"],
        "badge": None,
    },
    {
        "id": "deepseek-r1-14b-q4km",
        "family": "deepseek-r1",
        "name": "DeepSeek-R1 14B",
        "version": "R1",
        "size_label": "14B",
        "hf_repo": "bartowski/DeepSeek-R1-Distill-Qwen-14B-GGUF",
        "filename": "DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf",
        "quant": "Q4_K_M",
        "vram_gb": 9.5,
        "ram_gb": 20.0,
        "file_gb": 9.0,
        "context": 131072,
        "tier": "high",
        "tasks": {"chat": 80, "code": 82, "reasoning": 93, "instruct": 77},
        "license": "MIT",
        "release": "2025-01",
        "recommended_for": ["high"],
        "badge": None,
    },
]

# ── Family upgrade chain ───────────────────────────────────────────────────────
# keyword (lowercased, found in model path or alias) → catalog family
FAMILY_DETECT: dict[str, str] = {
    "qwen3.6": "qwen3.6",
    "qwen-3.6": "qwen3.6",
    "qwen3": "qwen3",
    "qwen2.5": "qwen2.5",
    "qwen2": "qwen2",
    "qwen": "qwen",
    "gemma-4": "gemma4",
    "gemma4": "gemma4",
    "gemma-3": "gemma3",
    "gemma3": "gemma3",
    "gemma-2": "gemma2",
    "gemma2": "gemma2",
    "gemma": "gemma",
    "llama-3.2": "llama3",
    "llama-3.1": "llama3",
    "llama3": "llama3",
    "llama": "llama3",
    "mistral": "mistral",
    "deepseek-r1": "deepseek-r1",
    "deepseek": "deepseek-r1",
}

FAMILY_UPGRADES: dict[str, str] = {
    "qwen3": "qwen3.6",
    "qwen2.5": "qwen3",
    "qwen2": "qwen3",
    "qwen": "qwen3",
    "gemma2": "gemma3",
    "gemma": "gemma3",
    "gemma3": "gemma4",
    "llama3": "llama3",  # internal — no upgrade yet
}


# ─── Hardware classifier ───────────────────────────────────────────────────────

def classify_hardware(vram_gb: float, ram_gb: float) -> str:
    """Return 'entry' | 'mid' | 'high' | 'ultra' based on available VRAM (or RAM)."""
    if vram_gb >= 16:
        return "ultra"
    elif vram_gb >= 8:
        return "high"
    elif vram_gb >= 4:
        return "mid"
    elif vram_gb > 0:
        return "entry"
    # CPU-only path — use RAM heuristic
    if ram_gb >= 64:
        return "ultra"
    elif ram_gb >= 32:
        return "high"
    elif ram_gb >= 16:
        return "mid"
    return "entry"


def _avg_score(m: dict) -> float:
    t = m["tasks"]
    return (t["chat"] + t["code"] + t["reasoning"] + t["instruct"]) / 4.0


def get_recommendations(vram_gb: float, ram_gb: float, catalog: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return ideal/balanced/fast models for the given hardware."""
    models = catalog if catalog is not None else CATALOG
    vram_headroom = float(os.getenv("HUB_VRAM_HEADROOM_RATIO", "0.95"))
    vram_headroom = max(0.75, min(vram_headroom, 1.05))

    def fits(m: dict) -> bool:
        if vram_gb > 0:
            return m["vram_gb"] <= vram_gb * vram_headroom
        return m["ram_gb"] <= ram_gb * 0.70

    candidates = [m for m in models if fits(m)]
    if not candidates:
        candidates = sorted(models, key=lambda x: x["vram_gb"])[:3]

    by_score = sorted(candidates, key=_avg_score, reverse=True)
    by_size = sorted(candidates, key=lambda x: x["file_gb"])

    ideal = by_score[0] if by_score else None
    balanced = by_score[len(by_score) // 2] if len(by_score) > 1 else ideal
    fast = by_size[0] if by_size else ideal

    return {
        "tier": classify_hardware(vram_gb, ram_gb),
        "ideal": ideal,
        "balanced": balanced,
        "fast": fast,
        "all_fitting": by_score,
    }


# ─── Update detector ──────────────────────────────────────────────────────────

def check_for_update(
    current_model_path: str,
    current_alias: str,
    catalog: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    Return update/upgrade info if available, else None.
    Checks current model name against catalog for same-family upgrades.
    """
    combined = (current_model_path + " " + current_alias).lower().replace("\\", "/")
    if not combined.strip():
        return None

    # Detect current family
    current_family: str | None = None
    for kw, family in FAMILY_DETECT.items():
        if kw in combined:
            current_family = family
            break

    if not current_family:
        return None

    models = catalog if catalog is not None else CATALOG

    # Is current model already in catalog?
    current_entry: dict | None = None
    for m in models:
        fname = m["filename"].lower()
        mid = m["id"].lower()
        if fname in combined or mid in combined:
            current_entry = m
            break

    # Check if there's a newer family available
    upgrade_family = FAMILY_UPGRADES.get(current_family)
    if upgrade_family and upgrade_family != current_family:
        upgrade_models = [m for m in models if m["family"] == upgrade_family]
        if upgrade_models:
            best = max(upgrade_models, key=_avg_score)
            return {
                "type": "family_upgrade",
                "current_family": current_family,
                "new_family": upgrade_family,
                "recommended": best,
                "message": f"Nueva familia disponible: {best['name']}",
            }

    # Current model in catalog — suggest best in same family if it's not already the best
    family_models = [m for m in models if m["family"] == current_family]
    if family_models and current_entry:
        best = max(family_models, key=_avg_score)
        if best["id"] != current_entry["id"] and _avg_score(best) > _avg_score(current_entry) + 3:
            return {
                "type": "same_family_upgrade",
                "current_family": current_family,
                "current_entry": current_entry,
                "recommended": best,
                "message": f"Versión mejorada disponible: {best['name']}",
            }
        return None

    # Model not in catalog but family is known — suggest catalog entry
    if family_models:
        best = max(family_models, key=_avg_score)
        return {
            "type": "catalog_suggestion",
            "current_family": current_family,
            "recommended": best,
            "message": f"Modelo optimizado disponible: {best['name']}",
        }

    return None


# ─── Online catalog enrichment (multi-source) ───────────────────────────────

_ONLINE_CACHE_TTL_SEC = int(os.getenv("HUB_ONLINE_CACHE_TTL_SEC", "900"))
_ONLINE_CACHE: dict[str, Any] = {"ts": 0.0, "catalog": None, "meta": None}


def _http_json(url: str, timeout: float = 6.0) -> Any:
    req = Request(url, headers={"User-Agent": "UNLZ-Agent/2.0", "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _extract_size_label(text: str) -> str | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(b|B)(?:[-_ ]?(A\d+B))?", text)
    if not m:
        return None
    base = f"{m.group(1)}B"
    moe = m.group(3)
    return f"{base}-{moe}" if moe else base


def _fetch_huggingface_hints() -> dict[str, Any]:
    queries = ["Qwen3.6 GGUF", "Gemma 4 GGUF", "Qwen3.6-35B-A3B-GGUF"]
    found_ids: list[str] = []
    last_modified: dict[str, str] = {}
    for q in queries:
        try:
            url = f"https://huggingface.co/api/models?search={quote(q)}&limit=20&sort=lastModified&direction=-1"
            data = _http_json(url, timeout=5.0) or []
            if not isinstance(data, list):
                continue
            for item in data:
                mid = str(item.get("id") or "").strip()
                if not mid:
                    continue
                mid_l = mid.lower()
                if ("qwen3.6" in mid_l or "gemma-4" in mid_l or "gemma4" in mid_l) and "gguf" in mid_l:
                    found_ids.append(mid)
                    lm = str(item.get("lastModified") or "")
                    if lm:
                        last_modified[mid] = lm
        except Exception:
            continue
    return {"source": "huggingface", "found_ids": sorted(set(found_ids)), "last_modified": last_modified}


def _fetch_openrouter_hints() -> dict[str, Any]:
    found_ids: list[str] = []
    try:
        data = _http_json("https://openrouter.ai/api/v1/models", timeout=5.0) or {}
        rows = data.get("data") if isinstance(data, dict) else []
        if isinstance(rows, list):
            for r in rows:
                mid = str(r.get("id") or "").strip()
                if not mid:
                    continue
                ml = mid.lower()
                if "qwen3.6" in ml or "gemma-4" in ml or "gemma4" in ml:
                    found_ids.append(mid)
    except Exception:
        pass
    return {"source": "openrouter", "found_ids": sorted(set(found_ids))}


def _merge_online_hints(base_catalog: list[dict[str, Any]], hints: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    catalog = deepcopy(base_catalog)
    meta: dict[str, Any] = {"sources": hints, "applied": []}

    hf_ids: list[str] = []
    for h in hints:
        if h.get("source") == "huggingface":
            hf_ids.extend(h.get("found_ids") or [])
    hf_join = " ".join(x.lower() for x in hf_ids)

    # If online sources report Qwen 3.6 and catalog lacks it, inject a sane default entry.
    has_qwen36 = any((m.get("family") == "qwen3.6") for m in catalog)
    if ("qwen3.6" in hf_join) and not has_qwen36:
        catalog.insert(0, {
            "id": "qwen3.6-35b-a3b-q4km-auto",
            "family": "qwen3.6",
            "name": "Qwen3.6 35B-A3B",
            "version": "3.6",
            "size_label": "35B-A3B",
            "hf_repo": "unsloth/Qwen3.6-35B-A3B-GGUF",
            "filename": "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
            "quant": "Q4_K_M",
            "vram_gb": 22.5,
            "ram_gb": 48.0,
            "file_gb": 20.5,
            "context": 262144,
            "tier": "ultra",
            "tasks": {"chat": 93, "code": 94, "reasoning": 94, "instruct": 92},
            "license": "Apache 2.0",
            "release": "2026-04",
            "recommended_for": ["ultra"],
            "badge": "new",
        })
        meta["applied"].append("inject_qwen3.6")

    # If online sources report Gemma 4 heavily, boost discoverability for Gemma 4 entries.
    if ("gemma-4" in hf_join or "gemma4" in hf_join):
        for m in catalog:
            if m.get("family") == "gemma4" and "31b" in str(m.get("size_label", "")).lower():
                if m.get("badge") is None:
                    m["badge"] = "recommended"
                    meta["applied"].append(f"badge_boost:{m.get('id')}")
                break

    return catalog, meta


def get_runtime_catalog() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Build runtime catalog from static + online hints from multiple sources.
    Safe fallback: static catalog if network fails.
    """
    now = time.time()
    if (
        _ONLINE_CACHE.get("catalog") is not None
        and (now - float(_ONLINE_CACHE.get("ts") or 0.0)) < _ONLINE_CACHE_TTL_SEC
    ):
        return deepcopy(_ONLINE_CACHE["catalog"]), deepcopy(_ONLINE_CACHE["meta"] or {})

    hints = [
        _fetch_huggingface_hints(),
        _fetch_openrouter_hints(),
    ]
    merged, meta = _merge_online_hints(CATALOG, hints)
    _ONLINE_CACHE["ts"] = now
    _ONLINE_CACHE["catalog"] = deepcopy(merged)
    _ONLINE_CACHE["meta"] = deepcopy(meta)
    return merged, meta
