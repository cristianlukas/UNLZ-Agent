"""
UNLZ Agent Server — opencode-only harness.
FastAPI + SSE streaming via opencode subprocess.
"""
from __future__ import annotations

import asyncio
import hashlib
import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen


# ── Redirect stdout/stderr to log when not running in a real terminal ─────────

def _bootstrap_runtime_root() -> str:
    """Resolve the project root directory.

    Checks UNLZ_PROJECT_ROOT env var first, then handles PyInstaller frozen
    executables, and falls back to the script directory.

    Returns:
        Absolute path to the project root as a string.
    """
    override = (os.getenv("UNLZ_PROJECT_ROOT") or "").strip()
    if override:
        return override
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name.lower() == "binaries":
            return str(exe_dir.parent)
        return str(exe_dir)
    return os.path.dirname(os.path.abspath(__file__))


def _bootstrap_log_path() -> str:
    """Return the absolute path to the agent server log file.

    Returns:
        Path to agent_server.log inside the runtime root.
    """
    return os.path.join(_bootstrap_runtime_root(), "agent_server.log")


def _install_stdio_file_log() -> None:
    """Redirect stdout/stderr to a log file when not running in a real terminal.

    Used when launched from Tauri (CREATE_NO_WINDOW) or background processes.
    Tries primary log path first, then temp directory as fallback.

    Raises:
        No exceptions — failures are silently ignored.
    """
    force_log = os.getenv("UNLZ_FORCE_LOG_FILE", "0").strip().lower() in ("1", "true", "yes")
    try:
        is_tty = os.isatty(sys.stdout.fileno())
    except (AttributeError, OSError):
        is_tty = False
    if not (force_log or not is_tty):
        return
    candidates = [
        _bootstrap_log_path(),
        os.path.join(tempfile.gettempdir(), "unlz-agent", "agent_server.log"),
    ]
    for path in candidates:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            log_fh = open(path, "a", encoding="utf-8", buffering=1)
            sys.stdout = log_fh
            sys.stderr = log_fh
            return
        except Exception:
            continue


_install_stdio_file_log()

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent))


def _runtime_root_dir() -> Path:
    """Resolve the project root directory as a Path object.

    Same logic as _bootstrap_runtime_root but returns Path instead of str.
    Used after imports when Path is preferred over string paths.

    Returns:
        Path object pointing to the project root directory.
    """
    override = (os.getenv("UNLZ_PROJECT_ROOT") or "").strip()
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name.lower() == "binaries":
            return exe_dir.parent
        return exe_dir
    return Path(__file__).parent


load_dotenv(dotenv_path=_runtime_root_dir() / ".env")

from config import Config
from opencode_1_catalog import load_opencode_1_profiles
from guardrails.validator import explain_error_for_humans


# ── Env helpers ───────────────────────────────────────────────────────────────

def _env_path() -> Path:
    """Return the path to the .env file.

    Returns:
        Path to .env inside the runtime root.
    """
    return _runtime_root_dir() / ".env"


def _reload_config_runtime() -> None:
    """Reload critical config values from .env without restarting the server.

    Updates AGENT_LANGUAGE, AGENT_EXECUTION_MODE, and HARNESS_OPENCODE_BIN
    in the Config class to reflect changes made to .env at runtime.
    """
    load_dotenv(dotenv_path=_env_path(), override=True)
    Config.AGENT_LANGUAGE = os.getenv("AGENT_LANGUAGE", "es").lower()
    Config.AGENT_EXECUTION_MODE = os.getenv("AGENT_EXECUTION_MODE", "autonomous").lower()
    Config.HARNESS_OPENCODE_BIN = os.getenv("HARNESS_OPENCODE_BIN", "")


def _upsert_env_settings(payload: dict) -> None:
    """Write key-value pairs to .env file and reload runtime config.

    Only processes keys that are uppercase (SCREAMING_SNAKE_CASE).
    Existing keys are updated in place; new keys are appended.
    Calls _reload_config_runtime() after writing.

    Args:
        payload: Dict of env var names to values.

    Raises:
        IOError: If .env file cannot be written.
    """
    env_path = _env_path()
    content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    for key, value in payload.items():
        if key != key.upper():
            continue
        pattern = re.compile(f"^{re.escape(key)}=.*", re.MULTILINE)
        line = f"{key}={value}"
        content = pattern.sub(lambda _: line, content) if pattern.search(content) else (content + f"\n{line}")
    env_path.write_text(content.strip() + "\n", encoding="utf-8")
    _reload_config_runtime()


_LOCKED_ENV_KEYS = {
    "AGENT_HARNESS",
    "AGENT_EXECUTION_MODE",
    "LLM_PROVIDER",
    "LLAMACPP_EXECUTABLE",
    "LLAMACPP_MODEL_PATH",
    "LLAMACPP_MODEL_ALIAS",
}


def _select_bundled_llama_server() -> str:
    """Find the bundled llama-server executable.

    Searches in priority order:
    1. tools/llama.cpp/opencode-mtp/llama-server.exe
    2. llama.cpp/llama-server.exe
    3. llama.cpp/b*/llama-server.exe (latest build directory)

    Returns:
        Absolute path to the executable, or empty string if not found.
    """
    root = _runtime_root_dir()
    opencode_mtp = root / "tools" / "llama.cpp" / "opencode-mtp" / "llama-server.exe"
    if opencode_mtp.exists():
        return str(opencode_mtp)
    explicit = root / "llama.cpp" / "llama-server.exe"
    if explicit.exists():
        return str(explicit)

    llroot = root / "llama.cpp"
    if not llroot.exists():
        return ""
    cands = sorted([p for p in llroot.glob("b*/llama-server.exe") if p.exists()], reverse=True)
    return str(cands[0]) if cands else ""


def _detect_hardware_tier() -> tuple[str, float, float]:
    """Detect system hardware capabilities.

    Queries RAM via psutil and VRAM via nvidia-smi (Windows).
    Classifies the system into a tier based on available memory.

    Returns:
        Tuple of (tier, vram_gb, ram_gb) where tier is one of:
        'ultra' (VRAM>=20 or RAM>=64), 'high' (VRAM>=12 or RAM>=32),
        'mid' (VRAM>=8 or RAM>=16), or 'entry' (everything else).
    """
    ram_gb = 0.0
    vram_gb = 0.0
    try:
        import psutil
        ram_gb = float(psutil.virtual_memory().total) / (1024 ** 3)
    except Exception:
        pass
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if proc.returncode == 0:
            vals = [float(x.strip()) / 1024.0 for x in (proc.stdout or "").splitlines() if x.strip()]
            if vals:
                vram_gb = max(vals)
    except Exception:
        pass

    if vram_gb >= 20 or ram_gb >= 64:
        return ("ultra", vram_gb, ram_gb)
    if vram_gb >= 12 or ram_gb >= 32:
        return ("high", vram_gb, ram_gb)
    if vram_gb >= 8 or ram_gb >= 16:
        return ("mid", vram_gb, ram_gb)
    return ("entry", vram_gb, ram_gb)


def _hardware_bucket(vram_gb: float) -> str:
    """Map VRAM amount to a hardware bucket key.

    Buckets correspond to entries in the hardware plan dict.

    Args:
        vram_gb: Available GPU VRAM in gigabytes.

    Returns:
        Bucket key: 'cpu', 'gpu_4', 'gpu_8', 'gpu_12', 'gpu_16', 'gpu_24', or 'gpu_32'.
    """
    if vram_gb <= 0:
        return "cpu"
    if vram_gb < 6:
        return "gpu_4"
    if vram_gb < 10:
        return "gpu_8"
    if vram_gb < 14:
        return "gpu_12"
    if vram_gb < 20:
        return "gpu_16"
    if vram_gb < 28:
        return "gpu_24"
    return "gpu_32"


def _default_hardware_plan() -> dict[str, Any]:
    """Return the default hardware-to-model mapping plan.

    Maps each hardware bucket to a recommended GGUF model with download
    info from HuggingFace. Each entry contains profile_name, opencode_model_id,
    model_folder, alias, hf_repo, filename, and optional fallback_candidates.

    Returns:
        Dict keyed by hardware bucket (cpu, gpu_4, gpu_8, etc.) with model specs.
    """
    return {
        "cpu": {
            "profile_name": "1_ GEMMA",
            "opencode_model_id": "gemma-26b-131k",
            "model_folder": "Qwen3.6-4B-GGUF",
            "alias": "qwen3.6-4b-q4km",
            "hf_repo": "unsloth/Qwen3.6-4B-GGUF",
            "filename": "Qwen3.6-4B-Q4_K_M.gguf",
            "fallback_candidates": [],
        },
        "gpu_4": {
            "profile_name": "1_ GEMMA",
            "opencode_model_id": "gemma-26b-131k",
            "model_folder": "Qwen3.6-8B-GGUF",
            "alias": "qwen3.6-8b-q4km",
            "hf_repo": "unsloth/Qwen3.6-8B-GGUF",
            "filename": "Qwen3.6-8B-Q4_K_M.gguf",
            "fallback_candidates": [],
        },
        "gpu_8": {
            "profile_name": "1_ GEMMA",
            "opencode_model_id": "gemma-26b-131k",
            "model_folder": "Qwen3.6-14B-GGUF",
            "alias": "qwen3.6-14b-q4km",
            "hf_repo": "unsloth/Qwen3.6-14B-GGUF",
            "filename": "Qwen3.6-14B-Q4_K_M.gguf",
            "fallback_candidates": [],
        },
        "gpu_12": {
            "profile_name": "1_ QWEN MTP XS",
            "opencode_model_id": "ideal-mtp-xs-131k",
            "model_folder": "Qwen3.6-27B-MTP-IQ4_XS-GGUF",
            "alias": "ideal-mtp-xs-131k",
            "hf_repo": "froggeric/Qwen3.6-27B-MTP-GGUF",
            "filename": "Qwen3.6-27B-MTP-IQ4_XS.gguf",
            "fallback_candidates": [
                {
                    "model_folder": "Qwen3.6-27B-GGUF",
                    "alias": "qwen3.6-27b-q4km",
                    "hf_repo": "bartowski/Qwen_Qwen3.6-27B-GGUF",
                    "filename": "Qwen_Qwen3.6-27B-Q4_K_M.gguf",
                }
            ],
        },
        "gpu_16": {
            "profile_name": "1_ QWEN MTP KM",
            "opencode_model_id": "ideal-mtp-km-131k",
            "model_folder": "Qwen3.6-27B-MTP-Q4_K_M-GGUF",
            "alias": "ideal-mtp-km-131k",
            "hf_repo": "RDson/Qwen3.6-27B-MTP-Q4_K_M-GGUF",
            "filename": "Qwen3.6-27B-MTP-Q4_K_M.gguf",
            "fallback_candidates": [
                {
                    "model_folder": "Qwen3.6-27B-GGUF",
                    "alias": "qwen3.6-27b-q4km",
                    "hf_repo": "bartowski/Qwen_Qwen3.6-27B-GGUF",
                    "filename": "Qwen_Qwen3.6-27B-Q4_K_M.gguf",
                }
            ],
        },
        "gpu_24": {
            "profile_name": "1_ QWEN MTP MOE",
            "opencode_model_id": "ideal-35moe-mtp-131k",
            "model_folder": "Qwen3.6-35B-A3B-MTP-IQ4_XS-GGUF",
            "alias": "ideal-35moe-mtp-131k",
            "hf_repo": "localweights/Qwen3.6-35B-A3B-MTP-IQ4_XS-GGUF",
            "filename": "Qwen3.6-35B-A3B-MTP-IQ4_XS.gguf",
            "require_1_profile": True,
            "fallback_candidates": [
                {
                    "model_folder": "Qwen3.6-35B-A3B-GGUF",
                    "alias": "qwen3.6-35b-a3b-q4km",
                    "hf_repo": "cmp-nct/Qwen3.6-35B-A3B-GGUF",
                    "filename": "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
                }
            ],
        },
        "gpu_32": {
            "profile_name": "1_ QWEN MTP MOE",
            "opencode_model_id": "ideal-35moe-mtp-131k",
            "model_folder": "Qwen3.6-35B-A3B-MTP-IQ4_XS-GGUF",
            "alias": "ideal-35moe-mtp-131k",
            "hf_repo": "localweights/Qwen3.6-35B-A3B-MTP-IQ4_XS-GGUF",
            "filename": "Qwen3.6-35B-A3B-MTP-IQ4_XS.gguf",
            "fallback_candidates": [
                {
                    "model_folder": "Qwen3.6-35B-A3B-GGUF",
                    "alias": "qwen3.6-35b-a3b-q4km",
                    "hf_repo": "cmp-nct/Qwen3.6-35B-A3B-GGUF",
                    "filename": "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
                }
            ],
        },
    }


def _read_hardware_plan() -> dict[str, Any]:
    """Read hardware plan from environment variable or return default.

    Checks UNLZ_HARDWARE_MODEL_PLAN_JSON for a custom JSON plan.
    Falls back to _default_hardware_plan() if env var is empty, invalid JSON,
    or not a dict.

    Returns:
        Dict mapping hardware buckets to model specifications.
    """
    raw = (os.getenv("UNLZ_HARDWARE_MODEL_PLAN_JSON") or "").strip()
    if not raw:
        return _default_hardware_plan()
    try:
        data = json.loads(raw)
    except Exception:
        return _default_hardware_plan()
    if not isinstance(data, dict):
        return _default_hardware_plan()
    return data


def _download_hf_file(hf_repo: str, filename: str, dest: Path) -> None:
    """Download a file from HuggingFace to the destination path.

    Downloads to a .part temp file first, then atomically replaces the
    destination on success. Updates _BOOTSTRAP_STATE with progress info.

    Args:
        hf_repo: HuggingFace repo ID (e.g. 'unsloth/Qwen3.6-4B-GGUF').
        filename: Filename within the repo.
        dest: Destination path for the downloaded file.

    Raises:
        urllib.error.URLError: If download fails or times out (60s).
        IOError: If destination directory cannot be created.
    """
    url = f"https://huggingface.co/{hf_repo}/resolve/main/{filename}"
    req = Request(url, headers={"User-Agent": "UNLZ-Agent/2.0"})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urlopen(req, timeout=60) as resp, tmp.open("wb") as fh:
        total = int(resp.headers.get("Content-Length", "0") or "0")
        done = 0
        t0 = time.time()
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            elapsed = max(time.time() - t0, 0.001)
            speed_mbps = (done / (1024 * 1024)) / elapsed
            progress = (done / total) if total > 0 else 0.0
            _BOOTSTRAP_STATE.update({
                "status": "downloading",
                "progress": round(progress, 4),
                "downloaded_mb": round(done / (1024 * 1024), 1),
                "total_mb": round(total / (1024 * 1024), 1) if total > 0 else None,
                "speed_mbps": round(speed_mbps, 2),
            })
    tmp.replace(dest)


def _sha256_file(path: Path) -> str:
    """Compute SHA256 hash of a file.

    Reads in 1MB chunks for memory efficiency.

    Args:
        path: Path to the file to hash.

    Returns:
        Lowercase hex digest string.

    Raises:
        IOError: If file cannot be read.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _resolve_download_target(selected_plan: dict[str, Any]) -> dict[str, str]:
    """Select the first valid download candidate from a hardware plan entry.

    Checks the primary model first, then fallback_candidates. Returns the
    first candidate that has both hf_repo and filename set.

    Args:
        selected_plan: Hardware plan entry with model_folder, alias, hf_repo,
            filename, and optional fallback_candidates list.

    Returns:
        Dict with keys: model_folder, alias, hf_repo, filename, sha256.

    Raises:
        RuntimeError: If no valid candidate is found.
    """
    primary = {
        "model_folder": str(selected_plan.get("model_folder") or "").strip(),
        "alias": str(selected_plan.get("alias") or "").strip(),
        "hf_repo": str(selected_plan.get("hf_repo") or "").strip(),
        "filename": str(selected_plan.get("filename") or "").strip(),
        "sha256": str(selected_plan.get("sha256") or "").strip().lower(),
    }
    candidates = [primary]
    extra = selected_plan.get("fallback_candidates")
    if isinstance(extra, list):
        for c in extra:
            if not isinstance(c, dict):
                continue
            candidates.append({
                "model_folder": str(c.get("model_folder") or "").strip(),
                "alias": str(c.get("alias") or "").strip(),
                "hf_repo": str(c.get("hf_repo") or "").strip(),
                "filename": str(c.get("filename") or "").strip(),
                "sha256": str(c.get("sha256") or "").strip().lower(),
            })

    last_err = None
    for c in candidates:
        if c["hf_repo"] and c["filename"]:
            return c
        last_err = f"Candidate inválido: {c}"
    raise RuntimeError(last_err or "Sin candidatos de descarga válidos")


_BOOTSTRAP_STATE: dict[str, Any] = {"status": "idle", "detail": ""}
_LLAMA_SERVER_PROC_LOCK = threading.Lock()
_LLAMA_SERVER_PROC: Optional[subprocess.Popen] = None
_OPENCODE_WARMUP_STATE: dict[str, Any] = {
    "status": "idle",
    "detail": "",
    "started_at": "",
    "finished_at": "",
}
_OPENCODE_WARMUP_LOCK = threading.Lock()


def _bootstrap_locked_runtime() -> None:
    """Initialize the runtime: force config, detect hardware, select/download model.

    This is the main bootstrap function called at server startup. It:
    1. Forces AGENT_HARNESS=opencode, LLM_PROVIDER=llamacpp, AGENT_EXECUTION_MODE=autonomous
    2. Detects hardware tier (VRAM/RAM) and maps to hardware bucket
    3. Selects model from hardware plan for the detected bucket
    4. Verifies model exists on disk with SHA256 check
    5. Downloads from HuggingFace if missing or checksum mismatch
    6. Writes LLAMACPP_MODEL_PATH and LLAMACPP_MODEL_ALIAS to .env

    Updates _BOOTSTRAP_STATE with progress and final status.
    """
    profiles_file = os.getenv("UNLZ_OPENCODE_PROFILES_FILE", r"C:\Users\cristian\Documents\OpenCode\launcher_profiles.json")
    models_dir = Path(os.getenv("LLAMACPP_MODELS_DIR") or str(_runtime_root_dir() / "llama.cpp" / "models"))
    bundled = _select_bundled_llama_server()

    force_payload: dict[str, Any] = {
        "AGENT_HARNESS": "opencode",
        "LLM_PROVIDER": "llamacpp",
        "AGENT_EXECUTION_MODE": "autonomous",
        "LLAMACPP_MODELS_DIR": str(models_dir),
    }
    if bundled:
        force_payload["LLAMACPP_EXECUTABLE"] = bundled
    _upsert_env_settings(force_payload)

    profiles = load_opencode_1_profiles(profiles_file)
    profiles_by_name = {str(p.get("profile_name") or ""): p for p in profiles}
    tier, vram, ram = _detect_hardware_tier()
    bucket = _hardware_bucket(vram)
    plan = _read_hardware_plan()
    selected_plan = plan.get(bucket) if isinstance(plan, dict) else None
    if not isinstance(selected_plan, dict):
        _BOOTSTRAP_STATE.update({"status": "error", "detail": f"No hay plan para bucket '{bucket}'"})
        return

    selected_profile_name = str(selected_plan.get("profile_name") or "").strip()
    selected_profile = profiles_by_name.get(selected_profile_name)
    if bool(selected_plan.get("require_1_profile")) and selected_profile is None:
        _BOOTSTRAP_STATE.update({
            "status": "error",
            "detail": f"Bucket {bucket} requiere perfil 1_* '{selected_profile_name}' y no existe en {profiles_file}",
        })
        return

    profile_alias = str((selected_profile or {}).get("alias") or "").strip()
    plan_model_id = str(selected_plan.get("opencode_model_id") or "").strip()
    chosen_target = _resolve_download_target(selected_plan)
    alias = chosen_target["alias"] or profile_alias or plan_model_id or "local-model"
    model_folder = chosen_target["model_folder"] or alias
    hf_repo = chosen_target["hf_repo"]
    filename = chosen_target["filename"]

    model_path = models_dir / model_folder / filename
    _upsert_env_settings({
        "LLAMACPP_MODEL_PATH": str(model_path),
        "LLAMACPP_MODEL_ALIAS": alias,
        "UNLZ_SELECTED_1_PROFILE": selected_profile_name,
        "UNLZ_BOOTSTRAP_TIER": tier,
        "UNLZ_BOOTSTRAP_BUCKET": bucket,
    })

    expected_sha = str(chosen_target.get("sha256") or "").strip().lower()
    if model_path.exists():
        if expected_sha:
            try:
                got_sha = _sha256_file(model_path)
                if got_sha != expected_sha:
                    model_path.unlink(missing_ok=True)
                    raise RuntimeError(f"SHA256 mismatch archivo existente ({got_sha} != {expected_sha})")
            except Exception as exc:
                _BOOTSTRAP_STATE.update({"status": "warning", "detail": f"Re-descargando por integridad: {exc}"})
        else:
            _BOOTSTRAP_STATE.update({
                "status": "ready",
                "detail": "Modelo ya presente.",
                "model_path": str(model_path),
                "selected_plan": selected_plan,
                "tier": tier,
                "bucket": bucket,
                "vram_gb": round(vram, 1),
                "ram_gb": round(ram, 1),
            })
            return

    if model_path.exists() and expected_sha:
        _BOOTSTRAP_STATE.update({
            "status": "ready",
            "detail": "Modelo ya presente (SHA256 verificado).",
            "model_path": str(model_path),
            "selected_plan": selected_plan,
            "tier": tier,
            "bucket": bucket,
            "vram_gb": round(vram, 1),
            "ram_gb": round(ram, 1),
        })
        return

    _BOOTSTRAP_STATE.update({"status": "downloading", "detail": f"Descargando {filename}..."})
    candidates = [chosen_target]
    if isinstance(selected_plan.get("fallback_candidates"), list):
        for c in selected_plan["fallback_candidates"]:
            if isinstance(c, dict):
                candidates.append({
                    "model_folder": str(c.get("model_folder") or "").strip(),
                    "alias": str(c.get("alias") or "").strip(),
                    "hf_repo": str(c.get("hf_repo") or "").strip(),
                    "filename": str(c.get("filename") or "").strip(),
                    "sha256": str(c.get("sha256") or "").strip().lower(),
                })

    last_exc = None
    for idx, cand in enumerate(candidates):
        if not cand["hf_repo"] or not cand["filename"]:
            continue
        cand_alias = cand["alias"] or alias
        cand_folder = cand["model_folder"] or model_folder
        cand_path = models_dir / cand_folder / cand["filename"]
        try:
            _download_hf_file(cand["hf_repo"], cand["filename"], cand_path)
            cand_sha = str(cand.get("sha256") or "").strip().lower()
            if cand_sha:
                got_sha = _sha256_file(cand_path)
                if got_sha != cand_sha:
                    cand_path.unlink(missing_ok=True)
                    raise RuntimeError(f"SHA256 mismatch descarga ({got_sha} != {cand_sha})")
            _upsert_env_settings({
                "LLAMACPP_MODEL_PATH": str(cand_path),
                "LLAMACPP_MODEL_ALIAS": cand_alias,
                "UNLZ_MODEL_SOURCE_REPO": cand["hf_repo"],
                "UNLZ_MODEL_SOURCE_FILE": cand["filename"],
                "UNLZ_MODEL_FALLBACK_INDEX": str(idx),
                "UNLZ_MODEL_MTP_ACTIVE": "true" if ("mtp" in cand_alias.lower() or "mtp" in cand["filename"].lower()) else "false",
            })
            _BOOTSTRAP_STATE.update({
                "status": "ready",
                "detail": "Modelo descargado." if idx == 0 else f"Modelo descargado con fallback #{idx}.",
                "model_path": str(cand_path),
                "selected_plan": selected_plan,
                "selected_candidate": cand,
                "tier": tier,
                "bucket": bucket,
                "vram_gb": round(vram, 1),
                "ram_gb": round(ram, 1),
            })
            return
        except Exception as exc:
            last_exc = exc

    _BOOTSTRAP_STATE.update({"status": "error", "detail": f"Fallo descarga (todos candidatos): {last_exc}"})


def _slug_alias(name: str) -> str:
    """Convert a model name to a URL-safe alias slug.

    Replaces underscores, dots, and spaces with hyphens. Lowercases result.

    Args:
        name: Raw model name or alias.

    Returns:
        Slugified alias string. Defaults to 'local-model' if empty.
    """
    alias = (name or "local-model").strip().lower()
    for ch in ("_", ".", " "):
        alias = alias.replace(ch, "-")
    return alias


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _http_reachable(url: str, timeout: float = 1.5) -> bool:
    """Check if an HTTP(S) endpoint is reachable.

    Performs a GET request and accepts any 1xx-5xx status code as reachable.

    Args:
        url: Full URL to check.
        timeout: Connection and read timeout in seconds.

    Returns:
        True if the endpoint responded with a valid HTTP status, False otherwise.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(parsed.hostname, port, timeout=timeout)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            _ = resp.read(32)
            return 100 <= resp.status < 600
        finally:
            conn.close()
    except Exception:
        return False


def _opencode_config_path() -> Path:
    """Return the path to the opencode config file.

    Returns:
        Path to opencode.json in the isolated opencode home directory.
    """
    return _opencode_local_config_path()


def _opencode_selected_base_url() -> str:
    """Extract the base URL from the opencode config's selected provider.

    Reads the model field (e.g. 'unlz-llama-local/alias'), extracts the
    provider ID, then returns the provider's baseURL option.

    Returns:
        Base URL string, or empty string if config is missing or invalid.
    """
    p = _opencode_config_path()
    if not p.exists():
        return ""
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ""
    model = str(cfg.get("model") or "").strip()
    if "/" not in model:
        return ""
    provider_id = model.split("/", 1)[0]
    provider = ((cfg.get("provider") or {}) if isinstance(cfg, dict) else {}).get(provider_id) or {}
    options = provider.get("options") if isinstance(provider, dict) else {}
    return str((options or {}).get("baseURL") or "").strip()


def _llamacpp_server_url() -> str:
    """Build the llama.cpp server OpenAI-compatible API URL.

    Returns:
        URL string like 'http://127.0.0.1:8081/v1'.
    """
    host = (os.getenv("LLAMACPP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = (os.getenv("LLAMACPP_PORT") or "8081").strip() or "8081"
    return f"http://{host}:{port}/v1"


def _ensure_llamacpp_server_started(timeout_sec: int = 25) -> tuple[bool, str]:
    """Start the llama.cpp server subprocess if not already running.

    Checks if the server is reachable. If not, starts llama-server.exe with
    the configured model, host, port, context size, and extra args.
    Polls until the server responds or timeout is reached.

    Args:
        timeout_sec: Maximum seconds to wait for server startup.

    Returns:
        Tuple of (success, detail_message). If success is True, detail is
        'ready' or 'started'. If False, detail describes the failure reason.
    """
    target = _llamacpp_server_url()
    if _http_reachable(target, timeout=1.2):
        return True, "ready"
    exe = (os.getenv("LLAMACPP_EXECUTABLE") or "").strip()
    model_path = (os.getenv("LLAMACPP_MODEL_PATH") or "").strip()
    host = (os.getenv("LLAMACPP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = (os.getenv("LLAMACPP_PORT") or "8081").strip() or "8081"
    ctx = (os.getenv("LLAMACPP_CONTEXT_SIZE") or "8192").strip() or "8192"
    extra = (os.getenv("LLAMACPP_EXTRA_ARGS") or "").strip()
    if not exe or not Path(exe).exists():
        return False, "LLAMACPP_EXECUTABLE no configurado o inexistente"
    if not model_path or not Path(model_path).exists():
        return False, "LLAMACPP_MODEL_PATH no configurado o inexistente"

    log_path = _unlz_internal_dir() / "llamacpp_start.log"
    with _LLAMA_SERVER_PROC_LOCK:
        global _LLAMA_SERVER_PROC
        if _LLAMA_SERVER_PROC is not None:
            rc = _LLAMA_SERVER_PROC.poll()
            if rc is None:
                started = time.time()
                while time.time() - started < timeout_sec:
                    if _http_reachable(target, timeout=1.2):
                        return True, "ready"
                    time.sleep(0.7)
                return False, f"llama.cpp no respondió en {target}"
            _LLAMA_SERVER_PROC = None

        args = [exe, "-m", model_path, "--host", host, "--port", port, "-c", ctx]
        if (os.getenv("LLAMACPP_FLASH_ATTN") or "").strip().lower() in ("1", "true", "yes", "on"):
            args.extend(["--flash-attn", "on"])
        if extra:
            args.extend(extra.split())
        env = os.environ.copy()
        exe_parent = str(Path(exe).resolve().parent)
        env["PATH"] = exe_parent + os.pathsep + env.get("PATH", "")
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        try:
            log_fh = open(log_path, "a", encoding="utf-8")
            log_fh.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] START llama-server: {' '.join(args)}\n")
            log_fh.flush()
            _LLAMA_SERVER_PROC = subprocess.Popen(
                args,
                cwd=exe_parent,
                stdout=log_fh,
                stderr=log_fh,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=creationflags,
                close_fds=True,
            )
        except Exception as exc:
            _LLAMA_SERVER_PROC = None
            return False, f"No se pudo iniciar llama.cpp: {exc}"

    started = time.time()
    while time.time() - started < timeout_sec:
        with _LLAMA_SERVER_PROC_LOCK:
            p = _LLAMA_SERVER_PROC
        if p is not None:
            rc = p.poll()
            if rc is not None:
                tail = ""
                try:
                    tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-6:]
                    tail = " | ".join(tail)
                except Exception:
                    tail = ""
                return False, f"llama.cpp terminó al iniciar (rc={rc}). {tail}"
        if _http_reachable(target, timeout=1.2):
            return True, "started"
        time.sleep(0.7)
    return False, f"llama.cpp no respondió en {target} dentro de {timeout_sec}s"


def _stop_llamacpp_server() -> None:
    """Terminate the managed llama.cpp server subprocess.

    On Windows, uses taskkill /T /F to kill the process tree.
    On other platforms, sends SIGTERM. Clears the global proc reference.
    """
    with _LLAMA_SERVER_PROC_LOCK:
        global _LLAMA_SERVER_PROC
        proc = _LLAMA_SERVER_PROC
        _LLAMA_SERVER_PROC = None
    if proc is not None:
        try:
            if proc.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], check=False, capture_output=True)
                else:
                    proc.terminate()
        except Exception:
            pass


def _run_opencode_warmup_once() -> dict[str, Any]:
    """Run a single opencode warmup to pre-load the model.

    Ensures llama.cpp is started, then runs opencode with a short prompt
    to trigger model loading. Uses isolated home directory and config.

    Returns:
        Dict with keys: status ('ready'/'error'), detail, started_at, finished_at.
    """
    started_at = datetime.now().isoformat(timespec="seconds")
    bin_path = _opencode_bin()
    if not bin_path:
        return {"status": "error", "detail": "opencode no instalado", "started_at": started_at, "finished_at": datetime.now().isoformat(timespec="seconds")}
    ok, reason = _ensure_llamacpp_server_started(timeout_sec=40)
    if not ok:
        return {"status": "error", "detail": f"llama.cpp no listo: {reason}", "started_at": started_at, "finished_at": datetime.now().isoformat(timespec="seconds")}

    local_cfg = _ensure_opencode_local_config()
    local_home = _opencode_local_home_dir()
    args = [bin_path, "run", "--dir", str(_runtime_root_dir())]
    if _opencode_supports_flag("--dangerously-skip-permissions"):
        args.append("--dangerously-skip-permissions")
    if _opencode_supports_flag("--format"):
        args.extend(["--format", "json"])
    args.append("Warmup run. Reply with a short OK.")

    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    env["HOME"] = str(local_home)
    env["USERPROFILE"] = str(local_home)
    env["XDG_CONFIG_HOME"] = str(local_home / ".config")
    env["UNLZ_OPENCODE_CONFIG"] = str(local_cfg)

    try:
        proc = subprocess.run(
            args,
            cwd=str(_runtime_root_dir()),
            env=env,
            capture_output=True,
            text=True,
            timeout=int(os.getenv("OPENCODE_WARMUP_TIMEOUT_SEC", "480")),
        )
        stderr = _strip_ansi((proc.stderr or "").strip())
        if proc.returncode == 0:
            return {
                "status": "ready",
                "detail": "warmup completado",
                "started_at": started_at,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }
        return {
            "status": "error",
            "detail": f"warmup rc={proc.returncode} {stderr[:300]}",
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
    except Exception as exc:
        return {
            "status": "error",
            "detail": f"warmup exception: {exc}",
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }


# ── Data paths ────────────────────────────────────────────────────────────────

def _runs_dir() -> Path:
    """Return the runtime directory used to persist per-run traces.

    Purpose:
        Ensures `data/runs/` exists and provides a stable location for trace
        files generated by streaming chat runs.

    Parameters:
        None.

    Returns:
        Path: Absolute path to the runs directory.

    Raises:
        OSError: If directory creation fails.
    """
    p = Path(Config.DATA_DIR) / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _trace_path(run_id: str) -> Path:
    """Build the JSON trace file path for a run identifier.

    Parameters:
        run_id (str): Sanitized run identifier.

    Returns:
        Path: Absolute path to the run trace file.

    Raises:
        This function does not raise exceptions intentionally.
    """
    return _runs_dir() / f"{run_id}.json"


def _persist_trace(run_id: str, trace: dict) -> None:
    """Persist a run trace payload as formatted UTF-8 JSON.

    Parameters:
        run_id (str): Run identifier.
        trace (dict): Serializable trace payload.

    Returns:
        None.

    Raises:
        OSError: If the file cannot be written.
        TypeError: If `trace` contains non-serializable values.
    """
    _trace_path(run_id).write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")


def _log_path() -> Path:
    """Return the absolute path of the backend log file."""
    return _runtime_root_dir() / "agent_server.log"


def _newbie_profile_path() -> Path:
    """Return and ensure the beginner profile JSON path under `data/`."""
    p = Path(Config.DATA_DIR) / "newbie_profile.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _newbie_metrics_path() -> Path:
    """Return and ensure the beginner metrics JSON path under `data/`."""
    p = Path(Config.DATA_DIR) / "newbie_metrics.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _newbie_snapshots_dir() -> Path:
    """Return and ensure the snapshots directory for beginner flows."""
    p = Path(Config.DATA_DIR) / "snapshots"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_json_file(path: Path, default: Any) -> Any:
    """Load a JSON file safely with fallback to a default value.

    Parameters:
        path (Path): File path to read.
        default (Any): Value returned when file is absent or invalid.

    Returns:
        Any: Parsed JSON value or `default`.

    Raises:
        This function catches read/parse exceptions and does not re-raise.
    """
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json_file(path: Path, payload: Any) -> None:
    """Write a payload as human-readable UTF-8 JSON.

    Parameters:
        path (Path): Destination file path.
        payload (Any): JSON-serializable value to write.

    Returns:
        None.

    Raises:
        OSError: If writing to disk fails.
        TypeError: If `payload` is not JSON serializable.
    """
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Run cancel registry ───────────────────────────────────────────────────────

_active_run_cancels: dict[str, asyncio.Event] = {}
_active_run_cancels_lock = threading.Lock()


def _register_run_cancel(run_id: str) -> asyncio.Event:
    """Register and return the cancellation event for a run.

    Parameters:
        run_id (str): Unique run identifier.

    Returns:
        asyncio.Event: Event that can be signaled to request cancellation.

    Raises:
        This function does not raise exceptions intentionally.
    """
    ev = asyncio.Event()
    with _active_run_cancels_lock:
        _active_run_cancels[run_id] = ev
    return ev


def _unregister_run_cancel(run_id: str) -> None:
    """Remove a run cancellation handle from the in-memory registry."""
    with _active_run_cancels_lock:
        _active_run_cancels.pop(run_id, None)


def _set_run_cancel(run_id: str) -> bool:
    """Signal cancellation for a registered run.

    Parameters:
        run_id (str): Run identifier.

    Returns:
        bool: `True` if the run existed and was signaled, else `False`.

    Raises:
        This function suppresses event signaling errors and returns `False`.
    """
    with _active_run_cancels_lock:
        ev = _active_run_cancels.get(run_id)
    if not ev:
        return False
    try:
        ev.set()
    except Exception:
        return False
    return True


# ── Local behaviors ───────────────────────────────────────────────────────────

def _load_local_behaviors() -> list[dict]:
    """Load user-defined local behaviors from persisted JSON.

    Purpose:
        Parses and sanitizes behavior definitions stored in
        `data/local_behaviors.json`, applying defaults for optional fields.

    Parameters:
        None.

    Returns:
        list[dict]: Normalized local behavior records ready for API responses.

    Raises:
        This function catches file and JSON parse errors internally.
    """
    path = Path(Config.DATA_DIR) / "local_behaviors.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    now = int(time.time() * 1000)
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        content = str(item.get("content") or "").strip()
        if not name or not content:
            continue
        bid = str(item.get("id") or "").strip() or f"local-{_slug_alias(name)}"
        tools_mode = str(item.get("defaultToolsMode") or "auto")
        if tools_mode not in ("auto", "with_tools", "without_tools"):
            tools_mode = "auto"
        out.append({
            "id": bid,
            "name": name,
            "content": content,
            "icon": str(item.get("icon") or "🜏").strip() or "🜏",
            "model": str(item.get("model") or "").strip(),
            "harness": str(item.get("harness") or "").strip(),
            "defaultInternetEnabled": bool(item.get("defaultInternetEnabled", True)),
            "defaultToolsMode": tools_mode,
            "createdAt": int(item.get("createdAt") or now),
            "updatedAt": int(item.get("updatedAt") or now),
            "localOnly": True,
        })
    return out


# ── Harness meta ──────────────────────────────────────────────────────────────

def _harness_install_root() -> Path:
    """Return the directory where local harness artifacts are installed."""
    return _runtime_root_dir() / "data" / ".unlz_internal" / "harnesses"


def _harness_meta_path() -> Path:
    """Return the metadata JSON path for installed harness information."""
    return _harness_install_root() / "harnesses.json"


def _ensure_harness_dirs() -> None:
    """Ensure harness install directories exist on disk."""
    _harness_install_root().mkdir(parents=True, exist_ok=True)


def _unlz_internal_dir() -> Path:
    """Ensure and return the internal runtime data directory."""
    p = _runtime_root_dir() / "data" / ".unlz_internal"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _opencode_local_home_dir() -> Path:
    """Ensure and return the isolated opencode home directory."""
    p = _unlz_internal_dir() / "opencode_home"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _opencode_local_config_path() -> Path:
    """Ensure and return the opencode local configuration file path."""
    p = _opencode_local_home_dir() / ".config" / "opencode" / "opencode.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _llamacpp_local_base_url() -> str:
    """Build the local OpenAI-compatible base URL for llama.cpp."""
    host = (os.getenv("LLAMACPP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = (os.getenv("LLAMACPP_PORT") or "8081").strip() or "8081"
    return f"http://{host}:{port}/v1"


def _ensure_opencode_local_config() -> Path:
    """Generate or verify the opencode local config file.

    Creates an isolated opencode.json with a 'unlz-llama-local' provider
    pointing to the local llama.cpp server. Writes to data/.unlz_internal/
    opencode_home/.config/opencode/opencode.json.

    Returns:
        Path to the config file.
    """
    cfg_path = _opencode_local_config_path()
    alias = (os.getenv("LLAMACPP_MODEL_ALIAS") or "unlz-local-model").strip() or "unlz-local-model"
    base_url = _llamacpp_local_base_url()
    payload = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "unlz-llama-local": {
                "name": "UNLZ Local llama.cpp",
                "npm": "@ai-sdk/openai-compatible",
                "options": {
                    "baseURL": base_url,
                    "timeout": 180000,
                    "chunkTimeout": 180000,
                },
                "models": {
                    alias: {
                        "name": alias,
                        "tool_call": True,
                        "limit": {"context": 120000, "output": 4096},
                    }
                },
            }
        },
        "model": f"unlz-llama-local/{alias}",
        "small_model": f"unlz-llama-local/{alias}",
        "compaction": {"auto": True, "prune": True, "reserved": 30000},
        "mcp": {},
    }
    existing = _load_json_file(cfg_path, None)
    if existing != payload:
        _save_json_file(cfg_path, payload)
    return cfg_path


def _read_harness_meta() -> dict:
    """Read installed harness metadata from disk with safe fallback.

    Returns:
        dict: Parsed metadata map, or `{}` when missing/invalid.
    """
    p = _harness_meta_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_harness_meta(data: dict) -> None:
    """Persist installed harness metadata to disk.

    Parameters:
        data (dict): Serializable metadata object.

    Raises:
        OSError: If writing fails.
        TypeError: If `data` is not JSON serializable.
    """
    _ensure_harness_dirs()
    _harness_meta_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── npm helper ────────────────────────────────────────────────────────────────

def _which_any(candidates: list[str]) -> str:
    """Return the first executable path found for candidate command names."""
    for name in candidates:
        p = shutil.which(name)
        if p:
            return p
    return ""


def _npm_bin() -> str:
    """Locate `npm` executable using PATH and common Windows install paths."""
    found = _which_any(["npm", "npm.cmd", "npm.exe"])
    if found:
        return found
    roots = [os.getenv("ProgramFiles", ""), os.getenv("ProgramFiles(x86)", ""), os.getenv("LocalAppData", "")]
    for root in roots:
        if not root:
            continue
        p = Path(root) / "nodejs" / "npm.cmd"
        if p.exists():
            return str(p)
    return ""


# ── opencode helpers ──────────────────────────────────────────────────────────

def _opencode_bin() -> str:
    """Locate the opencode CLI binary from config, PATH, or AppData."""
    configured = (os.getenv("HARNESS_OPENCODE_BIN") or getattr(Config, "HARNESS_OPENCODE_BIN", "") or "").strip()
    if configured and Path(configured).exists():
        return configured
    detected = _which_any(["opencode.cmd", "opencode.exe", "opencode"])
    if detected:
        try:
            p = Path(detected)
            if p.suffix.lower() == ".ps1":
                sibling_cmd = p.with_suffix(".cmd")
                if sibling_cmd.exists():
                    return str(sibling_cmd)
        except Exception:
            pass
        return detected
    appdata = os.getenv("APPDATA", "")
    if appdata:
        for name in ("opencode.cmd", "opencode.exe", "opencode"):
            p = Path(appdata) / "npm" / name
            if p.exists():
                return str(p)
    return ""


def _opencode_version(bin_path: str) -> str:
    """Get the opencode CLI version string.

    Runs 'opencode --version' and returns the first line of output.

    Args:
        bin_path: Path to the opencode binary.

    Returns:
        Version string (max 120 chars), or empty string on failure.
    """
    if not bin_path:
        return ""
    try:
        proc = subprocess.run([bin_path, "--version"], capture_output=True, text=True, timeout=12)
        if proc.returncode == 0:
            txt = (proc.stdout or proc.stderr or "").strip()
            if txt:
                return txt.splitlines()[0][:120]
    except Exception:
        pass
    return ""


def _opencode_installed() -> bool:
    """Check if opencode is available on the system.

    Returns:
        True if _opencode_bin() finds a valid binary path.
    """
    return bool(_opencode_bin())


# ── Process kill ──────────────────────────────────────────────────────────────

def _kill_pid_tree(pid: int) -> bool:
    """Kill a process and its children.

    On Windows, uses 'taskkill /PID /T /F'. On other platforms, sends SIGTERM.
    Refuses to kill PID <= 0 or the current process.

    Args:
        pid: Process ID to kill.

    Returns:
        True if the kill command was issued, False if refused or failed.
    """
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            return True
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


# ── opencode streaming ────────────────────────────────────────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_OPENCODE_FLAG_CACHE: dict[str, bool] = {}


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from terminal output.

    Args:
        text: Raw text potentially containing ANSI color/format codes.

    Returns:
        Clean text with all ANSI sequences removed.
    """
    return _ANSI_RE.sub("", text or "")


def _sse(payload: dict[str, Any]) -> str:
    """Format a dict as an SSE data line.

    Args:
        payload: Dict to serialize as JSON.

    Returns:
        String like "data: {json}\n\n".
    """
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _timeline_stage_for_step(step_text: str) -> tuple[str, str]:
    """Map an opencode step text to a UI timeline stage.

    Args:
        step_text: The step identifier from opencode (e.g. 'tool', 'plan', 'search').

    Returns:
        Tuple of (stage_key, human_label). Stages: understanding, reading,
        planning, editing, validating.
    """
    low = (step_text or "").strip().lower()
    if not low:
        return ("understanding", "Analizando tu pedido")
    if "args" in low or "task_router" in low:
        return ("understanding", "Analizando tu pedido")
    if "search" in low or "folder" in low or "knowledge" in low:
        return ("reading", "Leyendo archivos y contexto")
    if "plan" in low:
        return ("planning", "Planificando solución")
    if "run_windows_command" in low or "tool" in low:
        return ("editing", "Aplicando cambios")
    if "stderr" in low or "valid" in low:
        return ("validating", "Validando resultado")
    return ("editing", "Aplicando cambios")


def _timeline_sse(stage: str, label: str) -> str:
    """Create a timeline SSE event with timestamp.

    Args:
        stage: Stage key (understanding, reading, planning, editing, validating, generating, done).
        label: Human-readable label for the stage.

    Returns:
        SSE-formatted timeline event string.
    """
    return _sse({"type": "timeline", "stage": stage, "label": label, "ts": int(time.time() * 1000)})


def _detect_confusion_signal(message: str, history: list[dict[str, Any]]) -> bool:
    """Detect if the user appears confused based on message and recent history.

    Checks for trigger phrases like "no entend", "explicá más simple", "me perdí".

    Args:
        message: Current user message.
        history: Recent conversation turns.

    Returns:
        True if confusion triggers are detected.
    """
    text = " ".join(
        [str(message or "")]
        + [str((h or {}).get("content") or "") for h in history[-4:]]
    ).lower()
    triggers = ("no entend", "explicá más simple", "explica mas simple", "me perdí", "no me queda claro")
    return any(t in text for t in triggers)


def _opencode_supports_flag(flag: str) -> bool:
    cache_key = str(flag or "").strip()
    if cache_key in _OPENCODE_FLAG_CACHE:
        return _OPENCODE_FLAG_CACHE[cache_key]
    bin_path = _opencode_bin()
    if not bin_path or not cache_key:
        _OPENCODE_FLAG_CACHE[cache_key] = False
        return False
    try:
        proc = subprocess.run([bin_path, "run", "--help"], capture_output=True, text=True, timeout=8)
        txt = (proc.stdout or "") + "\n" + (proc.stderr or "")
        ok = cache_key in txt
        _OPENCODE_FLAG_CACHE[cache_key] = ok
        return ok
    except Exception:
        _OPENCODE_FLAG_CACHE[cache_key] = False
        return False


_OPENCODE_SYSTEM_PROMPT = (
    "Harness profile: opencode. "
    "Favor short iterative coding loops with quick verification and tool use when needed. "
    "Keep responses practical and execution-oriented. "
    "When solving coding tasks, prefer concrete patches and checks over long explanations."
)


def _build_opencode_prompt(
    message: str,
    history: list[dict[str, Any]],
    system_prompt: str = "",
    mode: str = "normal",
    internet_enabled: bool = True,
    tools_mode: str = "auto",
) -> str:
    """Build the full prompt string passed to opencode.

    Assembles sections: [SYSTEM] (base + behavior), [SESSION] (mode, tool/internet policy),
    [HISTORY] (last 12 turns), [USER] (current message), [INSTRUCTIONS].

    Detects confusion signals in the message/history and injects beginner-friendly
    instructions when the user appears confused.

    Args:
        message: Current user message.
        history: List of {role, content} dicts.
        system_prompt: Optional behavior-specific system prompt.
        mode: Chat mode ('normal', 'simple', etc.).
        internet_enabled: Whether internet tools are allowed.
        tools_mode: 'auto', 'with_tools', or 'without_tools'.

    Returns:
        Complete prompt string with all sections joined by blank lines.
    """
    base = _OPENCODE_SYSTEM_PROMPT
    if system_prompt:
        base = f"{base}\n\nBehavior profile:\n{system_prompt}"
    hist_lines: list[str] = []
    for h in history[-12:]:
        role = str(h.get("role") or "").strip().lower()
        content = str(h.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            hist_lines.append(f"{role}: {content}")
    tool_policy = (
        "no_tools" if tools_mode == "without_tools"
        else ("tools_required" if tools_mode == "with_tools" else "tools_auto")
    )
    internet_policy = "internet_enabled" if internet_enabled else "internet_disabled"
    is_confused = _detect_confusion_signal(message, history)
    parts = [
        f"[SYSTEM]\n{base}",
        f"[SESSION]\nmode={(mode or 'normal').lower()}\n{tool_policy}\n{internet_policy}",
    ]
    if hist_lines:
        parts.append("[HISTORY]\n" + "\n".join(hist_lines))
    parts.append(f"[USER]\n{message}")
    extra = "If the user seems confused, explain in beginner-friendly steps with plain language and short examples." if is_confused else ""
    parts.append(f"[INSTRUCTIONS]\nRespond in Markdown. Be concrete and concise. {extra}".strip())
    return "\n\n".join(parts)


async def _opencode_stream(
    message: str,
    history: list[dict[str, Any]],
    system_prompt: str = "",
    model_override: str = "",
    harness_override: str = "",
    folder_id: str = "",
    sandbox_root: str = "",
    mode: str = "normal",
    internet_enabled: bool = True,
    tools_mode: str = "auto",
    llamacpp_overrides: Optional[dict[str, Any]] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> AsyncGenerator[str, None]:
    """Execute opencode as a subprocess and stream output as SSE events.

    This is the core execution function. It:
    1. Validates opencode binary and working directory
    2. Ensures llama.cpp is reachable
    3. Builds prompt with _build_opencode_prompt()
    4. Spawns opencode subprocess with isolated HOME, config, env
    5. Pumps stdout/stderr to an async queue
    6. Parses JSON output (if --format json supported) or raw text
    7. Yields SSE events: step, chunk, error, done

    Supports cancellation via cancel_event which kills the process tree.
    Handles timeouts: first_chunk_timeout for cold starts, silent_timeout for stalls.

    Args:
        message: User's current message.
        history: Conversation history as [{role, content}, ...].
        system_prompt: Optional behavior system prompt.
        model_override: Optional model ID override.
        harness_override: Unused (opencode-only).
        folder_id: Unused (sandbox_root takes precedence).
        sandbox_root: Working directory for opencode. Defaults to runtime root.
        mode: Chat mode string.
        internet_enabled: Whether internet access is allowed.
        tools_mode: 'auto', 'with_tools', or 'without_tools'.
        llamacpp_overrides: Unused (config is managed by bootstrap).
        cancel_event: Asyncio Event to signal cancellation.

    Yields:
        SSE-formatted strings: "data: {json}\n\n"

    Raises:
        No exceptions — errors are yielded as SSE error events.
    """
    bin_path = _opencode_bin()
    if not bin_path:
        yield _sse({"type": "error", "text": "opencode no instalado o no encontrado en PATH. Instalá con: npm i -g opencode-ai"})
        yield _sse({"type": "done"})
        return

    # Resolve working directory — default to runtime root (never user home).
    if (sandbox_root or "").strip():
        workdir_path = Path(sandbox_root).expanduser().resolve()
        if not workdir_path.is_dir():
            yield _sse({"type": "error", "text": f"Sandbox inválido o inexistente: {workdir_path}"})
            yield _sse({"type": "done"})
            return
    else:
        workdir_path = _runtime_root_dir().resolve()

    workdir = str(workdir_path)

    local_cfg = _ensure_opencode_local_config()
    local_home = _opencode_local_home_dir()

    base_url = _opencode_selected_base_url()
    if base_url and not _http_reachable(base_url, timeout=1.2):
        ok, reason = _ensure_llamacpp_server_started(timeout_sec=30)
        if ok:
            base_url = _opencode_selected_base_url()
        if ok and base_url and _http_reachable(base_url, timeout=1.2):
            pass
        else:
            cfg_path = _opencode_config_path()
            yield _sse({
                "type": "error",
                "text": (
                    "opencode configurado con endpoint no disponible: "
                    f"{base_url}. Config local: {cfg_path}. Detalle: {reason}. "
                    "Verificá provider/modelo local o iniciá llama.cpp local."
                ),
            })
            yield _sse({"type": "done"})
            return

    exec_mode = (getattr(Config, "AGENT_EXECUTION_MODE", "autonomous") or "autonomous").strip().lower()
    if exec_mode == "confirm":
        yield _sse({
            "type": "error",
            "text": "El modo 'confirm' no es compatible con opencode: requiere interacción manual. Cambiá a 'autonomous' en Configuración → Execution Mode.",
        })
        yield _sse({"type": "done"})
        return

    prompt = _build_opencode_prompt(message, history, system_prompt, mode, internet_enabled, tools_mode)
    mo = (model_override or "").strip()

    args = [bin_path, "run", "--dir", workdir]

    if mo and "/" in mo:
        args.extend(["--model", mo])

    if _opencode_supports_flag("--dangerously-skip-permissions"):
        args.append("--dangerously-skip-permissions")

    if _opencode_supports_flag("--format"):
        args.extend(["--format", "json"])

    args.append(prompt)

    effective_model = mo if (mo and "/" in mo) else "(opencode config)"
    yield _sse({
        "type": "step",
        "text": "opencode.args",
        "args": {
            "bin": bin_path,
            "cwd": workdir,
            "prompt_chars": len(prompt),
            "opencode_config": str(local_cfg),
            "opencode_home": str(local_home),
        },
    })
    yield _sse({"type": "step", "text": "opencode.run", "args": {"cwd": workdir, "model": effective_model}})

    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    # Force opencode to use UNLZ-local config instead of user's global profile.
    env["HOME"] = str(local_home)
    env["USERPROFILE"] = str(local_home)
    env["XDG_CONFIG_HOME"] = str(local_home / ".config")
    env["UNLZ_OPENCODE_CONFIG"] = str(local_cfg)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=workdir,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except Exception as e:
        yield _sse({"type": "error", "text": f"No se pudo iniciar opencode: {e}"})
        yield _sse({"type": "done"})
        return

    emitted = False
    first_chunk_emitted = False
    first_chunk_elapsed_ms: Optional[int] = None
    stderr_seen: list[str] = []
    migration_in_progress = False
    queue: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
    stdout_buf = ""

    async def _pump_pipe(pipe, name: str):
        if pipe is None:
            return
        try:
            while True:
                raw = await pipe.read(1024)
                if not raw:
                    break
                await queue.put((name, raw))
        except Exception as e:
            await queue.put((name, f"\n[{name} read error: {e}]\n".encode("utf-8", errors="ignore")))

    pump_tasks = [
        asyncio.create_task(_pump_pipe(proc.stdout, "stdout")),
        asyncio.create_task(_pump_pipe(proc.stderr, "stderr")),
    ]

    try:
        last_output_at = time.time()
        started_waiting_at = time.time()

        while True:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    if proc.returncode is None:
                        _kill_pid_tree(proc.pid)
                except Exception:
                    pass
                yield _sse({"type": "error", "text": "Ejecución cancelada por el usuario."})
                yield _sse({"type": "done"})
                return

            proc_done = proc.returncode is not None
            pumps_done = all(t.done() for t in pump_tasks)
            if proc_done and pumps_done and queue.empty():
                break

            try:
                name, raw = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # Cold starts can be slow on local models (load/warmup/download). Use safer defaults.
                first_chunk_timeout = int(os.getenv("OPENCODE_FIRST_CHUNK_TIMEOUT_SEC", "35"))
                if str((_BOOTSTRAP_STATE or {}).get("status") or "") in ("running", "downloading"):
                    first_chunk_timeout = max(first_chunk_timeout, 600)
                if migration_in_progress:
                    first_chunk_timeout = max(first_chunk_timeout, 420)
                if not first_chunk_emitted and (time.time() - started_waiting_at > first_chunk_timeout):
                    if proc.returncode is None:
                        _kill_pid_tree(proc.pid)
                    yield _sse({"type": "error", "text": f"opencode timeout esperando primer token ({first_chunk_timeout}s)."})
                    break
                silent_timeout = int(os.getenv("OPENCODE_SILENT_TIMEOUT_SEC", "900"))
                if time.time() - last_output_at > silent_timeout:
                    if proc.returncode is None:
                        _kill_pid_tree(proc.pid)
                    yield _sse({"type": "error", "text": f"opencode timeout ({silent_timeout}s sin salida)."})
                    break
                continue

            last_output_at = time.time()
            text = _strip_ansi(raw.decode("utf-8", errors="ignore")).replace("\r", "\n")

            if name == "stderr":
                stderr_seen.append(text)
                line = text.strip()
                low_line = line.lower()
                if "one time database migration" in low_line or "sqlite-migration" in low_line:
                    migration_in_progress = True
                if line:
                    yield _sse({"type": "step", "text": "opencode.stderr", "args": {"line": line[:500]}})
                continue

            stdout_buf += text
            lines = stdout_buf.split("\n")
            stdout_buf = lines.pop() if lines else ""
            for ln in lines:
                clean = ln.strip()
                if not clean:
                    continue
                parsed: dict[str, Any] | None = None
                if clean.startswith("{") and clean.endswith("}"):
                    try:
                        parsed = json.loads(clean)
                    except Exception:
                        parsed = None
                if parsed is not None:
                    et = str(parsed.get("type") or "").strip().lower()
                    txt = ""
                    for k in ("text", "content", "message", "delta"):
                        v = parsed.get(k)
                        if isinstance(v, str) and v.strip():
                            txt = v
                            break
                    if not txt:
                        data_v = parsed.get("data")
                        if isinstance(data_v, dict):
                            for k in ("text", "content", "delta", "message"):
                                vv = data_v.get(k)
                                if isinstance(vv, str) and vv.strip():
                                    txt = vv
                                    break
                    if et in ("tool", "tool_use", "step", "status"):
                        yield _sse({"type": "step", "text": f"opencode.{et}", "args": parsed})
                        continue
                    if txt.strip():
                        low = txt.strip().lower()
                        if low not in ("thinking", "working") and "esc to interrupt" not in low:
                            emitted = True
                            first_chunk_emitted = True
                            if first_chunk_elapsed_ms is None:
                                first_chunk_elapsed_ms = int((time.time() - started_waiting_at) * 1000)
                                yield _sse({"type": "step", "text": "opencode.first_token", "args": {"elapsed_ms": first_chunk_elapsed_ms}})
                            yield _sse({"type": "chunk", "text": txt})
                    continue

                low = clean.lower()
                if low not in ("thinking", "working") and "esc to interrupt" not in low:
                    emitted = True
                    first_chunk_emitted = True
                    if first_chunk_elapsed_ms is None:
                        first_chunk_elapsed_ms = int((time.time() - started_waiting_at) * 1000)
                        yield _sse({"type": "step", "text": "opencode.first_token", "args": {"elapsed_ms": first_chunk_elapsed_ms}})
                    yield _sse({"type": "chunk", "text": clean})

        tail = stdout_buf.strip()
        if tail:
            try:
                parsed_tail = json.loads(tail) if (tail.startswith("{") and tail.endswith("}")) else None
            except Exception:
                parsed_tail = None
            if isinstance(parsed_tail, dict):
                txt = str(parsed_tail.get("text") or parsed_tail.get("content") or "").strip()
                if txt:
                    emitted = True
                    first_chunk_emitted = True
                    if first_chunk_elapsed_ms is None:
                        first_chunk_elapsed_ms = int((time.time() - started_waiting_at) * 1000)
                        yield _sse({"type": "step", "text": "opencode.first_token", "args": {"elapsed_ms": first_chunk_elapsed_ms}})
                    yield _sse({"type": "chunk", "text": txt})
            else:
                emitted = True
                first_chunk_emitted = True
                if first_chunk_elapsed_ms is None:
                    first_chunk_elapsed_ms = int((time.time() - started_waiting_at) * 1000)
                    yield _sse({"type": "step", "text": "opencode.first_token", "args": {"elapsed_ms": first_chunk_elapsed_ms}})
                yield _sse({"type": "chunk", "text": tail})

    finally:
        for task in pump_tasks:
            if not task.done():
                task.cancel()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10.0)
        except (asyncio.TimeoutError, Exception):
            pass
        try:
            if proc.returncode is None:
                _kill_pid_tree(proc.pid)
        except Exception:
            pass

    if not emitted:
        stderr_text = _strip_ansi("".join(stderr_seen)).strip()
        err_msg = (
            f"opencode error: {stderr_text[:500]}" if stderr_text
            else "opencode no devolvió salida (empty completion)."
        )
        yield _sse({"type": "error", "text": err_msg})

    return_code = proc.returncode
    if return_code not in (0, None):
        stderr_text = _strip_ansi("".join(stderr_seen)).strip()
        msg = f"opencode terminó con código {return_code}."
        if stderr_text:
            msg += f"\n\nstderr:\n```text\n{stderr_text[:1200]}\n```"
        yield _sse({"type": "error", "text": msg})

    yield _sse({"type": "done"})


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="UNLZ Agent Server (opencode)", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup_bootstrap():
    """Run at server startup: bootstrap runtime then optionally warm up opencode.

    1. Runs _bootstrap_locked_runtime() in a thread (forces config, downloads model)
    2. If UNLZ_OPENCODE_WARMUP_ON_STARTUP=1, starts background warmup task
    """
    try:
        _BOOTSTRAP_STATE.update({"status": "running", "detail": "Inicializando runtime bloqueado..."})
        await asyncio.to_thread(_bootstrap_locked_runtime)
        auto_warmup = (os.getenv("UNLZ_OPENCODE_WARMUP_ON_STARTUP", "1") or "1").strip().lower() in ("1", "true", "yes", "on")
        if auto_warmup:
            async def _bg_warmup():
                with _OPENCODE_WARMUP_LOCK:
                    _OPENCODE_WARMUP_STATE.update({
                        "status": "running",
                        "detail": "warmup en progreso",
                        "started_at": datetime.now().isoformat(timespec="seconds"),
                        "finished_at": "",
                    })
                result = await asyncio.to_thread(_run_opencode_warmup_once)
                with _OPENCODE_WARMUP_LOCK:
                    _OPENCODE_WARMUP_STATE.update(result)
            asyncio.create_task(_bg_warmup())
    except Exception as exc:
        _BOOTSTRAP_STATE.update({"status": "error", "detail": f"Bootstrap error: {exc}"})


class ChatRequest(BaseModel):
    """Request body for the chat endpoint.

    Attributes:
        message: User's current message.
        history: Previous conversation turns as [{role, content}, ...].
        system_prompt: Optional behavior-specific system prompt override.
        model_override: Optional model alias override.
        harness_override: Always opencode (retained for compatibility).
        llamacpp_overrides: Per-request llama.cpp runtime overrides.
        folder_id: Optional folder scope for sandboxed operations.
        sandbox_root: Absolute path for opencode working directory.
        mode: Chat mode (default 'normal').
        conversation_id: Optional ID for trace persistence.
        dry_run: If True, returns immediately without executing opencode.
        internet_enabled: Whether internet access is allowed.
        tools_mode: 'auto', 'with_tools', or 'without_tools'.
        user_profile: Dict with experience_level, detail_level, language.
    """
    message: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    system_prompt: str = ""
    model_override: str = ""
    harness_override: str = ""
    llamacpp_overrides: dict[str, Any] = Field(default_factory=dict)
    folder_id: str = ""
    sandbox_root: str = ""
    mode: str = "normal"
    conversation_id: str = ""
    dry_run: bool = False
    internet_enabled: bool = True
    tools_mode: str = "auto"
    user_profile: dict[str, Any] = Field(default_factory=dict)


class HarnessInstallRequest(BaseModel):
    """Request body for installing a harness.

    Attributes:
        harness_id: ID of the harness to install (only 'opencode' supported).
    """
    harness_id: str


class OnboardingActionRequest(BaseModel):
    """Request body for onboarding fix action.

    Attributes:
        ensure_runtime: If True, creates required directories and harness dirs.
    """
    ensure_runtime: bool = True


# ── Chat endpoint ─────────────────────────────────────────────────────────────

def _chat_streaming_response(req: ChatRequest) -> StreamingResponse:
    """Build the SSE streaming response for a chat request.

    Wraps _opencode_stream() with:
    - Run ID generation and cancel event registration
    - Trace collection (all SSE events persisted to data/runs/)
    - Timeline stage injection (understanding → reading → planning → ...)
    - User profile injection into system prompt
    - Error explanation via explain_error_for_humans()

    Args:
        req: Parsed ChatRequest from the POST /chat endpoint.

    Returns:
        StreamingResponse with text/event-stream media type and no-cache headers.
    """
    run_id = str(uuid.uuid4())
    cancel_event = _register_run_cancel(run_id)

    async def _generate():
        trace: dict[str, Any] = {
            "run_id": run_id,
            "conversation_id": req.conversation_id,
            "mode": req.mode,
            "mode_effective": "opencode",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": "",
            "input": {"message": req.message, "history_size": len(req.history)},
            "timing": {},
            "events": [],
        }

        def _record(ev_str: str):
            if ev_str.startswith("data: "):
                raw = ev_str[6:].strip()
                if raw:
                    try:
                        trace["events"].append(json.loads(raw))
                    except Exception:
                        pass

        try:
            yield f"data: {json.dumps({'type': 'run', 'run_id': run_id})}\n\n"
            yield _timeline_sse("understanding", "Analizando tu pedido")
            if req.dry_run:
                yield _sse({"type": "chunk", "text": f"[dry_run] opencode @ {req.sandbox_root or Path.home()}"})
                yield _timeline_sse("done", "Finalizado (dry-run)")
                yield _sse({"type": "done"})
                return

            profile = req.user_profile or {}
            profile_level = str(profile.get("experience_level") or "").strip().lower()
            profile_detail = str(profile.get("detail_level") or "").strip().lower()
            profile_lang = str(profile.get("language") or "").strip().lower()
            profile_hint = []
            if profile_level in ("newbie", "beginner"):
                profile_hint.append("User is beginner: avoid jargon, explain actions step-by-step.")
            if profile_detail in ("simple", "short"):
                profile_hint.append("Keep explanations simple and actionable.")
            if profile_lang in ("es", "spanish", "español"):
                profile_hint.append("Answer in Spanish.")
            system_prompt = req.system_prompt
            if profile_hint:
                system_prompt = f"{system_prompt}\n\n[USER_PROFILE]\n" + " ".join(profile_hint)

            seen_stages: set[str] = {"understanding"}
            async for ev in _opencode_stream(
                message=req.message,
                history=req.history,
                system_prompt=system_prompt,
                model_override=req.model_override,
                harness_override=req.harness_override,
                folder_id=req.folder_id,
                sandbox_root=req.sandbox_root,
                mode=req.mode,
                internet_enabled=req.internet_enabled,
                tools_mode=req.tools_mode,
                llamacpp_overrides=req.llamacpp_overrides,
                cancel_event=cancel_event,
            ):
                _record(ev)
                try:
                    raw = ev[6:].strip() if ev.startswith("data: ") else ""
                    payload = json.loads(raw) if raw else {}
                except Exception:
                    payload = {}

                ev_type = str(payload.get("type") or "")
                if ev_type == "step":
                    stage, label = _timeline_stage_for_step(str(payload.get("text") or ""))
                    if stage not in seen_stages:
                        seen_stages.add(stage)
                        yield _timeline_sse(stage, label)
                    yield ev
                    continue
                if ev_type == "chunk":
                    if "generating" not in seen_stages:
                        seen_stages.add("generating")
                        yield _timeline_sse("generating", "Generando respuesta")
                    yield ev
                    continue
                if ev_type == "error":
                    detail = explain_error_for_humans(str(payload.get("text") or ""))
                    err_payload = {
                        **payload,
                        "human_message": detail["human_message"],
                        "common_causes": detail["common_causes"],
                        "fix_steps": detail["fix_steps"],
                    }
                    yield _timeline_sse("validating", "Se detectó un error")
                    yield _sse(err_payload)
                    continue
                if ev_type == "done":
                    yield _timeline_sse("done", "Finalizado")
                    yield ev
                    continue
                yield ev
        finally:
            _unregister_run_cancel(run_id)
            trace["finished_at"] = datetime.now().isoformat(timespec="seconds")
            try:
                _persist_trace(run_id, trace)
            except Exception:
                pass

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat")
@app.post("/chat/stream")
@app.post("/api/chat")
@app.post("/api/chat/stream")
async def chat_endpoint(req: ChatRequest):
    """Streaming chat endpoint compatible with legacy and `/api` routes.

    Parameters:
        req (ChatRequest): Structured chat request payload.

    Returns:
        StreamingResponse: Server-Sent Events stream generated by the tool loop.

    Raises:
        HTTPException: Downstream request validation/runtime errors.
    """
    return _chat_streaming_response(req)


# ── Cancel / runs ─────────────────────────────────────────────────────────────

@app.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    """Request cancellation of an active streaming run.

    Parameters:
        run_id (str): Run identifier from prior `/chat` response events.

    Returns:
        dict: Cancellation status and normalized `run_id`.

    Raises:
        HTTPException: If `run_id` is invalid after sanitization.
    """
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", (run_id or "").strip())
    if not safe:
        raise HTTPException(status_code=400, detail="invalid run id")
    ok = _set_run_cancel(safe)
    return {"status": "cancelling" if ok else "not_found", "run_id": safe}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Return backend health and opencode dependency readiness status."""
    _reload_config_runtime()
    oc_installed = _opencode_installed()
    oc_bin = _opencode_bin()
    oc_version = _opencode_version(oc_bin) if oc_installed else ""
    return {
        "status": "online" if oc_installed else "degraded",
        "components": {
            "llm": {
                "status": "ok" if oc_installed else "warning",
                "details": f"opencode — {oc_version}" if oc_installed else "opencode no instalado",
                "state": "ready" if oc_installed else "not_loaded",
            }
        },
    }


@app.get("/health/onboarding")
async def onboarding_health():
    """Return onboarding diagnostics across runtime prerequisites.

    Returns:
        dict: Composite readiness state plus per-check remediation actions.
    """
    _reload_config_runtime()
    runtime_root = _runtime_root_dir()
    data_dir = Path(Config.DATA_DIR)
    chroma_dir = runtime_root / "rag_storage"
    mcp_ok = _http_reachable("http://127.0.0.1:8000/")
    op_ok = _opencode_installed()
    checks = [
        {
            "id": "provider",
            "name": "Provider opencode",
            "status": "ok" if op_ok else "error",
            "details": "opencode instalado y detectable" if op_ok else "opencode no está disponible en PATH",
            "action": "Instalar opencode (npm i -g opencode-ai) o configurar HARNESS_OPENCODE_BIN",
        },
        {
            "id": "backend_port",
            "name": "Backend 7719",
            "status": "ok",
            "details": "Servidor backend activo en 7719",
            "action": "Reiniciar backend si no responde",
        },
        {
            "id": "mcp_port",
            "name": "MCP 8000",
            "status": "ok" if mcp_ok else "warning",
            "details": "MCP disponible" if mcp_ok else "MCP no respondió en puerto 8000",
            "action": "Iniciar mcp_server.py para habilitar integraciones",
        },
        {
            "id": "data_dir",
            "name": "Escritura en data/",
            "status": "ok" if data_dir.exists() and os.access(str(data_dir), os.W_OK) else "error",
            "details": f"Ruta: {data_dir}",
            "action": "Verificar permisos de escritura en data/",
        },
        {
            "id": "rag_storage",
            "name": "RAG Chroma",
            "status": "ok" if chroma_dir.exists() else "warning",
            "details": "rag_storage detectado" if chroma_dir.exists() else "No hay índice RAG inicializado",
            "action": "Ingerir PDFs para habilitar búsqueda local",
        },
    ]
    all_ok = all(c["status"] == "ok" for c in checks)
    return {
        "status": "ready" if all_ok else "needs_attention",
        "checks": checks,
        "first_prompt_examples": [
            "Explicame este error de Python y cómo arreglarlo",
            "Refactorizá este archivo y dejalo más claro",
            "Documentá este módulo con docstrings",
        ],
    }


@app.post("/health/onboarding/fix")
async def onboarding_fix(_req: OnboardingActionRequest):
    """Apply minimal runtime bootstrap fixes for onboarding flows."""
    _ensure_harness_dirs()
    (Path(Config.DATA_DIR)).mkdir(parents=True, exist_ok=True)
    _newbie_snapshots_dir()
    return {"status": "ok", "message": "Se aplicaron ajustes base de runtime y carpetas."}


@app.post("/system/mcp/start")
async def start_mcp_server():
    """Start `mcp_server.py` as a detached background process.

    Returns:
        dict: Startup status (`already_running`, `started`, or `starting`).

    Raises:
        HTTPException: If script is missing or process launch fails.
    """
    if _http_reachable("http://127.0.0.1:8000/"):
        return {"status": "already_running"}
    script = _runtime_root_dir() / "mcp_server.py"
    if not script.exists():
        raise HTTPException(status_code=404, detail="mcp_server.py no encontrado")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    try:
        subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(_runtime_root_dir()),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo iniciar MCP: {exc}") from exc
    await asyncio.sleep(0.7)
    return {"status": "started" if _http_reachable("http://127.0.0.1:8000/") else "starting"}


@app.post("/system/mcp/stop")
async def stop_mcp_server():
    """Stop MCP server processes and report final reachability state."""
    if os.name == "nt":
        cmd = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -like '*mcp_server.py*' -or $_.Name -eq 'mcp_server.exe' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    else:
        subprocess.run(["pkill", "-f", "mcp_server.py"], capture_output=True, text=True, timeout=5, check=False)
    await asyncio.sleep(0.3)
    return {"status": "stopped" if not _http_reachable("http://127.0.0.1:8000/") else "running"}


@app.post("/llamacpp/start")
async def llamacpp_start():
    """Ensure local llama.cpp server is running and reachable."""
    ok, reason = _ensure_llamacpp_server_started(timeout_sec=40)
    return {"status": "ready" if ok else "error", "detail": reason, "url": _llamacpp_server_url()}


@app.post("/llamacpp/stop")
async def llamacpp_stop():
    """Stop local llama.cpp server and return resulting status."""
    _stop_llamacpp_server()
    await asyncio.sleep(0.3)
    alive = _http_reachable(_llamacpp_server_url(), timeout=1.0)
    return {"status": "running" if alive else "stopped", "url": _llamacpp_server_url()}


@app.get("/opencode/warmup")
async def opencode_warmup_status():
    """Return current opencode warmup task state snapshot."""
    with _OPENCODE_WARMUP_LOCK:
        return dict(_OPENCODE_WARMUP_STATE)


@app.post("/opencode/warmup")
async def opencode_warmup_run():
    """Execute a single opencode warmup pass unless already running."""
    with _OPENCODE_WARMUP_LOCK:
        if _OPENCODE_WARMUP_STATE.get("status") == "running":
            return dict(_OPENCODE_WARMUP_STATE)
        _OPENCODE_WARMUP_STATE.update({
            "status": "running",
            "detail": "warmup en progreso",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": "",
        })
    result = await asyncio.to_thread(_run_opencode_warmup_once)
    with _OPENCODE_WARMUP_LOCK:
        _OPENCODE_WARMUP_STATE.update(result)
        return dict(_OPENCODE_WARMUP_STATE)


@app.get("/newbie/task-templates")
async def newbie_task_templates():
    """Return predefined beginner task templates for quick prompting."""
    return [
        {
            "id": "explain_error",
            "title": "Explicame este error",
            "description": "Diagnóstico en lenguaje simple y pasos concretos",
            "prompt_template": "Tengo este error:\n\n{{error}}\n\nContexto del archivo: {{file_or_module}}\n\nExplicamelo simple y dame pasos para arreglarlo.",
        },
        {
            "id": "refactor_file",
            "title": "Refactorizar archivo",
            "description": "Limpieza segura con foco en legibilidad",
            "prompt_template": "Refactorizá {{file_or_module}} para que sea más legible sin romper comportamiento. Incluí validaciones sugeridas.",
        },
        {
            "id": "document_module",
            "title": "Documentar módulo",
            "description": "Docstrings y explicación práctica",
            "prompt_template": "Documentá {{file_or_module}} con docstrings claras y breves. Explicá supuestos y casos límite.",
        },
        {
            "id": "prepare_pr",
            "title": "Preparar PR",
            "description": "Resumen técnico y checklist de revisión",
            "prompt_template": "Prepará un resumen de PR para {{feature_or_fix}} con cambios, riesgos y plan de test.",
        },
    ]


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/settings")
async def get_settings():
    """Read current `.env` values exposed through the settings API.

    Returns:
        dict: Key-value environment pairs, excluding commented lines.
    """
    env_path = _runtime_root_dir() / ".env"
    if not env_path.exists():
        return {}
    config: dict = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            config[k.strip()] = v.strip()
    return config


@app.post("/settings")
async def save_settings(payload: dict):
    """Persist mutable settings to `.env` while blocking locked keys.

    Parameters:
        payload (dict): Requested key-value updates.

    Returns:
        dict: Operation result and blocked key list.
    """
    safe_payload: dict[str, Any] = {}
    blocked: list[str] = []
    for k, v in (payload or {}).items():
        key = str(k or "")
        if key in _LOCKED_ENV_KEYS:
            blocked.append(key)
            continue
        safe_payload[key] = v
    if safe_payload:
        _upsert_env_settings(safe_payload)
    return {"success": True, "blocked_keys": blocked}


@app.get("/bootstrap/status")
async def bootstrap_status():
    return _BOOTSTRAP_STATE


# ── Local behaviors ───────────────────────────────────────────────────────────

@app.get("/local/behaviors")
async def local_behaviors():
    """Return user-defined local behaviors loaded from disk."""
    return _load_local_behaviors()


# ── Harnesses ─────────────────────────────────────────────────────────────────

@app.get("/harnesses/status")
async def harnesses_status():
    """Return harness installation status and active option metadata."""
    _reload_config_runtime()
    _ensure_harness_dirs()
    meta = _read_harness_meta()
    opencode_bin = _opencode_bin()
    opencode_installed = _opencode_installed()
    opencode_meta = (meta.get("opencode") or {}) if isinstance(meta, dict) else {}
    opencode_version = _opencode_version(opencode_bin) or str(opencode_meta.get("version") or "")
    return {
        "active": "opencode",
        "options": [
            {
                "id": "opencode",
                "label": "opencode",
                "installed": opencode_installed,
                "version": opencode_version,
                "path": opencode_bin,
            }
        ],
    }


@app.post("/harnesses/install")
async def harnesses_install(req: HarnessInstallRequest):
    """Install supported harness tooling (`opencode`) via npm.

    Parameters:
        req (HarnessInstallRequest): Requested harness installation payload.

    Returns:
        dict: Installation result, detected binary, and version metadata.

    Raises:
        HTTPException: For unsupported harness IDs, missing npm, timeout, or
        installation/discovery failures.
    """
    _reload_config_runtime()
    _ensure_harness_dirs()
    harness_id = (req.harness_id or "").strip().lower()
    if harness_id != "opencode":
        raise HTTPException(400, f"Solo se puede instalar 'opencode' en esta versión. Solicitado: {harness_id}")

    npm = _npm_bin()
    if not npm:
        raise HTTPException(500, "npm no encontrado. Instalá Node.js primero.")

    try:
        proc = subprocess.run(
            [npm, "install", "-g", "opencode-ai"],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "Timeout instalando opencode (300s)")
    except Exception as e:
        raise HTTPException(500, f"Error al ejecutar npm: {e}")

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "")[:800]
        raise HTTPException(500, f"No se pudo instalar opencode: {detail}")

    op_bin = _opencode_bin()
    if not op_bin:
        raise HTTPException(500, "opencode instalado pero no encontrado en PATH. Reiniciá el terminal.")

    version = _opencode_version(op_bin)
    meta = _read_harness_meta()
    meta["opencode"] = {"version": version, "path": op_bin, "installed_at": datetime.now().isoformat()}
    _write_harness_meta(meta)

    return {"status": "ok", "path": op_bin, "version": version}


# ── Dev log ───────────────────────────────────────────────────────────────────

@app.get("/dev/log")
async def dev_get_log(lines: int = 300):
    p = _log_path()
    if not p.exists():
        return {"lines": [], "path": str(p), "exists": False}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        all_lines = text.splitlines()
        tail = all_lines[-lines:]
        return {"lines": tail, "path": str(p), "exists": True, "total": len(all_lines)}
    except Exception as exc:
        return {"lines": [], "path": str(p), "exists": True, "error": str(exc)}


@app.get("/dev/log/stream")
async def dev_log_stream(lines: int = 100):
    p = _log_path()

    async def _gen():
        last_size = 0
        if p.exists():
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                tail = text.splitlines()[-lines:]
                for ln in tail:
                    yield f"data: {json.dumps({'line': ln, 'init': True})}\n\n"
                last_size = p.stat().st_size
            except Exception:
                pass
        while True:
            await asyncio.sleep(1.0)
            if not p.exists():
                continue
            try:
                size = p.stat().st_size
                if size <= last_size:
                    if size < last_size:
                        last_size = 0
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
                all_lines = text.splitlines()
                prev_count = len(p.read_bytes()[:last_size].decode("utf-8", errors="replace").splitlines())
                new_lines = all_lines[prev_count:]
                for ln in new_lines:
                    yield f"data: {json.dumps({'line': ln, 'init': False})}\n\n"
                last_size = size
            except Exception:
                pass

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Traces ────────────────────────────────────────────────────────────────────

@app.get("/dev/traces")
async def dev_list_traces(limit: int = 30):
    runs_dir = _runs_dir()
    files = sorted(runs_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    result = []
    for f in files[:limit]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            events = data.get("events") or []
            error_events = [e for e in events if e.get("type") == "error"]
            result.append({
                "run_id": data.get("run_id", f.stem),
                "conversation_id": data.get("conversation_id", ""),
                "mode": data.get("mode", "normal"),
                "mode_effective": data.get("mode_effective", ""),
                "started_at": data.get("started_at", ""),
                "finished_at": data.get("finished_at", ""),
                "event_count": len(events),
                "error_count": len(error_events),
                "errors": [e.get("text", "") for e in error_events],
                "input_preview": (data.get("input") or {}).get("message", "")[:120],
                "timing": data.get("timing") or {},
            })
        except Exception:
            continue
    return result


@app.get("/dev/traces/{run_id}")
async def dev_get_trace(run_id: str):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", run_id)[:64]
    p = _runs_dir() / f"{safe}.json"
    if not p.exists():
        raise HTTPException(404, "Trace not found")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.delete("/dev/traces")
async def dev_clear_traces():
    runs_dir = _runs_dir()
    count = 0
    for f in runs_dir.glob("*.json"):
        try:
            f.unlink()
            count += 1
        except Exception:
            pass
    return {"deleted": count}


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/newbie/profile")
async def newbie_get_profile():
    return _load_json_file(
        _newbie_profile_path(),
        {"language": "es", "experience_level": "newbie", "detail_level": "simple"},
    )


@app.post("/newbie/profile")
async def newbie_save_profile(payload: dict[str, Any]):
    existing = _load_json_file(_newbie_profile_path(), {})
    next_payload = {**existing, **(payload or {})}
    _save_json_file(_newbie_profile_path(), next_payload)
    return {"status": "ok", "profile": next_payload}


@app.post("/newbie/snapshot")
async def newbie_snapshot(payload: dict[str, Any]):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = _newbie_snapshots_dir() / f"{ts}.json"
    _save_json_file(p, payload or {})
    return {"status": "ok", "snapshot": str(p)}


@app.get("/health/center")
async def health_center():
    _reload_config_runtime()
    op_bin = _opencode_bin()
    op_version = _opencode_version(op_bin) if op_bin else ""
    boot = _BOOTSTRAP_STATE.copy()
    traces = await dev_list_traces(limit=10)
    errors = [t for t in traces if int(t.get("error_count") or 0) > 0][:5]
    return {
        "provider": "opencode",
        "model_alias": os.getenv("LLAMACPP_MODEL_ALIAS", ""),
        "opencode_version": op_version,
        "bootstrap": boot,
        "rag_index_ready": (_runtime_root_dir() / "rag_storage").exists(),
        "recent_errors": [
            {
                "run_id": e.get("run_id"),
                "message": (e.get("errors") or [""])[0],
                "started_at": e.get("started_at"),
            }
            for e in errors
        ],
    }

@app.get("/stats")
async def stats():
    try:
        import psutil
        base = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_total_gb": round(psutil.virtual_memory().total / 1024**3, 1),
            "ram_used_gb": round(psutil.virtual_memory().used / 1024**3, 1),
            "ram_percent": psutil.virtual_memory().percent,
        }
        traces = await dev_list_traces(limit=200)
        success = [t for t in traces if int(t.get("error_count") or 0) == 0]
        failed = [t for t in traces if int(t.get("error_count") or 0) > 0]
        durations: list[float] = []
        for t in traces:
            try:
                a = datetime.fromisoformat(str(t.get("started_at") or ""))
                b = datetime.fromisoformat(str(t.get("finished_at") or ""))
                durations.append(max((b - a).total_seconds(), 0))
            except Exception:
                continue
        newbie = {
            "total_runs": len(traces),
            "successful_runs": len(success),
            "failed_runs": len(failed),
            "success_rate": round((len(success) / len(traces)) * 100, 1) if traces else 0.0,
            "time_to_first_success_sec": round(durations[0], 1) if durations and success else None,
            "avg_run_duration_sec": round(sum(durations) / len(durations), 1) if durations else None,
        }
        _save_json_file(_newbie_metrics_path(), newbie)
        return {**base, "newbie_metrics": newbie}
    except Exception:
        return {}


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "online", "service": "UNLZ Agent Server (opencode)", "health": "/health"}


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("AGENT_SERVER_PORT", "7719"))
    print(f"[UNLZ Agent Server] Starting on port {port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
