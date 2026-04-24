"""
UNLZ Agent Server — replaces n8n.
FastAPI + OpenAI-compatible tool-calling loop + SSE streaming.
Supports llamacpp / ollama / openai as LLM providers.
"""
from __future__ import annotations

import asyncio
import http.client
import hashlib
import json
import os
import re
import signal
import shutil
import sys
import tempfile
import time
import threading
import uuid
import zipfile
from datetime import datetime
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

# ── Redirect stdout/stderr to log when not running in a real terminal ─────────
# Covers: Tauri subprocess (CREATE_NO_WINDOW), background launch, etc.
# In PyInstaller one-file mode, __file__ may resolve to a transient extraction
# directory. Use runtime/install root first and gracefully fallback.
def _bootstrap_runtime_root() -> str:
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
    root = _bootstrap_runtime_root()
    return os.path.join(root, "agent_server.log")


def _install_stdio_file_log() -> None:
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
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Project root on sys.path
sys.path.insert(0, str(Path(__file__).parent))


def _runtime_root_dir() -> Path:
    override = (os.getenv("UNLZ_PROJECT_ROOT") or "").strip()
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        # Installed layout: <install_dir>\binaries\agent_server.exe
        if exe_dir.name.lower() == "binaries":
            return exe_dir.parent
        return exe_dir
    return Path(__file__).parent


load_dotenv(dotenv_path=_runtime_root_dir() / ".env")

from config import Config


def _http_reachable(url: str, timeout: float = 1.5) -> bool:
    """Fast local HTTP probe that avoids system proxy hangs on Windows."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(parsed.hostname, port, timeout=timeout)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            _ = resp.read(32)  # drain a tiny payload to complete the request
            # llama-server returns 503 while loading the model; that still means
            # the service is up and reachable.
            return 100 <= resp.status < 600
        finally:
            conn.close()
    except Exception:
        return False


def _http_get_text(url: str, timeout: float = 1.5) -> tuple[int, str]:
    """Tiny HTTP GET helper returning status and body text (no proxy side effects)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return 0, ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parsed.hostname, port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        raw = resp.read()
        try:
            txt = raw.decode("utf-8", errors="ignore")
        except Exception:
            txt = ""
        return int(resp.status), txt
    except Exception:
        return 0, ""
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _llamacpp_api_healthy(timeout: float = 1.5) -> bool:
    """
    Strict llama.cpp API probe.
    `/health` can return 200 for non-llama services bound to the same port,
    so validate `/v1/models` JSON shape.
    """
    base = f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}"
    status, body = _http_get_text(f"{base}/v1/models", timeout=timeout)
    if not (200 <= status < 300) or not body.strip():
        return False
    try:
        data = json.loads(body)
    except Exception:
        return False
    return isinstance(data, dict) and isinstance(data.get("data"), list)


def _reload_config_runtime() -> None:
    """Refresh Config class attributes from current process env/.env."""
    load_dotenv(dotenv_path=_env_path(), override=True)
    Config.VECTOR_DB_PROVIDER = os.getenv("VECTOR_DB_PROVIDER", "chroma").lower()
    Config.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
    Config.AGENT_LANGUAGE = os.getenv("AGENT_LANGUAGE", "en").lower()
    Config.AGENT_HARNESS = os.getenv("AGENT_HARNESS", "native").lower()
    Config.HARNESS_LITTLE_CODER_DIR = os.getenv("HARNESS_LITTLE_CODER_DIR", "")
    Config.HARNESS_CLAUDE_CODE_BIN = os.getenv("HARNESS_CLAUDE_CODE_BIN", "")
    Config.HARNESS_OPENCODE_BIN = os.getenv("HARNESS_OPENCODE_BIN", "")
    Config.MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
    Config.AGENT_EXECUTION_MODE = os.getenv("AGENT_EXECUTION_MODE", "confirm").lower()
    Config.AGENT_COMMAND_TIMEOUT_SEC = int(os.getenv("AGENT_COMMAND_TIMEOUT_SEC", "60"))
    Config.AGENT_COMMAND_MAX_OUTPUT = int(os.getenv("AGENT_COMMAND_MAX_OUTPUT", "4000"))
    Config.WEB_SEARCH_ENGINE = os.getenv("WEB_SEARCH_ENGINE", "google").lower()
    Config.SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    Config.SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    Config.OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    Config.OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")
    Config.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    Config.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    Config.LLAMACPP_EXECUTABLE = os.getenv("LLAMACPP_EXECUTABLE", "")
    Config.LLAMACPP_MODEL_PATH = os.getenv("LLAMACPP_MODEL_PATH", "")
    Config.LLAMACPP_HOST = os.getenv("LLAMACPP_HOST", "127.0.0.1")
    Config.LLAMACPP_PORT = int(os.getenv("LLAMACPP_PORT", "8080"))
    Config.LLAMACPP_CONTEXT_SIZE = int(os.getenv("LLAMACPP_CONTEXT_SIZE", "32768"))
    Config.LLAMACPP_N_GPU_LAYERS = int(os.getenv("LLAMACPP_N_GPU_LAYERS", "999"))
    Config.LLAMACPP_FLASH_ATTN = os.getenv("LLAMACPP_FLASH_ATTN", "true").lower() == "true"
    Config.LLAMACPP_MODEL_ALIAS = os.getenv("LLAMACPP_MODEL_ALIAS", "local-model")
    Config.LLAMACPP_CACHE_TYPE_K = os.getenv("LLAMACPP_CACHE_TYPE_K", "")
    Config.LLAMACPP_CACHE_TYPE_V = os.getenv("LLAMACPP_CACHE_TYPE_V", "")
    Config.LLAMACPP_EXTRA_ARGS = os.getenv("LLAMACPP_EXTRA_ARGS", "")
    Config.LLAMACPP_MODELS_DIR = os.getenv("LLAMACPP_MODELS_DIR", "")
    Config.LLAMACPP_AUTO_START = os.getenv("LLAMACPP_AUTO_START", "true").lower() in ("1", "true", "yes", "on")
    Config.LLAMACPP_AUTO_START_COOLDOWN_SEC = int(os.getenv("LLAMACPP_AUTO_START_COOLDOWN_SEC", "12"))
    Config.N8N_ENABLED = os.getenv("N8N_ENABLED", "true").lower() == "true"
    Config.N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://127.0.0.1:5678/webhook/chat")


def _slug_alias(name: str) -> str:
    alias = (name or "local-model").strip().lower()
    for ch in ("_", ".", " "):
        alias = alias.replace(ch, "-")
    return alias


def _env_path() -> Path:
    return _runtime_root_dir() / ".env"


def _upsert_env_settings(payload: dict) -> None:
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


def _llamacpp_install_root() -> Path:
    override = (os.getenv("LLAMACPP_INSTALL_DIR") or "").strip()
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return _runtime_root_dir() / "llama.cpp"
    # Dev layout: keep local tooling under the project root.
    return Path(Config.BASE_DIR) / "tools" / "llama.cpp"


def _llamacpp_install_meta_path() -> Path:
    return _llamacpp_install_root() / "install.json"


def _ensure_llamacpp_default_dirs() -> None:
    root = _llamacpp_install_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "models").mkdir(parents=True, exist_ok=True)


def _read_llamacpp_install_meta() -> dict:
    p = _llamacpp_install_meta_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_llamacpp_install_meta(data: dict) -> None:
    root = _llamacpp_install_root()
    root.mkdir(parents=True, exist_ok=True)
    _llamacpp_install_meta_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_llama_server_executable(root: Path) -> Optional[Path]:
    try:
        candidates = list(root.rglob("llama-server.exe"))
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]
    except Exception:
        return None


def _find_first_gguf(root: Path) -> Optional[Path]:
    try:
        g = list(root.rglob("*.gguf"))
        if not g:
            return None
        g.sort(key=lambda p: p.stat().st_size, reverse=True)
        return g[0]
    except Exception:
        return None


def _scan_gguf_models() -> list[dict]:
    """Return discovered GGUF candidates from configured/common roots."""
    search_roots: set[Path] = set()

    def add_if_exists(p: Path) -> None:
        try:
            if p.exists():
                search_roots.add(p.resolve())
        except (OSError, PermissionError):
            pass

    models_dir = Config.LLAMACPP_MODELS_DIR or os.getenv("LLAMACPP_MODELS_DIR", "")
    if models_dir:
        add_if_exists(Path(models_dir))

    if Config.LLAMACPP_MODEL_PATH:
        p = Path(Config.LLAMACPP_MODEL_PATH)
        add_if_exists(p.parent.parent)
        add_if_exists(p.parent)

    userprofile = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    for rel in ("Models\\llamacpp", "Models", "models\\llamacpp", "models"):
        if userprofile:
            add_if_exists(Path(userprofile) / rel)

    try:
        add_if_exists(Path.home() / "Models" / "llamacpp")
        add_if_exists(Path.home() / "Models")
    except Exception:
        pass

    models: list[dict] = []
    seen: set[str] = set()
    for root in search_roots:
        try:
            for gguf in root.rglob("*.gguf"):
                key = str(gguf).lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    size_gb = round(gguf.stat().st_size / 1024 ** 3, 1)
                except OSError:
                    size_gb = 0.0
                stem = gguf.stem
                alias = _slug_alias(stem)
                models.append({
                    "path": str(gguf),
                    "name": gguf.name,
                    "stem": stem,
                    "alias": alias,
                    "size_gb": size_gb,
                    "folder": gguf.parent.name,
                })
        except (PermissionError, OSError):
            continue
    models.sort(key=lambda m: (m["folder"], m["name"]))
    return models


def _load_local_behaviors() -> list[dict]:
    """
    Load local-only behaviors from DATA_DIR/local_behaviors.json.
    This file is intended for machine-local profiles (excluded from git).
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


def _harness_install_root() -> Path:
    return _runtime_root_dir() / "data" / ".unlz_internal" / "harnesses"


def _harness_meta_path() -> Path:
    return _harness_install_root() / "harnesses.json"


def _ensure_harness_dirs() -> None:
    _harness_install_root().mkdir(parents=True, exist_ok=True)


def _read_harness_meta() -> dict:
    p = _harness_meta_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_harness_meta(data: dict) -> None:
    _ensure_harness_dirs()
    _harness_meta_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _little_coder_install_dir() -> Path:
    cfg_dir = (os.getenv("HARNESS_LITTLE_CODER_DIR") or getattr(Config, "HARNESS_LITTLE_CODER_DIR", "") or "").strip()
    if cfg_dir:
        return Path(cfg_dir)
    return _harness_install_root() / "little-coder"


def _little_coder_installed() -> bool:
    d = _little_coder_install_dir()
    return d.exists() and d.is_dir() and (d / "README.md").exists()


def _claude_code_bin() -> str:
    configured = (os.getenv("HARNESS_CLAUDE_CODE_BIN") or getattr(Config, "HARNESS_CLAUDE_CODE_BIN", "") or "").strip()
    if configured and Path(configured).exists():
        return configured
    detected = shutil.which("claude")
    return detected or ""


def _claude_code_version(bin_path: str) -> str:
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


def _claude_code_installed() -> bool:
    return bool(_claude_code_bin())


def _which_any(candidates: list[str]) -> str:
    for name in candidates:
        p = shutil.which(name)
        if p:
            return p
    return ""


def _npm_bin() -> str:
    found = _which_any(["npm", "npm.cmd", "npm.exe"])
    if found:
        return found
    # Common Windows Node.js install locations
    roots = [
        os.getenv("ProgramFiles", ""),
        os.getenv("ProgramFiles(x86)", ""),
        os.getenv("LocalAppData", ""),
    ]
    for root in roots:
        if not root:
            continue
        p = Path(root) / "nodejs" / "npm.cmd"
        if p.exists():
            return str(p)
    return ""


def _opencode_bin() -> str:
    configured = (os.getenv("HARNESS_OPENCODE_BIN") or getattr(Config, "HARNESS_OPENCODE_BIN", "") or "").strip()
    if configured and Path(configured).exists():
        return configured
    detected = _which_any(["opencode", "opencode.cmd", "opencode.exe"])
    if detected:
        return detected
    # npm global bin on Windows (often not in PATH for packaged apps)
    appdata = os.getenv("APPDATA", "")
    if appdata:
        for name in ("opencode.cmd", "opencode.exe", "opencode"):
            p = Path(appdata) / "npm" / name
            if p.exists():
                return str(p)
    return ""


def _opencode_version(bin_path: str) -> str:
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
    return bool(_opencode_bin())


def _github_latest_llamacpp_release() -> dict:
    req = Request(
        "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "unlz-agent"},
    )
    with urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pick_windows_asset(assets: list[dict]) -> Optional[dict]:
    best = None
    best_score = -10**9
    for a in assets or []:
        name = (a.get("name") or "").lower()
        if not name.endswith(".zip") or "win" not in name:
            continue
        score = 0
        if "win" in name:
            score += 100
        if "cpu" in name:
            score += 30
        if "x64" in name:
            score += 15
        if "cuda" in name or "cu" in name:
            score -= 15
        if "vulkan" in name:
            score -= 10
        if "arm" in name:
            score -= 30
        if score > best_score:
            best_score = score
            best = a
    return best


def _collect_vram_stats() -> dict:
    """
    Returns VRAM aggregate and per-GPU stats when available.
    Uses nvidia-smi when present; otherwise returns zeros + empty gpu list.
    """
    gpus = []
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if proc.returncode == 0:
            for line in (proc.stdout or "").splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 3:
                    continue
                name = parts[0]
                total_mb = float(parts[1] or 0)
                used_mb = float(parts[2] or 0)
                total_gb = round(total_mb / 1024, 2)
                used_gb = round(used_mb / 1024, 2)
                percent = round((used_mb / total_mb) * 100, 1) if total_mb else 0.0
                gpus.append({
                    "name": name,
                    "total_gb": total_gb,
                    "used_gb": used_gb,
                    "percent": percent,
                })
    except Exception:
        pass

    vram_total_gb = round(sum(g["total_gb"] for g in gpus), 2)
    vram_used_gb = round(sum(g["used_gb"] for g in gpus), 2)
    vram_percent = round((vram_used_gb / vram_total_gb) * 100, 1) if vram_total_gb else 0.0
    return {
        "vram_total_gb": vram_total_gb,
        "vram_used_gb": vram_used_gb,
        "vram_percent": vram_percent,
        "gpus": gpus,
    }


def _is_research_request(text: str) -> bool:
    t = (text or "").lower()
    keywords = (
        "investiga", "investigar", "busca", "buscar", "google", "web",
        "internet", "noticias", "último", "ultima", "latest", "research",
    )
    return any(k in t for k in keywords)


def _is_action_request(text: str) -> bool:
    t = (text or "").lower()
    keywords = (
        "crea", "crear", "creame", "haz", "hace", "ejecuta", "ejecutar", "corre", "run",
        "borra", "elimina", "move", "mueve", "rename", "renombra", "mkdir",
    )
    return any(k in t for k in keywords)


def _tools_for_message(text: str) -> list[dict]:
    # Expose terminal execution only for explicit action intents.
    if _is_action_request(text):
        return TOOLS
    return [t for t in TOOLS if t.get("function", {}).get("name") != "run_windows_command"]


def _web_search(query: str, max_results: int = 4) -> str:
    q = (query or "").strip()
    if not q:
        return "Missing query."

    n = max(1, min(int(max_results or 4), 8))
    engine = (os.getenv("WEB_SEARCH_ENGINE", Config.WEB_SEARCH_ENGINE) or "google").lower()
    errors: list[str] = []
    provider_latency_ms: dict[str, int] = {}
    collected: list[dict] = []

    def search_google() -> list[dict]:
        start = time.perf_counter()
        # Optional dependency: googlesearch-python
        from googlesearch import search  # type: ignore
        items = []
        for idx, url in enumerate(search(q, num_results=n)):
            if idx >= n:
                break
            items.append({"title": "Google result", "body": "", "href": url})
        provider_latency_ms["google"] = int((time.perf_counter() - start) * 1000)
        return items

    def search_duckduckgo() -> list[dict]:
        start = time.perf_counter()
        # Prefer the renamed package when available, keep backward compatibility.
        try:
            from ddgs import DDGS  # type: ignore
        except Exception:
            from duckduckgo_search import DDGS  # type: ignore
        items = list(DDGS().text(q, max_results=n) or [])
        provider_latency_ms["duckduckgo"] = int((time.perf_counter() - start) * 1000)
        return items

    def search_serpapi() -> list[dict]:
        start = time.perf_counter()
        key = (os.getenv("SERPAPI_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("SERPAPI_API_KEY missing")
        endpoint = f"https://serpapi.com/search.json?engine=google&q={q}&api_key={key}&num={n}"
        req = Request(endpoint, headers={"User-Agent": "unlz-agent"})
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = []
        for item in (data.get("organic_results") or [])[:n]:
            out.append({
                "title": item.get("title") or "SerpAPI result",
                "body": item.get("snippet") or "",
                "href": item.get("link") or "",
            })
        provider_latency_ms["serpapi"] = int((time.perf_counter() - start) * 1000)
        return out

    def search_bing_api() -> list[dict]:
        start = time.perf_counter()
        key = (os.getenv("BING_API_KEY") or "").strip()
        endpoint = (os.getenv("BING_API_ENDPOINT") or "https://api.bing.microsoft.com/v7.0/search").strip()
        if not key:
            raise RuntimeError("BING_API_KEY missing")
        req = Request(
            f"{endpoint}?q={q}&count={n}",
            headers={"Ocp-Apim-Subscription-Key": key, "User-Agent": "unlz-agent"},
        )
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = []
        for item in (data.get("webPages", {}).get("value") or [])[:n]:
            out.append({
                "title": item.get("name") or "Bing result",
                "body": item.get("snippet") or "",
                "href": item.get("url") or "",
            })
        provider_latency_ms["bing"] = int((time.perf_counter() - start) * 1000)
        return out

    strategies = []
    if engine == "google":
        strategies = [("google", search_google), ("duckduckgo", search_duckduckgo), ("serpapi", search_serpapi), ("bing", search_bing_api)]
    elif engine == "duckduckgo":
        strategies = [("duckduckgo", search_duckduckgo), ("google", search_google), ("serpapi", search_serpapi), ("bing", search_bing_api)]
    elif engine == "serpapi":
        strategies = [("serpapi", search_serpapi), ("google", search_google), ("duckduckgo", search_duckduckgo)]
    elif engine == "bing":
        strategies = [("bing", search_bing_api), ("google", search_google), ("duckduckgo", search_duckduckgo)]
    elif engine in ("fusion", "auto"):
        strategies = [("google", search_google), ("duckduckgo", search_duckduckgo), ("serpapi", search_serpapi), ("bing", search_bing_api)]
    else:
        strategies = [("google", search_google), ("duckduckgo", search_duckduckgo)]

    for name, fn in strategies:
        try:
            results = fn()
            _record_web_provider(name, ok=True, latency_ms=provider_latency_ms.get(name, 0))
            if results:
                for r in results[:n]:
                    collected.append({
                        "provider": name,
                        "title": r.get("title", "Result"),
                        "body": r.get("body", ""),
                        "href": r.get("href", ""),
                    })
                if engine not in ("fusion", "auto"):
                    break
        except Exception as e:
            _record_web_provider(name, ok=False, err=str(e))
            errors.append(f"{name}: {e}")

    if collected:
        merged: list[dict] = []
        seen: set[str] = set()
        for r in collected:
            href = (r.get("href") or "").strip()
            if not href or href in seen:
                continue
            seen.add(href)
            merged.append(r)
            if len(merged) >= n:
                break
        lines = []
        for r in merged:
            lines.append(
                f"**{r.get('title', 'Result')}**\n{r.get('body', '')}\n{r.get('href', '')}\nFuente: {r.get('provider')}"
            )
        if provider_latency_ms:
            lines.append(
                "\n---\nSearch providers latency (ms): "
                + ", ".join(f"{k}={v}" for k, v in provider_latency_ms.items())
            )
        return "\n\n".join(lines)

    if errors:
        return f"WEB_SEARCH_UNAVAILABLE: No web results found. ({'; '.join(errors[:2])})"
    return "WEB_SEARCH_UNAVAILABLE: No web results found."


def _agent_limits() -> dict:
    return {
        "max_iterations": max(1, min(int(os.getenv("AGENT_MAX_ITERATIONS", "8")), 20)),
        "max_tool_calls": max(1, min(int(os.getenv("AGENT_MAX_TOOL_CALLS", "20")), 100)),
        "max_wall_sec": max(5, min(int(os.getenv("AGENT_MAX_WALL_TIME_SEC", "180")), 1800)),
        "tool_timeout_sec": max(1, min(int(os.getenv("AGENT_TOOL_TIMEOUT_SEC", "45")), 300)),
    }


def _runs_dir() -> Path:
    p = Path(Config.DATA_DIR) / "runs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _snapshots_dir() -> Path:
    p = Path(Config.DATA_DIR) / "snapshots"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _trace_path(run_id: str) -> Path:
    return _runs_dir() / f"{run_id}.json"


def _persist_trace(run_id: str, trace: dict) -> None:
    _trace_path(run_id).write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")


_active_run_cancels: dict[str, asyncio.Event] = {}
_active_run_cancels_lock = threading.Lock()


def _register_run_cancel(run_id: str) -> asyncio.Event:
    ev = asyncio.Event()
    with _active_run_cancels_lock:
        _active_run_cancels[run_id] = ev
    return ev


def _unregister_run_cancel(run_id: str) -> None:
    with _active_run_cancels_lock:
        _active_run_cancels.pop(run_id, None)


def _set_run_cancel(run_id: str) -> bool:
    with _active_run_cancels_lock:
        ev = _active_run_cancels.get(run_id)
    if not ev:
        return False
    try:
        ev.set()
    except Exception:
        return False
    return True


def _snapshot_path(conversation_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", (conversation_id or "").strip())[:80] or "default"
    return _snapshots_dir() / f"{safe}.json"


def _save_snapshot(conversation_id: str, payload: dict) -> None:
    if not (conversation_id or "").strip():
        return
    data = {
        "conversation_id": conversation_id,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        **payload,
    }
    _snapshot_path(conversation_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_snapshot(conversation_id: str) -> dict:
    p = _snapshot_path(conversation_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _list_snapshots() -> list[dict]:
    out: list[dict] = []
    for p in sorted(_snapshots_dir().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "conversation_id": rec.get("conversation_id") or p.stem,
                "saved_at": rec.get("saved_at") or "",
                "objective": rec.get("objective") or "",
                "stage_count": len(rec.get("stages") or []),
                "file": str(p),
            })
        except Exception:
            continue
    return out


def _memory_path() -> Path:
    p = Path(Config.DATA_DIR) / "memory.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _append_memory(conv_id: str, folder_id: str, role: str, content: str) -> None:
    if not content.strip():
        return
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "conversation_id": conv_id,
        "folder_id": folder_id,
        "role": role,
        "content": content[:4000],
    }
    with _memory_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _memory_decay_score(ts_iso: str) -> float:
    try:
        dt = datetime.fromisoformat(ts_iso)
        hours = max(0.0, (datetime.now() - dt).total_seconds() / 3600.0)
        return 1.0 / (1.0 + (hours / 24.0))
    except Exception:
        return 0.1


def _retrieve_memory(query: str, conv_id: str, folder_id: str, top_k: int = 5) -> list[str]:
    p = _memory_path()
    if not p.exists():
        return []
    q_terms = [t for t in re.split(r"\s+", (query or "").lower().strip()) if len(t) >= 3][:12]
    if not q_terms:
        return []
    rows: list[tuple[float, str]] = []
    try:
        for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines()[-1000:]:
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except Exception:
                continue
            txt = str(rec.get("content") or "")
            low = txt.lower()
            hits = sum(low.count(t) for t in q_terms)
            if hits <= 0:
                continue
            score = float(hits)
            if conv_id and str(rec.get("conversation_id") or "") == conv_id:
                score += 4.0
            if folder_id and str(rec.get("folder_id") or "") == folder_id:
                score += 2.0
            score *= _memory_decay_score(str(rec.get("ts") or ""))
            rows.append((score, txt))
    except Exception:
        return []
    rows.sort(key=lambda x: x[0], reverse=True)
    out: list[str] = []
    for _, t in rows[:max(1, min(top_k, 10))]:
        if t not in out:
            out.append(t[:500])
    return out


_CONNECTOR_METRICS: dict[str, Any] = {
    "web_search": {"providers": {}},
    "tools": {},
}

_TASK_ROUTER_DEFAULT = {
    "version": 1,
    "areas": {
        "notificaciones": {
            "primary_model": "gemma-3-4b-it-q4_0",
            "fallback_models": ["qwen3.6-35b-a3b-unsloth-q4_k_m"],
            "profile": "gemma3_4b_q40_jsonfmt",
            "keywords": ["notificacion", "cedula", "juzgado", "expediente", "traslado", "proveido"],
        },
        "resumen_asignacion": {
            "primary_model": "qwen3.6-35b-a3b-unsloth-q4_k_m",
            "fallback_models": ["gemma-3-4b-it-q4_0"],
            "profile": "qwen36_35b_unsloth_q4km_tuned_cache_jsonfmt",
            "keywords": ["resumen", "asignacion", "pendiente", "situacion", "estado actual"],
        },
        "metadata": {
            "primary_model": "gemma-3-4b-it-q4_0",
            "fallback_models": ["qwen3.6-35b-a3b-unsloth-q4_k_m"],
            "profile": "gemma3_4b_q40_jsonfmt",
            "keywords": ["metadata", "campos", "normalizar", "partes", "dominio", "monto", "hechos"],
        },
        "jurisdiccion": {
            "primary_model": "gemma-3-4b-it-q4_0",
            "fallback_models": ["qwen3.6-35b-a3b-unsloth-q4_k_m"],
            "profile": "gemma3_4b_q40_jsonfmt",
            "keywords": ["jurisdiccion", "fuero", "camara", "competencia", "procesal"],
        },
        "ocr": {
            "primary_model": "qwen3.6-35b-a3b-unsloth-q4_k_m",
            "fallback_models": ["gemma-3-4b-it-q4_0"],
            "profile": "qwen36_35b_unsloth_q4km_tuned_cache_jsonfmt",
            "keywords": ["ocr", "scan", "escaneado", "texto sucio", "ilegible", "pdf imagen"],
        },
        "rag": {
            "primary_model": "gemma-3-4b-it-q4_0",
            "fallback_models": ["qwen3.6-35b-a3b-unsloth-q4_k_m"],
            "profile": "gemma3_4b_q40_jsonfmt",
            "keywords": ["rag", "fuentes", "base documental", "conocimiento local", "documentos"],
        },
        "dev_codigo": {
            "primary_model": "qwen3.6-35b-a3b-unsloth-q4_k_m",
            "fallback_models": ["gemma-3-4b-it-q4_0"],
            "profile": "qwen36_35b_unsloth_q4km_tuned_cache_jsonfmt",
            "keywords": [
                "codigo", "código", "programa", "script", "frontend", "backend", "api",
                "html", "css", "javascript", "typescript", "python", "web", "pagina", "página",
                "react", "vite", "next", "crear web", "crear app", "crear proyecto"
            ],
        },
        "chat_general": {
            "primary_model": "gemma-3-4b-it-q4_0",
            "fallback_models": ["qwen3.6-35b-a3b-unsloth-q4_k_m"],
            "profile": "gemma3_4b_q40_jsonfmt",
            "keywords": ["hola", "ayuda", "consulta", "explicame", "que podes hacer"],
        },
        "docgen_informe": {
            "primary_model": "gemma-3-4b-it-q4_0",
            "fallback_models": ["qwen3.6-35b-a3b-unsloth-q4_k_m"],
            "profile": "gemma3_4b_q40_jsonfmt",
            "keywords": ["informe", "docgen", "redacta", "borrador", "dictamen", "seccion"],
        },
        "vlm": {
            "primary_model": "qwen2.5-vl:7b",
            "fallback_models": ["gemma-3-4b-it-q4_0"],
            "profile": "vlm_quality",
            "keywords": ["imagen", "foto", "visual", "pagina escaneada", "clasificar pagina", "captura"],
        },
    },
}


def _telemetry_enabled() -> bool:
    raw = (os.getenv("AGENT_TELEMETRY_OPT_IN", "false") or "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _telemetry_path() -> Path:
    p = Path(Config.DATA_DIR) / "telemetry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _emit_telemetry(event: str, payload: dict) -> None:
    if not _telemetry_enabled():
        return
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        **(payload or {}),
    }
    with _telemetry_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _devlog_trace_enabled() -> bool:
    raw = (os.getenv("AGENT_DEVLOG_TRACE", "true") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _devlog_emit_trace(event: dict[str, Any]) -> None:
    """
    Emit structured trace events to agent_server.log so Dev Log can display
    full process traces in real-time (not only post-run JSON traces).
    """
    if not _devlog_trace_enabled():
        return
    try:
        p = _runtime_root_dir() / "agent_server.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        ev = dict(event or {})
        # Keep log readable and bounded.
        txt = str(ev.get("text") or "")
        if len(txt) > 240:
            ev["text"] = txt[:240] + "…"
        args = ev.get("args")
        if isinstance(args, dict):
            clipped: dict[str, Any] = {}
            for k, v in args.items():
                sv = str(v)
                clipped[k] = (sv[:220] + "…") if len(sv) > 220 else v
            ev["args"] = clipped
        line = "[trace] " + json.dumps(ev, ensure_ascii=False)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # Never break runtime due to debug logging.
        pass


def _task_router_path() -> Path:
    data_dir = Path(Config.DATA_DIR)
    internal_dir = data_dir / ".unlz_internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    p = internal_dir / "task_router.json"
    legacy = data_dir / "task_router.json"
    if legacy.exists() and not p.exists():
        try:
            legacy.replace(p)
        except Exception:
            try:
                p.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
                legacy.unlink(missing_ok=True)
            except Exception:
                pass
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_task_router() -> dict:
    p = _task_router_path()
    if not p.exists():
        p.write_text(json.dumps(_TASK_ROUTER_DEFAULT, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.loads(json.dumps(_TASK_ROUTER_DEFAULT))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("areas"), dict):
            raise ValueError("invalid task router shape")
        # Forward-compat: inject newly added default areas without overriding user customizations.
        data_areas = data.get("areas") or {}
        for area_name, area_cfg in (_TASK_ROUTER_DEFAULT.get("areas") or {}).items():
            if area_name not in data_areas:
                data_areas[area_name] = area_cfg
        data["areas"] = data_areas
        try:
            _save_task_router(data)
        except Exception:
            pass
        return data
    except Exception:
        p.write_text(json.dumps(_TASK_ROUTER_DEFAULT, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.loads(json.dumps(_TASK_ROUTER_DEFAULT))


def _save_task_router(data: dict) -> None:
    _task_router_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _classify_task_area(message: str, mode: str = "normal") -> tuple[str, float, str]:
    router = _load_task_router()
    areas = router.get("areas", {})
    text = (message or "").lower()
    if mode == "plan":
        return "chat_general", 0.6, "mode=plan"

    best_area = "chat_general"
    best_score = 0
    for area, cfg in areas.items():
        kws = cfg.get("keywords") or []
        score = 0
        for kw in kws:
            if not isinstance(kw, str):
                continue
            if kw.lower() in text:
                score += 1
        if score > best_score:
            best_area = area
            best_score = score
    confidence = min(0.95, 0.35 + (best_score * 0.15))
    if best_score <= 0:
        return "chat_general", 0.35, "keyword default"
    return best_area, round(confidence, 2), f"keyword matches={best_score}"


def _looks_like_multistep_build_task(message: str) -> bool:
    t = (message or "").lower()
    if not t.strip():
        return False
    verbs = (
        "crear", "hacé", "hace", "armá", "arma", "build", "make", "generá", "genera",
        "implementá", "implementa", "desarrollá", "desarrolla",
    )
    targets = (
        "pagina web", "página web", "sitio web", "web", "landing", "app", "aplicacion", "aplicación",
        "proyecto", "frontend", "backend", "html", "react", "vite", "next", "django", "flask",
    )
    has_verb = any(v in t for v in verbs)
    has_target = any(x in t for x in targets)
    has_path_hint = ("c:\\" in t) or ("/" in t and ("home" in t or "users" in t))
    return has_verb and (has_target or has_path_hint)


def _resolve_task_route(area: str) -> dict:
    router = _load_task_router()
    areas = router.get("areas", {})
    cfg = areas.get(area) or areas.get("chat_general") or {}
    return {
        "area": area if area in areas else "chat_general",
        "primary_model": str(cfg.get("primary_model") or ""),
        "fallback_models": [str(x) for x in (cfg.get("fallback_models") or []) if str(x).strip()],
        "profile": str(cfg.get("profile") or ""),
    }


def _model_chain_key(model_name: str) -> str:
    return str(model_name or "").strip().casefold()


def _build_model_chain(base_model: str, route: dict) -> list[str]:
    chain: list[str] = []
    seen: set[str] = set()
    for m in [route.get("primary_model"), *(route.get("fallback_models") or []), base_model]:
        mm = str(m or "").strip()
        mk = _model_chain_key(mm)
        if mm and mk and mk not in seen:
            seen.add(mk)
            chain.append(mm)
    # llama.cpp serves one loaded model at a time; cross-model fallback chains
    # cause long sequential timeouts. Keep chain short by default.
    provider = (Config.LLM_PROVIDER or "").strip().lower()
    if provider == "llamacpp":
        single = (os.getenv("LLAMACPP_SINGLE_MODEL_CHAIN", "true") or "true").strip().lower() in ("1", "true", "yes", "on")
        max_chain = 1 if single else max(1, min(int(os.getenv("LLAMACPP_MAX_MODEL_CHAIN", "2")), 4))
        if chain:
            return chain[:max_chain]
        bm = str(base_model or "").strip()
        return [bm] if bm else []
    return chain or [base_model]


def _normal_chat_timeout_sec() -> Optional[int]:
    try:
        v = int(str(os.getenv("NORMAL_CHAT_TIMEOUT_SEC", "0")).strip())
        if v <= 0:
            return None
        return max(10, min(180, v))
    except Exception:
        return None


def _route_with_model_override(route: dict, model_override: str) -> dict:
    preferred = str(model_override or "").strip()
    if not preferred:
        return route
    fallback = [str(x) for x in (route.get("fallback_models") or []) if str(x).strip()]
    prev_primary = str(route.get("primary_model") or "").strip()
    if prev_primary and _model_chain_key(prev_primary) != _model_chain_key(preferred):
        fallback = [prev_primary, *fallback]
    dedup: list[str] = []
    seen: set[str] = set()
    preferred_key = _model_chain_key(preferred)
    for m in fallback:
        mk = _model_chain_key(m)
        if m and mk and mk != preferred_key and mk not in seen:
            seen.add(mk)
            dedup.append(m)
    updated = dict(route or {})
    updated["primary_model"] = preferred
    updated["fallback_models"] = dedup
    return updated


def _router_metrics_path() -> Path:
    data_dir = Path(Config.DATA_DIR)
    internal_dir = data_dir / ".unlz_internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    p = internal_dir / "router_metrics.jsonl"
    legacy = data_dir / "router_metrics.jsonl"
    if legacy.exists() and not p.exists():
        try:
            legacy.replace(p)
        except Exception:
            try:
                p.write_text(legacy.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
                legacy.unlink(missing_ok=True)
            except Exception:
                pass
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _is_visible_knowledge_file(path: Path) -> bool:
    if not path.is_file():
        return False
    name = (path.name or "").strip().lower()
    if not name:
        return False
    if name.startswith("."):
        return False
    blocked_names = {
        "task_router.json",
        "router_metrics.jsonl",
        "telemetry.jsonl",
    }
    if name in blocked_names:
        return False
    allowed_ext = {
        ".pdf",
        ".txt",
        ".md",
        ".doc",
        ".docx",
        ".rtf",
        ".csv",
        ".tsv",
    }
    return path.suffix.lower() in allowed_ext


def _record_router_metric(area: str, model: str, success: bool, latency_ms: int, retries: int, mode: str, reason: str = "") -> None:
    rec = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "area": area,
        "model": model,
        "success": bool(success),
        "latency_ms": int(latency_ms),
        "retries": int(retries),
        "mode": mode,
        "reason": reason[:300],
    }
    with _router_metrics_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    auto = (os.getenv("TASK_ROUTER_AUTO_RECALIBRATE", "false") or "false").strip().lower() in ("1", "true", "yes")
    if not auto:
        return
    interval = max(20, int(os.getenv("TASK_ROUTER_RECALIBRATE_INTERVAL", "100")))
    try:
        total = sum(1 for _ in _router_metrics_path().open("r", encoding="utf-8", errors="ignore"))
        if total % interval == 0:
            _recalibrate_router(min_samples=max(8, int(os.getenv("TASK_ROUTER_MIN_SAMPLES", "12"))))
    except Exception:
        pass


def _router_metrics_summary(limit: int = 5000) -> dict:
    p = _router_metrics_path()
    if not p.exists():
        return {"total": 0, "areas": {}}
    rows: list[dict] = []
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]:
        try:
            rows.append(json.loads(raw))
        except Exception:
            continue
    agg: dict[str, dict[str, dict]] = {}
    for r in rows:
        area = str(r.get("area") or "chat_general")
        model = str(r.get("model") or "unknown")
        a = agg.setdefault(area, {})
        m = a.setdefault(model, {"calls": 0, "ok": 0, "latency_total": 0, "retries_total": 0})
        m["calls"] += 1
        m["ok"] += 1 if r.get("success") else 0
        m["latency_total"] += int(r.get("latency_ms") or 0)
        m["retries_total"] += int(r.get("retries") or 0)
    out_areas: dict[str, dict] = {}
    for area, models in agg.items():
        out_models: dict[str, dict] = {}
        for model, stats in models.items():
            calls = max(1, int(stats["calls"]))
            out_models[model] = {
                "calls": stats["calls"],
                "success_rate": round(float(stats["ok"]) / calls, 3),
                "avg_latency_ms": round(float(stats["latency_total"]) / calls, 1),
                "avg_retries": round(float(stats["retries_total"]) / calls, 2),
            }
        out_areas[area] = out_models
    return {"total": len(rows), "areas": out_areas}


def _recalibrate_router(min_samples: int = 12) -> dict:
    router = _load_task_router()
    summary = _router_metrics_summary(limit=10000)
    changes = []
    for area, models in (summary.get("areas") or {}).items():
        scored = []
        for model, stats in (models or {}).items():
            calls = int(stats.get("calls") or 0)
            if calls < min_samples:
                continue
            success_rate = float(stats.get("success_rate") or 0.0)
            latency = float(stats.get("avg_latency_ms") or 0.0)
            score = success_rate - min(0.3, latency / 100000.0)
            scored.append((score, model))
        if not scored:
            continue
        scored.sort(reverse=True, key=lambda x: x[0])
        best_model = scored[0][1]
        if area in router.get("areas", {}):
            prev = str(router["areas"][area].get("primary_model") or "")
            if best_model and best_model != prev:
                fallback = [prev] + [m for _, m in scored[1:4] if m != prev]
                fallback = [m for m in fallback if m]
                router["areas"][area]["primary_model"] = best_model
                router["areas"][area]["fallback_models"] = fallback
                changes.append({"area": area, "from": prev, "to": best_model})
    if changes:
        _save_task_router(router)
    return {"changes": changes, "count": len(changes), "min_samples": min_samples}


def _normalize_messages_for_jinja(messages: Any) -> Any:
    """
    llama.cpp chat templates (jinja) can require that `system` is strictly first.
    Normalize messages by merging all system messages into one leading system entry.
    """
    if not isinstance(messages, list):
        return messages

    system_parts: list[str] = []
    non_system: list[dict[str, Any]] = []

    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        if role == "system":
            txt = str(m.get("content") or "").strip()
            if txt:
                system_parts.append(txt)
            continue
        non_system.append(m)

    if not system_parts:
        return non_system

    merged_system = {"role": "system", "content": "\n\n".join(system_parts)}
    return [merged_system] + non_system


async def _chat_create_with_fallback(
    client,
    model_chain: list[str],
    cancel_event: Optional[asyncio.Event] = None,
    **kwargs,
):
    """
    Try each model in the chain.
    - If the response lacks `.choices` (SDK v2 / misbehaving llama.cpp) and the
      request contained `tools`, silently retry that same model without tools so
      plain-text-only models can still answer.
    - Raises RuntimeError when every model+attempt fails.
    """
    errors: list[str] = []
    retries = 0
    kwargs_base = dict(kwargs)
    raw_timeout = kwargs_base.pop("timeout", None)
    req_timeout: Optional[float] = None
    try:
        if raw_timeout is not None:
            req_timeout = max(0.1, float(raw_timeout))
    except Exception:
        req_timeout = None
    if "messages" in kwargs_base:
        kwargs_base["messages"] = _normalize_messages_for_jinja(kwargs_base.get("messages"))

    has_tools = "tools" in kwargs_base
    wants_stream = bool(kwargs_base.get("stream"))
    kw_notool = {k: v for k, v in kwargs_base.items() if k not in ("tools", "tool_choice")}

    async def _create_with_deadline(model_name: str, params: dict[str, Any]):
        call_task = asyncio.create_task(client.chat.completions.create(model=model_name, **params))
        cancel_task: Optional[asyncio.Task] = None
        timeout_task: Optional[asyncio.Task] = None
        try:
            if cancel_event is not None:
                cancel_task = asyncio.create_task(cancel_event.wait())
            if req_timeout is not None:
                timeout_task = asyncio.create_task(asyncio.sleep(req_timeout))

            wait_set = {call_task}
            if cancel_task is not None:
                wait_set.add(cancel_task)
            if timeout_task is not None:
                wait_set.add(timeout_task)

            if len(wait_set) == 1:
                return await call_task

            done, _pending = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)
            if cancel_task is not None and cancel_task in done:
                call_task.cancel()
                raise asyncio.CancelledError("run cancelled by user")
            if timeout_task is not None and timeout_task in done:
                call_task.cancel()
                raise TimeoutError(f"Request timed out after {req_timeout:.1f}s")
            return await call_task
        finally:
            for t in (cancel_task, timeout_task):
                if t is not None and not t.done():
                    t.cancel()

    def _format_exc(e: Exception) -> str:
        try:
            txt = str(e or "").strip()
        except Exception:
            txt = ""
        if not txt:
            try:
                if getattr(e, "args", None):
                    txt = " ".join(str(x) for x in e.args if str(x).strip()).strip()
            except Exception:
                txt = ""
        name = type(e).__name__ if e is not None else "Error"
        return f"{name}: {txt}" if txt else name

    def _coerce_completion_like(resp: Any):
        """
        Accepts non-standard LLM response shapes (str/dict) and converts them
        into an object compatible with downstream `resp.choices[0].message.content`.
        """
        if getattr(resp, "choices", None) is not None:
            return resp

        # Plain-text response
        if isinstance(resp, str):
            if not resp.strip():
                return None
            msg = SimpleNamespace(content=resp, tool_calls=None)
            choice = SimpleNamespace(message=msg, finish_reason="stop")
            return SimpleNamespace(choices=[choice])

        # Dict-like response
        if isinstance(resp, dict):
            # Already OpenAI-like payload
            if isinstance(resp.get("choices"), list):
                try:
                    choices = []
                    for c in resp.get("choices") or []:
                        mobj = c.get("message") if isinstance(c, dict) else {}
                        msg = SimpleNamespace(
                            content=(mobj.get("content", "") if isinstance(mobj, dict) else ""),
                            tool_calls=(mobj.get("tool_calls") if isinstance(mobj, dict) else None),
                        )
                        choices.append(SimpleNamespace(message=msg, finish_reason=(c.get("finish_reason") if isinstance(c, dict) else "stop")))
                    return SimpleNamespace(choices=choices)
                except Exception:
                    pass

            # Minimal dict with "content"
            if "content" in resp:
                text = str(resp.get("content") or "")
                if not text.strip():
                    return None
                msg = SimpleNamespace(content=text, tool_calls=None)
                choice = SimpleNamespace(message=msg, finish_reason="stop")
                return SimpleNamespace(choices=[choice])

        return None

    def _extract_msg_text(msg_obj: Any) -> str:
        if msg_obj is None:
            return ""
        content = getattr(msg_obj, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    if item.strip():
                        parts.append(item.strip())
                    continue
                if isinstance(item, dict):
                    txt = str(item.get("text") or item.get("content") or "").strip()
                    if txt:
                        parts.append(txt)
            return "\n".join(parts).strip()
        return ""

    async def _string_stream_adapter(text: str):
        # Adapter for providers that may return plain text even when stream=True.
        if text:
            delta = SimpleNamespace(content=text)
            choice = SimpleNamespace(delta=delta)
            yield SimpleNamespace(choices=[choice])

    async def _consume_stream_to_text(stream_obj: Any) -> str:
        """
        Best-effort adapter for providers returning stream objects even when
        stream=False. Fold chunks into a single text answer.
        """
        out: list[str] = []
        try:
            if hasattr(stream_obj, "__aiter__"):
                async for chunk in stream_obj:
                    choices = getattr(chunk, "choices", None)
                    if not choices:
                        continue
                    c0 = choices[0]
                    msg = getattr(c0, "message", None)
                    if msg is not None:
                        txt = getattr(msg, "content", None)
                        if txt:
                            out.append(str(txt))
                            continue
                    delta = getattr(c0, "delta", None)
                    if delta is not None:
                        txt = getattr(delta, "content", None)
                        if txt:
                            out.append(str(txt))
            elif hasattr(stream_obj, "__iter__"):
                for chunk in stream_obj:
                    choices = getattr(chunk, "choices", None)
                    if not choices:
                        continue
                    c0 = choices[0]
                    msg = getattr(c0, "message", None)
                    if msg is not None:
                        txt = getattr(msg, "content", None)
                        if txt:
                            out.append(str(txt))
                            continue
                    delta = getattr(c0, "delta", None)
                    if delta is not None:
                        txt = getattr(delta, "content", None)
                        if txt:
                            out.append(str(txt))
        except Exception:
            return ""
        return "".join(out).strip()

    def _coerce_stream_like(resp: Any):
        # Standard OpenAI async stream object
        if hasattr(resp, "__aiter__"):
            return resp
        # Fallback: some providers may return a plain string/dict even in stream mode.
        if isinstance(resp, str):
            if not resp.strip():
                return None
            return _string_stream_adapter(resp)
        if isinstance(resp, dict):
            if isinstance(resp.get("content"), str):
                txt = str(resp.get("content") or "")
                if not txt.strip():
                    return None
                return _string_stream_adapter(txt)
            if isinstance(resp.get("text"), str):
                txt = str(resp.get("text") or "")
                if not txt.strip():
                    return None
                return _string_stream_adapter(txt)
        return None

    for m in model_chain:
        # ── Attempt 1: original kwargs ────────────────────────────────────────
        try:
            resp = await _create_with_deadline(m, kwargs_base)
            if not wants_stream and (hasattr(resp, "__aiter__") or hasattr(resp, "__iter__")):
                txt_from_stream = await _consume_stream_to_text(resp)
                if txt_from_stream:
                    msg = SimpleNamespace(content=txt_from_stream, tool_calls=None)
                    choice = SimpleNamespace(message=msg, finish_reason="stop")
                    return SimpleNamespace(choices=[choice]), m, retries, errors
            if wants_stream:
                stream_like = _coerce_stream_like(resp)
                if stream_like is not None:
                    return stream_like, m, retries, errors
                if not has_tools:
                    errors.append(f"{m}: invalid stream shape ({type(resp).__name__})")
                    retries += 1
                    continue
            coerced = _coerce_completion_like(resp)
            if coerced is not None:
                if not wants_stream:
                    c = (getattr(coerced, "choices", None) or [])
                    if c:
                        m0 = getattr(c[0], "message", None)
                        txt0 = _extract_msg_text(m0) if m0 else ""
                        tc0 = getattr(m0, "tool_calls", None) if m0 else None
                        if (not txt0) and (not tc0):
                            if not has_tools:
                                errors.append(f"{m}: empty completion")
                                retries += 1
                                continue
                            # With tools enabled, fall through to retry same model without tools.
                        else:
                            return coerced, m, retries, errors
                    else:
                        if not has_tools:
                            errors.append(f"{m}: empty completion")
                            retries += 1
                            continue
                else:
                    return coerced, m, retries, errors
            # Bad shape but we have a tools fallback → fall through
            if not has_tools:
                errors.append(f"{m}: invalid response shape ({type(resp).__name__})")
                retries += 1
                continue
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                raise
            errors.append(f"{m}: {_format_exc(e)}")
            retries += 1
            continue

        # ── Attempt 2: same model, no tools (only reached when tools caused bad shape)
        try:
            resp2 = await _create_with_deadline(m, kw_notool)
            if not wants_stream and (hasattr(resp2, "__aiter__") or hasattr(resp2, "__iter__")):
                txt2 = await _consume_stream_to_text(resp2)
                if txt2:
                    msg = SimpleNamespace(content=txt2, tool_calls=None)
                    choice = SimpleNamespace(message=msg, finish_reason="stop")
                    return SimpleNamespace(choices=[choice]), m, retries + 1, errors
            if wants_stream:
                stream_like2 = _coerce_stream_like(resp2)
                if stream_like2 is not None:
                    return stream_like2, m, retries + 1, errors
            coerced2 = _coerce_completion_like(resp2)
            if coerced2 is not None:
                if not wants_stream:
                    c2 = (getattr(coerced2, "choices", None) or [])
                    if c2:
                        m2 = getattr(c2[0], "message", None)
                        txt2 = _extract_msg_text(m2) if m2 else ""
                        tc2 = getattr(m2, "tool_calls", None) if m2 else None
                        if (not txt2) and (not tc2):
                            errors.append(f"{m}[notool]: empty completion")
                            retries += 1
                            continue
                return coerced2, m, retries + 1, errors
            errors.append(f"{m}[notool]: invalid shape ({type(resp2).__name__})")
        except Exception as e2:
            if isinstance(e2, asyncio.CancelledError):
                raise
            errors.append(f"{m}[notool]: {_format_exc(e2)}")
        retries += 1

    if (Config.LLM_PROVIDER or "").lower() == "llamacpp" and not _llamacpp_api_healthy(timeout=0.8):
        raise RuntimeError(
            f"llama.cpp API inválida/no disponible en {Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT} "
            f"(posible conflicto de puerto)."
        )
    raise RuntimeError(" | ".join(errors[:4]) or "llm call failed")


def _record_web_provider(provider: str, ok: bool, latency_ms: int = 0, err: str = "") -> None:
    p = (_CONNECTOR_METRICS.setdefault("web_search", {}).setdefault("providers", {}).setdefault(provider, {
        "calls": 0,
        "ok": 0,
        "error": 0,
        "avg_latency_ms": 0.0,
        "last_error": "",
        "last_seen": "",
    }))
    p["calls"] += 1
    p["ok"] += 1 if ok else 0
    p["error"] += 0 if ok else 1
    if latency_ms > 0:
        prev_calls = max(1, int(p["calls"]))
        prev_avg = float(p["avg_latency_ms"])
        p["avg_latency_ms"] = round(((prev_avg * (prev_calls - 1)) + latency_ms) / prev_calls, 2)
    if err and not ok:
        p["last_error"] = err[:400]
    p["last_seen"] = datetime.now().isoformat(timespec="seconds")


def _record_tool_metric(tool_name: str, ok: bool, latency_ms: int = 0, err: str = "") -> None:
    t = _CONNECTOR_METRICS.setdefault("tools", {}).setdefault(tool_name, {
        "calls": 0,
        "ok": 0,
        "error": 0,
        "avg_latency_ms": 0.0,
        "last_error": "",
        "last_seen": "",
    })
    t["calls"] += 1
    t["ok"] += 1 if ok else 0
    t["error"] += 0 if ok else 1
    if latency_ms > 0:
        prev_calls = max(1, int(t["calls"]))
        prev_avg = float(t["avg_latency_ms"])
        t["avg_latency_ms"] = round(((prev_avg * (prev_calls - 1)) + latency_ms) / prev_calls, 2)
    if err and not ok:
        t["last_error"] = err[:400]
    t["last_seen"] = datetime.now().isoformat(timespec="seconds")

# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []        # [{role, content}, ...]
    system_prompt: str = ""         # override default system prompt (from Behavior)
    model_override: str = ""        # optional behavior-level model override
    harness_override: str = ""      # optional behavior-level harness override
    llamacpp_overrides: dict[str, Any] = Field(default_factory=dict)  # per-behavior llama runtime overrides
    folder_id: str = ""             # optional folder scope for folder-only docs
    sandbox_root: str = ""          # optional folder sandbox path (enforced for command/file ops)
    mode: str = "normal"            # normal | plan | iterate | simple
    conversation_id: str = ""
    dry_run: bool = False
    internet_enabled: bool = True
    tools_mode: str = "auto"        # auto | with_tools | without_tools


class CommandActionRequest(BaseModel):
    command: str
    cwd: str = ""
    sandbox_root: str = ""
    timeout_sec: int = Config.AGENT_COMMAND_TIMEOUT_SEC
    idempotency_key: str = ""


class HarnessInstallRequest(BaseModel):
    harness_id: str


# ─────────────────────────────────────────────────────────────────────────────
# Tool specs (OpenAI function-calling format)
# ─────────────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_local_knowledge",
            "description": (
                "Search the local knowledge base (RAG) for information stored in university "
                "documents, PDFs, or any ingested content. Use this before web_search for "
                "domain-specific or institutional queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the internet for current events, news, or general knowledge "
                "not available in the local knowledge base."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current local date and time.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_stats",
            "description": "Get CPU, RAM usage statistics.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_knowledge_base_files",
            "description": "List files in the knowledge base (/data folder).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_folder_documents",
            "description": (
                "Search ONLY documents attached to the current conversation folder. "
                "Use this for folder-scoped context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_windows_command",
            "description": (
                "Execute a Windows PowerShell command to perform real actions on the machine "
                "(create folders/files, move files, run tools, etc). "
                "Use this when user asks to DO an action, not just explain it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "PowerShell command to execute"},
                    "cwd": {"type": "string", "description": "Optional working directory"},
                    "timeout_sec": {"type": "integer", "description": "Optional timeout in seconds"},
                    "idempotency_key": {"type": "string", "description": "Optional idempotency key for mutating actions"},
                    "dry_run": {"type": "boolean", "description": "When true, returns planned action without executing"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_file_exists",
            "description": "Verify that a file or directory exists on disk.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_file_contains",
            "description": "Verify that a file contains specific text.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "text": {"type": "string"}},
                "required": ["path", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_command_output",
            "description": "Run a read-only command and verify output contains expected text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "contains": {"type": "string"},
                    "cwd": {"type": "string"},
                    "timeout_sec": {"type": "integer"},
                },
                "required": ["command", "contains"],
            },
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Tool executor (sync, runs in thread pool)
# ─────────────────────────────────────────────────────────────────────────────

_HIGH_RISK_PATTERNS = [
    # Block dangerous disk format command, but avoid false-positives like URL params
    # (e.g. auto=format in image URLs inside HTML/CSS content).
    r"(?i)(?:^|[;&|]\s*|\s)format(?:\s+[a-z]:|\s+/|\s+fs=)",
    r"\bdiskpart\b",
    r"\bbcdedit\b",
    r"\bshutdown\b",
    r"\bstop-computer\b",
    r"\brestart-computer\b",
]

_TOOL_RESULTS_BY_IDEMPOTENCY: dict[str, str] = {}

_TOOL_CONTRACTS = {
    "search_local_knowledge": {
        "operation_class": "knowledge",
        "mutating": False,
        "required": {"query": str},
        "retry_hint": "Refine query terms.",
    },
    "web_search": {
        "operation_class": "network",
        "mutating": False,
        "required": {"query": str},
        "retry_hint": "Try another provider or a narrower query.",
    },
    "run_windows_command": {
        "operation_class": "system",
        "mutating": True,
        "required": {"command": str},
        "retry_hint": "Check permissions, cwd and command syntax.",
    },
    "verify_file_exists": {
        "operation_class": "filesystem",
        "mutating": False,
        "required": {"path": str},
        "retry_hint": "Ensure path is absolute and accessible.",
    },
    "verify_file_contains": {
        "operation_class": "filesystem",
        "mutating": False,
        "required": {"path": str, "text": str},
        "retry_hint": "Verify file encoding and exact substring.",
    },
    "verify_command_output": {
        "operation_class": "process",
        "mutating": False,
        "required": {"command": str, "contains": str},
        "retry_hint": "Use simpler command output and exact expected token.",
    },
}


def _tool_contract_error(name: str, args: dict) -> str | None:
    contract = _TOOL_CONTRACTS.get(name)
    if not contract:
        return None
    req = contract.get("required", {})
    for k, typ in req.items():
        if k not in args:
            return f"Tool contract error: missing '{k}'"
        if not isinstance(args.get(k), typ):
            return f"Tool contract error: '{k}' must be {typ.__name__}"
    return None


def _operation_class_for_command(command: str) -> str:
    c = (command or "").lower()
    if any(x in c for x in ["new-item", "remove-item", "copy-item", "move-item", "mkdir", "del ", "ren ", "set-content", "add-content"]):
        return "filesystem"
    if any(x in c for x in ["invoke-webrequest", "curl ", "wget ", "http://", "https://"]):
        return "network"
    if any(x in c for x in ["start-process", "stop-process", "taskkill", "get-process"]):
        return "process"
    return "system"


def _policy_decision(operation_class: str, mutating: bool) -> tuple[str, str]:
    # Global execution mode should be the primary gate:
    # - confirm => asks for approval
    # - autonomous => runs directly
    # Per-operation env policy can still force confirm/deny.
    default = "allow"
    env_key = f"AGENT_POLICY_{operation_class.upper()}"
    raw = (os.getenv(env_key, default) or default).strip().lower()
    if raw not in ("allow", "confirm", "deny"):
        raw = default
    if raw == "allow" and mutating and _execution_mode() == "confirm":
        return "confirm", "Global execution mode is confirm."
    if raw == "deny":
        return "deny", f"Denied by policy {env_key}=deny"
    if raw == "confirm":
        return "confirm", f"Requires confirmation by policy {env_key}=confirm"
    return "allow", "Allowed"


def _execution_mode() -> str:
    mode = os.getenv("AGENT_EXECUTION_MODE", Config.AGENT_EXECUTION_MODE).strip().lower()
    return mode if mode in ("confirm", "autonomous") else "confirm"


def _normalize_path(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p or ""))


def _is_path_within_base(path: str, base: str) -> bool:
    try:
        p = _normalize_path(path)
        b = _normalize_path(base)
        return os.path.commonpath([p, b]) == b
    except Exception:
        return False


def _extract_command_paths(command: str) -> list[str]:
    c = command or ""
    out: list[str] = []
    # Absolute Windows paths (quoted or unquoted), e.g. C:\foo\bar
    for m in re.finditer(r"(?i)([a-z]:\\[^\s\"']+|[a-z]:\\[^\"']*)", c):
        val = (m.group(1) or "").strip().strip("\"'")
        if val:
            out.append(val)
    # Relative explicit paths, e.g. .\foo, ..\bar
    for m in re.finditer(r"(?i)(\.\.?\\[^\s\"']+)", c):
        val = (m.group(1) or "").strip().strip("\"'")
        if val:
            out.append(val)
    # UNC paths
    for m in re.finditer(r"(\\\\[^\s\"']+)", c):
        val = (m.group(1) or "").strip().strip("\"'")
        if val:
            out.append(val)
    # De-dup while preserving order
    seen = set()
    clean: list[str] = []
    for p in out:
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        clean.append(p)
    return clean


def _sandbox_violation(command: str, cwd: str, sandbox_root: str) -> str | None:
    if not sandbox_root:
        return None

    sb = _normalize_path(sandbox_root)
    if not os.path.isdir(sb):
        return f"Invalid sandbox_root: {sb}"
    if not _is_path_within_base(cwd, sb):
        return f"cwd outside sandbox: {cwd}"

    c = command or ""
    if "..\\" in c or "../" in c:
        return "Parent path traversal is not allowed in sandbox mode."

    # Block explicit drive switch tokens outside sandbox drive (e.g. 'D:' in command body).
    sb_drive = os.path.splitdrive(sb)[0].lower()
    drive_tokens = re.findall(r"(?i)\b([a-z]:)\b", c)
    for d in drive_tokens:
        if d.lower() != sb_drive:
            return f"Drive switch outside sandbox drive is not allowed: {d}"

    for p in _extract_command_paths(c):
        # Relative explicit paths are resolved from cwd.
        full = _normalize_path(os.path.join(cwd, p) if (p.startswith(".\\") or p.startswith("..\\")) else p)
        if not _is_path_within_base(full, sb):
            return f"Path outside sandbox detected: {p}"
    return None


def _run_windows_command(args: dict) -> str:
    command = str(args.get("command", "")).strip()
    if not command:
        return json.dumps({"status": "error", "error": "Missing 'command'"}, ensure_ascii=False)

    for pattern in _HIGH_RISK_PATTERNS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            return json.dumps({
                "status": "blocked",
                "error": "Command blocked by safety policy",
                "command": command,
            }, ensure_ascii=False)

    sandbox_root = str(args.get("sandbox_root") or "").strip()
    sandbox_root = _normalize_path(sandbox_root) if sandbox_root else ""

    cwd = str(args.get("cwd") or "").strip()
    if cwd:
        run_cwd = _normalize_path(cwd)
    elif sandbox_root:
        run_cwd = sandbox_root
    else:
        run_cwd = os.path.expanduser("~")
    if not os.path.isdir(run_cwd):
        return json.dumps({"status": "error", "error": f"Invalid cwd: {run_cwd}"}, ensure_ascii=False)

    timeout_sec = args.get("timeout_sec", Config.AGENT_COMMAND_TIMEOUT_SEC)
    try:
        timeout_sec = int(timeout_sec)
    except Exception:
        timeout_sec = Config.AGENT_COMMAND_TIMEOUT_SEC
    timeout_sec = max(1, min(timeout_sec, 300))

    max_output = max(500, int(os.getenv("AGENT_COMMAND_MAX_OUTPUT", str(Config.AGENT_COMMAND_MAX_OUTPUT))))
    op_class = _operation_class_for_command(command)
    mutating = op_class in ("filesystem", "process", "system")
    approved = bool(args.get("approved", False))

    idem_key = str(args.get("idempotency_key") or "").strip()
    if not idem_key:
        idem_seed = f"{command}|{run_cwd}|{timeout_sec}"
        idem_key = hashlib.sha256(idem_seed.encode("utf-8")).hexdigest()[:20]
    if idem_key in _TOOL_RESULTS_BY_IDEMPOTENCY:
        return _TOOL_RESULTS_BY_IDEMPOTENCY[idem_key]

    dry_run = bool(args.get("dry_run", False))
    if dry_run:
        result = json.dumps({
            "status": "dry_run",
            "operation_class": op_class,
            "command": command,
            "cwd": run_cwd,
            "sandbox_root": sandbox_root,
            "idempotency_key": idem_key,
            "would_execute": True,
        }, ensure_ascii=False)
        _TOOL_RESULTS_BY_IDEMPOTENCY[idem_key] = result
        return result

    # If no sandbox configured, force explicit user decision only in confirm mode.
    # In autonomous mode, allow execution (unless blocked by explicit policy).
    if not sandbox_root and not approved and _execution_mode() == "confirm":
        return json.dumps({
            "status": "needs_confirmation",
            "mode": _execution_mode(),
            "operation_class": op_class,
            "command": command,
            "cwd": run_cwd,
            "sandbox_root": "",
            "idempotency_key": idem_key,
            "reason_key": "sandbox_not_configured",
            "message": "No hay carpeta sandbox definida para esta conversación. Confirmá si querés ejecutar igualmente.",
        }, ensure_ascii=False)

    if sandbox_root:
        violation = _sandbox_violation(command, run_cwd, sandbox_root)
        if violation:
            return json.dumps({
                "status": "blocked_sandbox",
                "operation_class": op_class,
                "command": command,
                "cwd": run_cwd,
                "sandbox_root": sandbox_root,
                "idempotency_key": idem_key,
                "reason": violation,
                "retry_hint": "Use rutas y operaciones dentro de la carpeta sandbox configurada para esta carpeta.",
            }, ensure_ascii=False)

    decision, reason = _policy_decision(op_class, mutating)
    if decision == "deny":
        return json.dumps({
            "status": "blocked_policy",
            "operation_class": op_class,
            "command": command,
            "cwd": run_cwd,
            "sandbox_root": sandbox_root,
            "idempotency_key": idem_key,
            "reason": reason,
            "retry_hint": "Request another operation or update policy settings.",
        }, ensure_ascii=False)

    mode = _execution_mode()
    if (mode == "confirm" or decision == "confirm") and not approved:
        return json.dumps({
            "status": "needs_confirmation",
            "mode": mode,
            "operation_class": op_class,
            "command": command,
            "cwd": run_cwd,
            "sandbox_root": sandbox_root,
            "idempotency_key": idem_key,
            "message": (
                "Execution requires confirmation. Awaiting explicit user choice."
            ),
        }, ensure_ascii=False)

    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
            cwd=run_cwd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        out = (completed.stdout or "")
        err = (completed.stderr or "")
        if len(out) > max_output:
            out = out[:max_output] + "\n...[truncated]"
        if len(err) > max_output:
            err = err[:max_output] + "\n...[truncated]"
        result = json.dumps({
            "status": "executed",
            "mode": mode,
            "operation_class": op_class,
            "command": command,
            "cwd": run_cwd,
            "sandbox_root": sandbox_root,
            "idempotency_key": idem_key,
            "returncode": completed.returncode,
            "stdout": out,
            "stderr": err,
        }, ensure_ascii=False)
        _TOOL_RESULTS_BY_IDEMPOTENCY[idem_key] = result
        return result
    except subprocess.TimeoutExpired:
        result = json.dumps({
            "status": "timeout",
            "command": command,
            "cwd": run_cwd,
            "sandbox_root": sandbox_root,
            "idempotency_key": idem_key,
            "timeout_sec": timeout_sec,
            "retry_hint": "Use a shorter command or increase timeout_sec.",
        }, ensure_ascii=False)
        _TOOL_RESULTS_BY_IDEMPOTENCY[idem_key] = result
        return result
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": str(e),
            "command": command,
            "cwd": run_cwd,
            "sandbox_root": sandbox_root,
            "idempotency_key": idem_key,
            "retry_hint": "Validate command syntax and working directory.",
        }, ensure_ascii=False)


def _summarize_windows_command_result(result_text: str) -> str:
    try:
        data = json.loads(result_text)
    except Exception:
        return "Comando ejecutado."

    status = data.get("status")
    command = data.get("command", "")
    if status == "executed":
        rc = data.get("returncode", 0)
        if rc == 0:
            return f"Acción ejecutada correctamente.\n\nComando: `{command}`"
        err = (data.get("stderr") or "").strip()
        return f"El comando terminó con código {rc}.\n\nComando: `{command}`\n\nError:\n```\n{err}\n```"
    if status == "needs_confirmation":
        if str(data.get("reason_key") or "") == "sandbox_not_configured":
            return (
                "Esta conversación no tiene carpeta sandbox definida.\n\n"
                "Confirmá si querés ejecutar igualmente o configurá la carpeta sandbox en `Carpetas`."
            )
        return (
            "Modo de ejecución actual: `Preguntar antes de ejecutar`.\n\n"
            "Elegí una acción en las tarjetas de confirmación para continuar."
        )
    if status == "timeout":
        return f"El comando superó el tiempo límite.\n\nComando: `{command}`"
    if status == "blocked":
        return "El comando fue bloqueado por política de seguridad."
    if status == "blocked_policy":
        return f"El comando fue bloqueado por política.\n\nRazón: {data.get('reason', 'policy deny')}."
    if status == "blocked_sandbox":
        return f"El comando fue bloqueado por sandbox.\n\nRazón: {data.get('reason', 'ruta fuera de sandbox')}."
    if status == "dry_run":
        return f"Modo dry-run: no ejecuté el comando.\n\nComando: `{command}`"
    if status == "error":
        return f"No pude ejecutar el comando: {data.get('error', 'error desconocido')}."
    return "Comando procesado."


def _summarize_tool_result(tool_name: str | None, result_text: str | None) -> str:
    if not tool_name or not result_text:
        return "No pude generar respuesta final, pero sí ejecuté herramientas."
    if tool_name == "run_windows_command":
        return _summarize_windows_command_result(result_text)
    if tool_name == "web_search":
        snippet = result_text.strip()
        if not snippet:
            return "Realicé búsqueda web, pero no obtuve resultados útiles."
        return f"Resultado de búsqueda web:\n\n{snippet[:1800]}"
    if tool_name == "search_local_knowledge":
        snippet = result_text.strip()
        if not snippet:
            return "Busqué en conocimiento local, sin resultados relevantes."
        return f"Resultado de búsqueda local:\n\n{snippet[:1800]}"
    if tool_name == "search_folder_documents":
        snippet = result_text.strip()
        if not snippet:
            return "Busqué en documentos de carpeta, sin resultados relevantes."
        return f"Resultado de documentos de carpeta:\n\n{snippet[:1800]}"
    snippet = result_text.strip()
    if snippet:
        return snippet[:1800]
    return f"Ejecuté la herramienta `{tool_name}`, pero sin salida de texto."


def _safe_folder_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", (raw or "").strip())
    return cleaned[:64]


def _folder_docs_dir(folder_id: str) -> Path:
    return Path(Config.DATA_DIR) / "folders" / folder_id


def _extract_text_for_search(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix in (".txt", ".md", ".csv", ".log"):
            return path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                chunks = []
                for page in reader.pages[:8]:
                    chunks.append((page.extract_text() or ""))
                return "\n".join(chunks)
            except Exception:
                return ""
    except Exception:
        return ""
    return ""


def _search_folder_documents(folder_id: str, query: str, max_results: int = 4) -> str:
    fid = _safe_folder_id(folder_id)
    if not fid:
        return "No folder selected for this conversation."
    folder = _folder_docs_dir(fid)
    if not folder.exists():
        return "This folder has no attached documents."
    q = (query or "").strip().lower()
    if not q:
        return "Missing query."
    terms = [t for t in re.split(r"\s+", q) if t]
    if not terms:
        return "Missing query terms."

    ranked: list[tuple[int, str]] = []
    for f in folder.iterdir():
        if not f.is_file():
            continue
        text = _extract_text_for_search(f)
        if not text:
            continue
        low = text.lower()
        score = sum(low.count(t) for t in terms)
        if score <= 0:
            continue
        snippet_pos = max((low.find(t) for t in terms), default=0)
        snippet_pos = max(snippet_pos, 0)
        start = max(0, snippet_pos - 220)
        end = min(len(text), snippet_pos + 680)
        snippet = text[start:end].replace("\n", " ").strip()
        ranked.append((score, f"[{f.name}] score={score}\n{snippet}"))

    if not ranked:
        return "No relevant content found in folder documents."

    ranked.sort(key=lambda x: x[0], reverse=True)
    n = max(1, min(int(max_results or 4), 8))
    return "\n\n".join(item for _, item in ranked[:n])


def _verify_file_exists(path: str) -> str:
    p = Path(os.path.expanduser(path or "")).resolve()
    return json.dumps({
        "passed": p.exists(),
        "path": str(p),
        "is_file": p.is_file(),
        "is_dir": p.is_dir(),
    }, ensure_ascii=False)


def _verify_file_contains(path: str, text: str) -> str:
    p = Path(os.path.expanduser(path or "")).resolve()
    if not p.exists() or not p.is_file():
        return json.dumps({"passed": False, "path": str(p), "reason": "file_not_found"}, ensure_ascii=False)
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return json.dumps({"passed": False, "path": str(p), "reason": f"read_error:{e}"}, ensure_ascii=False)
    needle = str(text or "")
    return json.dumps({
        "passed": needle in content,
        "path": str(p),
        "contains": needle,
    }, ensure_ascii=False)


def _verify_command_output(command: str, contains: str, cwd: str = "", timeout_sec: int = 20) -> str:
    payload = _run_windows_command({
        "command": command,
        "cwd": cwd,
        "timeout_sec": timeout_sec,
        "dry_run": False,
        "idempotency_key": f"verify::{hashlib.sha1((command+'|'+cwd).encode('utf-8')).hexdigest()[:20]}",
    })
    try:
        data = json.loads(payload)
    except Exception:
        return json.dumps({"passed": False, "reason": "invalid_command_result"}, ensure_ascii=False)
    out = str(data.get("stdout") or "")
    err = str(data.get("stderr") or "")
    txt = f"{out}\n{err}"
    needle = str(contains or "")
    return json.dumps({
        "passed": needle in txt and data.get("status") == "executed" and int(data.get("returncode", 1)) == 0,
        "status": data.get("status"),
        "returncode": data.get("returncode"),
        "contains": needle,
    }, ensure_ascii=False)


def execute_tool(name: str, args: dict, folder_id: str = "", sandbox_root: str = "", dry_run: bool = False) -> str:
    started = time.perf_counter()
    ok = False
    last_err = ""
    try:
        if not isinstance(args, dict):
            last_err = "invalid args shape"
            return f"Tool error ({name}): invalid args shape"
        c_err = _tool_contract_error(name, args)
        if c_err:
            hint = (_TOOL_CONTRACTS.get(name) or {}).get("retry_hint", "")
            last_err = c_err
            return f"{c_err}. RETRY_HINT: {hint}"

        if name == "search_local_knowledge":
            from rag_pipeline.retriever import search_documents
            results = search_documents(args.get("query", ""))
            if not results:
                ok = True
                return "No relevant documents found in the knowledge base."
            ok = True
            return "\n\n".join(
                f"[Document {i + 1}]:\n{r.get('page_content') or r.get('content') or json.dumps(r)}"
                for i, r in enumerate(results[:4])
            )

        elif name == "web_search":
            out = _web_search(args.get("query", ""), args.get("max_results", 4))
            ok = not str(out).startswith("WEB_SEARCH_UNAVAILABLE")
            if not ok:
                last_err = "unavailable"
            return out

        elif name == "get_current_time":
            from datetime import datetime
            ok = True
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        elif name == "get_system_stats":
            import psutil
            mem = psutil.virtual_memory()
            vram = _collect_vram_stats()
            ok = True
            return json.dumps({
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "ram_total_gb": round(mem.total / 1024 ** 3, 2),
                "ram_used_gb": round(mem.used / 1024 ** 3, 2),
                "ram_percent": mem.percent,
                "vram_total_gb": vram["vram_total_gb"],
                "vram_used_gb": vram["vram_used_gb"],
                "vram_percent": vram["vram_percent"],
                "gpus": vram["gpus"],
            }, indent=2)

        elif name == "list_knowledge_base_files":
            data_dir = Path(Config.DATA_DIR)
            if not data_dir.exists():
                ok = True
                return "Knowledge base is empty."
            files = [f.name for f in data_dir.iterdir() if f.is_file()]
            ok = True
            return json.dumps(files) if files else "No files in knowledge base."

        elif name == "search_folder_documents":
            out = _search_folder_documents(
                folder_id=folder_id,
                query=args.get("query", ""),
                max_results=args.get("max_results", 4),
            )
            ok = True
            return out

        elif name == "run_windows_command":
            payload = dict(args)
            if dry_run and "dry_run" not in payload:
                payload["dry_run"] = True
            if sandbox_root and "sandbox_root" not in payload:
                payload["sandbox_root"] = sandbox_root
            out = _run_windows_command(payload)
            try:
                p = json.loads(out)
                st = str(p.get("status") or "")
                ok = st in ("executed", "dry_run")
                if not ok:
                    last_err = st or "failed"
            except Exception:
                ok = False
                last_err = "invalid_json_result"
            return out

        elif name == "verify_file_exists":
            out = _verify_file_exists(str(args.get("path", "")))
            try:
                ok = bool(json.loads(out).get("passed"))
            except Exception:
                ok = False
                last_err = "invalid_json_result"
            return out

        elif name == "verify_file_contains":
            out = _verify_file_contains(str(args.get("path", "")), str(args.get("text", "")))
            try:
                ok = bool(json.loads(out).get("passed"))
            except Exception:
                ok = False
                last_err = "invalid_json_result"
            return out

        elif name == "verify_command_output":
            out = _verify_command_output(
                command=str(args.get("command", "")),
                contains=str(args.get("contains", "")),
                cwd=str(args.get("cwd", "")),
                timeout_sec=int(args.get("timeout_sec", 20) or 20),
            )
            try:
                ok = bool(json.loads(out).get("passed"))
            except Exception:
                ok = False
                last_err = "invalid_json_result"
            return out

        else:
            last_err = "unknown_tool"
            return f"Unknown tool: {name}"

    except Exception as e:
        hint = (_TOOL_CONTRACTS.get(name) or {}).get("retry_hint", "Check parameters and try again.")
        last_err = str(e)
        return f"Tool error ({name}): {e}. RETRY_HINT: {hint}"
    finally:
        latency = int((time.perf_counter() - started) * 1000)
        _record_tool_metric(name, ok=ok, latency_ms=latency, err=last_err)


# ─────────────────────────────────────────────────────────────────────────────
# LLM client factory
# ─────────────────────────────────────────────────────────────────────────────

def _get_client():
    from openai import AsyncOpenAI

    p = Config.LLM_PROVIDER
    if p == "llamacpp":
        return (
            AsyncOpenAI(
                base_url=f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}/v1",
                api_key="not-needed",
            ),
            Config.LLAMACPP_MODEL_ALIAS,
        )
    elif p == "openai":
        return AsyncOpenAI(api_key=Config.OPENAI_API_KEY), Config.OPENAI_MODEL
    else:  # ollama
        return (
            AsyncOpenAI(
                base_url=f"{Config.OLLAMA_BASE_URL.rstrip('/')}/v1",
                api_key="not-needed",
            ),
            Config.OLLAMA_MODEL,
        )


# ─────────────────────────────────────────────────────────────────────────────
# System prompts
# ─────────────────────────────────────────────────────────────────────────────

_PROMPTS = {
    "en": (
        "You are an intelligent local AI assistant. "
        "You have access to tools: local knowledge search (RAG), web search, time, system stats, and Windows terminal command execution. "
        "Do not claim you lack internet access. If the user asks to research/search online, you must call web_search. "
        "When the user asks you to perform an action on their machine, use run_windows_command instead of just explaining how. "
        "If run_windows_command returns needs_confirmation, ask the user to approve/reject using confirmation cards in chat. "
        "Use tools proactively to answer accurately. "
        "Format responses in Markdown. Be concise and precise."
    ),
    "es": (
        "Sos un asistente local de IA, generalista y neutral. "
        "Tenés acceso a herramientas: búsqueda de conocimiento local (RAG), búsqueda web, hora, stats del sistema y ejecución de comandos en terminal de Windows. "
        "No digas que no tenés acceso a internet: si el usuario pide investigar o buscar online, tenés que usar web_search. "
        "Cuando el usuario te pida realizar una acción en su máquina, usá run_windows_command en lugar de solo explicar pasos. "
        "Si run_windows_command devuelve needs_confirmation, pedí al usuario aprobar o rechazar desde las tarjetas de confirmación del chat. "
        "Usá las herramientas proactivamente para responder con precisión. "
        "Formateá las respuestas en Markdown. Sé conciso y preciso."
    ),
    "zh": (
        "您是一个通用且中立的本地AI助手。"
        "您可以使用工具：本地知识搜索(RAG)、网络搜索、时间查询、系统状态。"
        "主动使用工具以准确回答。用Markdown格式化回答。简洁精确。"
    ),
}


_HARNESS_PROMPTS = {
    "native": "",
    "claude-code": (
        "Harness profile: claude-code. "
        "Behave like a pragmatic coding agent: understand task, plan briefly, then execute concrete steps. "
        "Prefer deterministic, testable changes and minimal diffs. "
        "When coding, mention assumptions succinctly and prioritize correctness over verbosity. "
        "Use tools only when they materially improve accuracy or execution."
    ),
    "opencode": (
        "Harness profile: opencode. "
        "Favor short iterative coding loops with quick verification and tool use when needed. "
        "Keep responses practical and execution-oriented. "
        "When solving coding tasks, prefer concrete patches and checks over long explanations."
    ),
    "little-coder": (
        "Harness profile: little-coder. "
        "Prefer short action loops and minimal context. "
        "Before using tools, decide if they are strictly needed for the user goal. "
        "When writing code: keep patches small, concrete, and executable. "
        "State assumptions briefly, then produce directly usable output. "
        "Avoid verbose chain-of-thought style narration."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Agent streaming generator
# ─────────────────────────────────────────────────────────────────────────────

def _compose_system_prompt(system_prompt: str = "", harness_override: str = "") -> str:
    lang = Config.AGENT_LANGUAGE
    base_prompt = _PROMPTS.get(lang, _PROMPTS["en"])
    harness = (harness_override or getattr(Config, "AGENT_HARNESS", "native") or "native").strip().lower()
    if harness not in _HARNESS_PROMPTS:
        harness = "native"
    harness_prompt = _HARNESS_PROMPTS.get(harness, _HARNESS_PROMPTS["native"])
    if harness_prompt:
        base_prompt = f"{base_prompt}\n\n{harness_prompt}"
    if system_prompt:
        return (
            f"{base_prompt}\n\n"
            "Behavior profile (additional instructions):\n"
            f"{system_prompt}"
        )
    return base_prompt


def _simple_chat_system_prompt() -> str:
    lang = (Config.AGENT_LANGUAGE or "es").strip().lower()
    if lang == "es":
        return (
            "Sos un asistente conversacional. Respondé en español, breve y natural, "
            "en 1-2 oraciones, sin usar herramientas."
        )
    if lang == "zh":
        return "你是一个聊天助手。请简短自然地回答（1-2句），不要调用工具。"
    return "You are a chat assistant. Reply briefly and naturally in 1-2 sentences. Do not call tools."


def _simple_chat_extra_body(model_name: str) -> dict[str, Any]:
    m = str(model_name or "").strip().lower()
    # Qwen 3.6 supports enable_thinking kwarg; disabling it improves latency.
    if "qwen3.6" in m or "qwen3-6" in m or "qwen-3.6" in m:
        # llama.cpp expects this through chat_template_kwargs for Qwen 3.6 templates.
        # Keep top-level flag as compatibility fallback for other backends/wrappers.
        return {
            "enable_thinking": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
    return {}


def _simple_chat_timeout_sec() -> int:
    try:
        v = int(str(os.getenv("SIMPLE_CHAT_TIMEOUT_SEC", "0")).strip())
        if v <= 0:
            return 0
        return max(30, min(600, v))
    except Exception:
        return 0


def _speed_router_model_chain(base_model: str = "") -> list[str]:
    """
    Candidate model chain for quick-vs-detailed routing.
    Prefer a tiny model via env; always keep base/current model as fallback.
    """
    raw = str(os.getenv("AGENT_SPEED_ROUTER_MODELS", "") or "").strip()
    if not raw:
        raw = str(os.getenv("AGENT_SPEED_ROUTER_MODEL", "qwen3-0.6b,qwen3-1.7b,gemma-3-4b-it-q4_0") or "").strip()
    candidates = [x.strip() for x in raw.split(",") if x.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for m in [*candidates, str(base_model or "").strip()]:
        mk = _model_chain_key(m)
        if m and mk and mk not in seen:
            seen.add(mk)
            out.append(m)
    return out


async def _llm_route_response_depth(
    message: str,
    history: list[dict[str, Any]],
    preferred_model: str,
    cancel_event: Optional[asyncio.Event] = None,
) -> tuple[str, str]:
    """
    LLM-based depth router.
    Returns ("quick"|"detailed", reason).
    """
    client, base_model = _get_client()
    chain = _speed_router_model_chain(preferred_model or base_model)
    if not chain:
        return "detailed", "speed_router_no_models"

    recent = []
    for h in history[-4:]:
        role = str(h.get("role") or "").strip().lower()
        content = str(h.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            recent.append({"role": role, "content": content})

    router_prompt = (
        "Clasificá la consulta del usuario según profundidad de respuesta.\n"
        "Respondé SOLO una palabra: QUICK o DETAILED.\n"
        "QUICK: saludo, charla corta, ánimo, respuesta breve directa.\n"
        "DETAILED: análisis, explicación profunda, investigación, planes, código, herramientas, múltiples pasos."
    )
    msgs: list[dict[str, Any]] = [{"role": "system", "content": router_prompt}]
    msgs.extend(recent)
    msgs.append({"role": "user", "content": message})

    resp, model_used, retries, _errors = await _chat_create_with_fallback(
        client,
        chain,
        cancel_event=cancel_event,
        messages=msgs,
        stream=False,
        max_tokens=8,
        temperature=0.0,
        top_p=1.0,
        extra_body=_simple_chat_extra_body(chain[0]),
    )
    choices = getattr(resp, "choices", None) or []
    if not choices:
        return "detailed", f"speed_router_empty:{model_used}:r{retries}"
    msg = getattr(choices[0], "message", None)
    text = str(getattr(msg, "content", "") or "").strip().upper()
    if "QUICK" in text:
        return "quick", f"speed_router_llm:{model_used}:r{retries}"
    return "detailed", f"speed_router_llm:{model_used}:r{retries}"


def _format_runtime_error(e: Exception) -> str:
    try:
        txt = str(e or "").strip()
    except Exception:
        txt = ""
    if not txt:
        try:
            if getattr(e, "args", None):
                txt = " ".join(str(x) for x in e.args if str(x).strip()).strip()
        except Exception:
            txt = ""
    name = type(e).__name__ if e is not None else "Error"
    return f"{name}: {txt}" if txt else name


def _extract_urls(text: str, limit: int = 8) -> list[str]:
    urls: list[str] = []
    for u in re.findall(r"https?://[^\s)>\]\"']+", text or ""):
        if u not in urls:
            urls.append(u)
        if len(urls) >= limit:
            break
    return urls


def _tool_result_failed(tool_name: str, result: str) -> bool:
    t = result or ""
    if tool_name == "web_search":
        return t.startswith("WEB_SEARCH_UNAVAILABLE")
    if tool_name == "run_windows_command":
        try:
            data = json.loads(t)
            return str(data.get("status") or "") not in ("executed", "dry_run")
        except Exception:
            return True
    return "Tool error" in t


def _confidence_from_context(
    tool_calls: int,
    had_errors: bool,
    research_request: bool,
    answer_text: str,
    web_result_text: str,
) -> float:
    score = 0.65
    if tool_calls > 0:
        score += min(0.2, tool_calls * 0.03)
    if had_errors:
        score -= 0.22
    if research_request:
        urls_in_answer = _extract_urls(answer_text)
        urls_in_web = _extract_urls(web_result_text)
        if urls_in_answer:
            score += 0.1
        elif urls_in_web:
            score += 0.03
        else:
            score -= 0.15
    return max(0.05, min(0.99, round(score, 2)))


async def _agent_stream_normal(
    message: str,
    history: list[dict],
    system_prompt: str = "",
    model_override: str = "",
    harness_override: str = "",
    folder_id: str = "",
    sandbox_root: str = "",
    conversation_id: str = "",
    dry_run: bool = False,
    simple_chat: bool = False,
    internet_enabled: bool = True,
    tools_mode: str = "auto",
    cancel_event: Optional[asyncio.Event] = None,
) -> AsyncGenerator[str, None]:
    """
    Multi-step tool-calling agent. Yields SSE data lines.
    Event types: step | chunk | error | confidence | done
    """
    from guardrails.validator import validate_input

    safety = validate_input(message)
    if not safety.get("valid", True):
        err = safety.get("error", "Query rejected by safety filter.")
        yield f"data: {json.dumps({'type': 'error', 'text': err})}\n\n"
        return

    requested_tools_mode = str(tools_mode or "auto").strip().lower()
    if requested_tools_mode not in ("auto", "with_tools", "without_tools"):
        requested_tools_mode = "auto"

    client, model = _get_client()
    if simple_chat:
        # Fast path: skip task router and keep model chain short for low latency.
        provider = (Config.LLM_PROVIDER or "").strip().lower()
        preferred_model = str(model_override or "").strip()
        smalltalk_model = str(os.getenv("AGENT_SMALLTALK_MODEL", "gemma-3-4b-it-q4_0")).strip()
        # llama.cpp can serve only the currently loaded model efficiently.
        # For simple chat, avoid cross-alias fallbacks that tend to timeout.
        if provider == "llamacpp":
            preferred_model = str(model or "").strip()
        elif not preferred_model and smalltalk_model:
            preferred_model = smalltalk_model
        task_area = "chat_general"
        route_conf = 1.0
        route_reason = "simple_mode"
        primary_model = preferred_model or model
        fallback_models = []
        route = {
            "primary_model": primary_model,
            "fallback_models": fallback_models,
            "profile": "simple",
        }
        model_chain = _build_model_chain(model, route)
    else:
        task_area, route_conf, route_reason = _classify_task_area(message, mode="normal")
        route = _resolve_task_route(task_area)
        route = _route_with_model_override(route, model_override)
        model_chain = _build_model_chain(model, route)
    limits = _agent_limits()
    started_at = time.time()
    tool_calls = 0
    had_tool_errors = False
    final_chunks: list[str] = []
    last_tool_name: str | None = None
    last_tool_result: str | None = None
    force_tools = _is_research_request(message) or _is_action_request(message)
    is_research = _is_research_request(message)
    llm_retries_total = 0
    model_used = model_chain[0]
    if not simple_chat:
        yield f"data: {json.dumps({'type': 'step', 'text': 'task_router', 'args': {'area': task_area, 'confidence': route_conf, 'reason': route_reason, 'primary_model': route.get('primary_model'), 'fallback_models': route.get('fallback_models'), 'profile': route.get('profile')}})}\n\n"

    prompt_text = _simple_chat_system_prompt() if simple_chat else _compose_system_prompt(system_prompt, harness_override)
    messages: list[dict] = [{"role": "system", "content": prompt_text}]
    for h in history[-12:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})

    if not simple_chat:
        mem_lines = _retrieve_memory(message, conversation_id, _safe_folder_id(folder_id), top_k=5)
        if mem_lines:
            messages.append({
                "role": "system",
                "content": "Memoria relevante previa:\n" + "\n".join(f"- {m}" for m in mem_lines),
            })
        if is_research:
            messages.append({
                "role": "system",
                "content": (
                    "Research mode: use web/local tools first, provide URLs, and mark confidence as low when evidence is insufficient."
                ),
            })
    messages.append({"role": "user", "content": message})

    # Simple mode: answer directly with no tool-calling.
    if simple_chat:
        try:
            timeout_fast = _simple_chat_timeout_sec()
            fast_kwargs: dict[str, Any] = {
                "messages": messages,
                "stream": False,
                "max_tokens": 72,
                "temperature": 0.6,
                "top_p": 0.9,
                "extra_body": _simple_chat_extra_body(model_chain[0] if model_chain else primary_model),
            }
            if timeout_fast > 0:
                fast_kwargs["timeout"] = timeout_fast
            resp_fast, model_used, retries, _errors = await _chat_create_with_fallback(
                client,
                model_chain,
                cancel_event=cancel_event,
                **fast_kwargs,
            )
            llm_retries_total += retries
            if retries > 0:
                yield f"data: {json.dumps({'type': 'step', 'text': 'task_router.llm_fallback', 'args': {'used_model': model_used, 'retries': retries}})}\n\n"
            choices_fast = getattr(resp_fast, "choices", None) or []
            if choices_fast:
                msg_fast = getattr(choices_fast[0], "message", None)
                txt_fast = str(getattr(msg_fast, "content", "") or "").strip()
                if txt_fast:
                    final_chunks.append(txt_fast)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': txt_fast})}\n\n"
            if not final_chunks:
                errs = ""
                if _errors:
                    errs = " | " + " | ".join(str(x) for x in _errors[:2])
                raise RuntimeError(f"No se recibió texto del modelo{errs}")
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        except Exception as e:
            err_txt = _format_runtime_error(e)
            yield f"data: {json.dumps({'type': 'error', 'text': f'Simple chat error: {err_txt}'})}\n\n"
            _record_router_metric(task_area, model_used, False, int((time.time() - started_at) * 1000), llm_retries_total, "simple", err_txt)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        final_text = "".join(final_chunks)
        confidence = _confidence_from_context(
            tool_calls=0,
            had_errors=False,
            research_request=False,
            answer_text=final_text,
            web_result_text="",
        )
        yield f"data: {json.dumps({'type': 'confidence', 'score': confidence, 'tool_calls': 0})}\n\n"
        if conversation_id:
            try:
                fid = _safe_folder_id(folder_id)
                _append_memory(conversation_id, fid, "user", message)
                _append_memory(conversation_id, fid, "assistant", final_text)
            except Exception:
                pass
        _record_router_metric(
            task_area,
            model_used,
            True,
            int((time.time() - started_at) * 1000),
            llm_retries_total,
            "simple",
            route_reason,
        )
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Resolve tool policy from UI.
    if requested_tools_mode == "without_tools":
        available_tools = []
        force_tools = False
    elif requested_tools_mode == "with_tools":
        available_tools = list(TOOLS)
    else:
        available_tools = _tools_for_message(message)

    if not internet_enabled:
        available_tools = [
            t for t in available_tools
            if t.get("function", {}).get("name") != "web_search"
        ]
    if _safe_folder_id(folder_id):
        available_tools = [
            t for t in available_tools
            if t.get("function", {}).get("name") != "search_local_knowledge"
        ]
    if requested_tools_mode != "auto":
        yield f"data: {json.dumps({'type': 'step', 'text': 'tools.policy', 'args': {'mode': requested_tools_mode, 'internet_enabled': bool(internet_enabled), 'tools_available': [t.get('function', {}).get('name') for t in available_tools]}})}\n\n"

    loop = asyncio.get_event_loop()
    emitted_final = False
    normal_timeout = _normal_chat_timeout_sec()

    def _raise_if_cancelled() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError("run cancelled by user")

    for iteration in range(limits["max_iterations"]):
        _raise_if_cancelled()
        if (time.time() - started_at) >= limits["max_wall_sec"]:
            yield f"data: {json.dumps({'type': 'error', 'text': 'Agent wall-time limit reached before completion.'})}\n\n"
            break

        try:
            _extra: dict = {}
            if available_tools:
                _extra["tools"] = available_tools
                # "required" breaks many llama.cpp builds — use "auto" always.
                # The fallback logic in _chat_create_with_fallback will retry
                # without tools if the model can't handle them.
                _extra["tool_choice"] = "auto"
            req_kwargs: dict[str, Any] = {"messages": messages, "stream": False, **_extra}
            if normal_timeout is not None:
                req_kwargs["timeout"] = normal_timeout
            resp, model_used, retries, _errors = await _chat_create_with_fallback(
                client,
                model_chain,
                cancel_event=cancel_event,
                **req_kwargs,
            )
            llm_retries_total += retries
            if retries > 0:
                yield f"data: {json.dumps({'type': 'step', 'text': 'task_router.llm_fallback', 'args': {'used_model': model_used, 'retries': retries}})}\n\n"
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        except Exception as e2:
            err_txt = _format_runtime_error(e2)
            lower_err = err_txt.lower()
            is_timeout = isinstance(e2, TimeoutError) or ("timeout" in lower_err) or ("timed out" in lower_err)
            # If normal route timed out, try one last quick simple-chat fallback
            # so casual queries do not end as hard errors.
            if is_timeout and requested_tools_mode != "with_tools":
                try:
                    quick_messages: list[dict] = [{"role": "system", "content": _simple_chat_system_prompt()}]
                    for h in history[-8:]:
                        if h.get("role") in ("user", "assistant") and h.get("content"):
                            quick_messages.append({"role": h["role"], "content": h["content"]})
                    quick_messages.append({"role": "user", "content": message})
                    quick_timeout = _simple_chat_timeout_sec()
                    quick_kwargs: dict[str, Any] = {
                        "messages": quick_messages,
                        "stream": False,
                        "max_tokens": 96,
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "extra_body": _simple_chat_extra_body(model_chain[0] if model_chain else model),
                    }
                    if quick_timeout > 0:
                        quick_kwargs["timeout"] = max(8, min(quick_timeout, 25))
                    resp_quick, model_used_quick, retries_quick, _errors_quick = await _chat_create_with_fallback(
                        client,
                        model_chain,
                        cancel_event=cancel_event,
                        **quick_kwargs,
                    )
                    llm_retries_total += retries_quick
                    if retries_quick > 0:
                        yield f"data: {json.dumps({'type': 'step', 'text': 'task_router.llm_fallback', 'args': {'used_model': model_used_quick, 'retries': retries_quick}})}\n\n"
                    choices_quick = getattr(resp_quick, "choices", None) or []
                    if choices_quick:
                        msg_quick = getattr(choices_quick[0], "message", None)
                        txt_quick = str(getattr(msg_quick, "content", "") or "").strip()
                        if txt_quick:
                            final_chunks.append(txt_quick)
                            yield f"data: {json.dumps({'type': 'chunk', 'text': txt_quick})}\n\n"
                            confidence = _confidence_from_context(
                                tool_calls=tool_calls,
                                had_errors=had_tool_errors,
                                research_request=is_research,
                                answer_text=txt_quick,
                                web_result_text=(last_tool_result or ""),
                            )
                            yield f"data: {json.dumps({'type': 'confidence', 'score': confidence, 'tool_calls': int(tool_calls)})}\n\n"
                            _record_router_metric(task_area, model_used_quick, True, int((time.time() - started_at) * 1000), llm_retries_total, "normal", f"{route_reason}|timeout_fallback_simple")
                            yield f"data: {json.dumps({'type': 'done'})}\n\n"
                            return
                except Exception:
                    pass
            yield f"data: {json.dumps({'type': 'error', 'text': f'LLM error: {err_txt}'})}\n\n"
            _record_router_metric(task_area, model_used, False, int((time.time() - started_at) * 1000), llm_retries_total, "normal", err_txt)
            return

        choices = getattr(resp, "choices", None)
        # _chat_create_with_fallback guarantees choices is not None, but be safe.
        if choices is None:
            yield f"data: {json.dumps({'type': 'error', 'text': 'LLM returned no choices after all fallbacks'})}\n\n"
            return
        if not choices:
            yield f"data: {json.dumps({'type': 'error', 'text': 'LLM returned empty choices'})}\n\n"
            return

        choice = choices[0]
        msg = getattr(choice, "message", None)
        finish_reason = getattr(choice, "finish_reason", None)
        msg_tool_calls = getattr(msg, "tool_calls", None) if msg else None

        # Direct answer path: when the model responded without tool calls,
        # use that response immediately and avoid a second streaming request.
        if not msg_tool_calls:
            direct_text = str(getattr(msg, "content", "") or "").strip()
            if not direct_text:
                try:
                    recovery_messages = messages + [{
                        "role": "system",
                        "content": "Respondé ahora en texto plano, breve y en el mismo idioma del usuario. No uses herramientas.",
                    }]
                    fill_kwargs: dict[str, Any] = {"messages": recovery_messages, "stream": False}
                    if normal_timeout is not None:
                        fill_kwargs["timeout"] = max(10, min(normal_timeout, 30))
                    resp_fill, model_used_fill, retries_fill, _errors_fill = await _chat_create_with_fallback(
                        client,
                        model_chain,
                        cancel_event=cancel_event,
                        **fill_kwargs,
                    )
                    llm_retries_total += retries_fill
                    if retries_fill > 0:
                        yield f"data: {json.dumps({'type': 'step', 'text': 'task_router.llm_fallback', 'args': {'used_model': model_used_fill, 'retries': retries_fill}})}\n\n"
                    choices_fill = getattr(resp_fill, "choices", None) or []
                    if choices_fill:
                        msg_fill = getattr(choices_fill[0], "message", None)
                        direct_text = str(getattr(msg_fill, "content", "") or "").strip()
                except Exception:
                    direct_text = ""
            if direct_text:
                final_chunks.append(direct_text)
                yield f"data: {json.dumps({'type': 'chunk', 'text': direct_text})}\n\n"
                emitted_final = True
                break

        if finish_reason == "tool_calls" and msg_tool_calls:
            messages.append({
                "role": "assistant",
                "content": (getattr(msg, "content", "") or ""),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg_tool_calls
                ],
            })

            hard_stop = False
            for tc in msg_tool_calls:
                if tool_calls >= limits["max_tool_calls"]:
                    yield f"data: {json.dumps({'type': 'error', 'text': 'Agent tool-call limit reached.'})}\n\n"
                    hard_stop = True
                    break
                fn = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    fn_args = {}

                yield f"data: {json.dumps({'type': 'step', 'text': fn, 'args': fn_args})}\n\n"
                await asyncio.sleep(0)
                try:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, execute_tool, fn, fn_args, folder_id, sandbox_root, dry_run),
                        timeout=float(limits["tool_timeout_sec"]),
                    )
                except asyncio.TimeoutError:
                    result = f"Tool error ({fn}): timeout after {limits['tool_timeout_sec']}s. RETRY_HINT: reduce scope or split command."

                tool_calls += 1
                last_tool_name = fn
                last_tool_result = result

                if _tool_result_failed(fn, result):
                    had_tool_errors = True
                    if fn == "web_search":
                        fallback_args = {"query": fn_args.get("query", message)}
                        yield f"data: {json.dumps({'type': 'step', 'text': 'fallback.search_local_knowledge', 'args': fallback_args})}\n\n"
                        fb = await loop.run_in_executor(None, execute_tool, "search_local_knowledge", fallback_args, folder_id, sandbox_root, dry_run)
                        tool_calls += 1
                        last_tool_name = "search_local_knowledge"
                        last_tool_result = fb
                        result = f"{result}\n\nFallback(search_local_knowledge):\n{fb}"

                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

            if hard_stop:
                break

            if last_tool_name == "run_windows_command" and last_tool_result:
                summary = _summarize_windows_command_result(last_tool_result)
                try:
                    cmd_data = json.loads(last_tool_result)
                    if str(cmd_data.get("status") or "") == "needs_confirmation":
                        yield f"data: {json.dumps({'type': 'step', 'text': 'command_confirmation_required', 'args': {'command': cmd_data.get('command', ''), 'cwd': cmd_data.get('cwd', ''), 'sandbox_root': cmd_data.get('sandbox_root', ''), 'idempotency_key': cmd_data.get('idempotency_key', ''), 'operation_class': cmd_data.get('operation_class', ''), 'mode': cmd_data.get('mode', ''), 'reason': cmd_data.get('message', ''), 'reason_key': cmd_data.get('reason_key', '')}})}\n\n"
                except Exception:
                    pass
                final_chunks.append(summary)
                yield f"data: {json.dumps({'type': 'chunk', 'text': summary})}\n\n"
                emitted_final = True
                break
            continue

        try:
            emitted_any = False
            stream, model_used, retries, _errors = await _chat_create_with_fallback(
                client,
                model_chain,
                cancel_event=cancel_event,
                messages=messages,
                stream=True,
                timeout=120,
            )
            llm_retries_total += retries
            if retries > 0:
                yield f"data: {json.dumps({'type': 'step', 'text': 'task_router.llm_fallback', 'args': {'used_model': model_used, 'retries': retries}})}\n\n"
        except Exception as e:
            had_tool_errors = True
            yield f"data: {json.dumps({'type': 'error', 'text': f'Stream error: {e}'})}\n\n"
            emitted_final = True
            break
        try:
            async for chunk in stream:
                _raise_if_cancelled()
                chunk_choices = getattr(chunk, "choices", None)
                if not chunk_choices:
                    continue
                delta = getattr(chunk_choices[0], "delta", None)
                delta_content = getattr(delta, "content", None) if delta else None
                if delta_content:
                    emitted_any = True
                    final_chunks.append(delta_content)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': delta_content})}\n\n"
                    await asyncio.sleep(0)
            if not emitted_any:
                if last_tool_result:
                    summary = _summarize_tool_result(last_tool_name, last_tool_result)
                    final_chunks.append(summary)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': summary})}\n\n"
                else:
                    # Some providers/models return an empty stream; retry once as non-stream.
                    recovered = ""
                    try:
                        resp_ns, model_used_ns, retries_ns, _errors_ns = await _chat_create_with_fallback(
                            client,
                            model_chain,
                            cancel_event=cancel_event,
                            messages=messages,
                            stream=False,
                            timeout=120,
                        )
                        llm_retries_total += retries_ns
                        if retries_ns > 0:
                            yield f"data: {json.dumps({'type': 'step', 'text': 'task_router.llm_fallback', 'args': {'used_model': model_used_ns, 'retries': retries_ns}})}\n\n"
                        choices_ns = getattr(resp_ns, "choices", None) or []
                        if choices_ns:
                            msg_ns = getattr(choices_ns[0], "message", None)
                            recovered = str(getattr(msg_ns, "content", "") or "").strip()
                    except Exception:
                        recovered = ""

                    if recovered:
                        final_chunks.append(recovered)
                        yield f"data: {json.dumps({'type': 'chunk', 'text': recovered})}\n\n"
                    else:
                        # Second recovery attempt forcing plain text and no tools.
                        recovered2 = ""
                        try:
                            recovery_messages2 = messages + [{
                                "role": "system",
                                "content": "Respondé en texto plano, breve y útil. No llames herramientas.",
                            }]
                            resp_ns2, model_used_ns2, retries_ns2, _errors_ns2 = await _chat_create_with_fallback(
                                client,
                                model_chain,
                                cancel_event=cancel_event,
                                messages=recovery_messages2,
                                stream=False,
                                timeout=90,
                            )
                            llm_retries_total += retries_ns2
                            if retries_ns2 > 0:
                                yield f"data: {json.dumps({'type': 'step', 'text': 'task_router.llm_fallback', 'args': {'used_model': model_used_ns2, 'retries': retries_ns2}})}\n\n"
                            choices_ns2 = getattr(resp_ns2, "choices", None) or []
                            if choices_ns2:
                                msg_ns2 = getattr(choices_ns2[0], "message", None)
                                recovered2 = str(getattr(msg_ns2, "content", "") or "").strip()
                        except Exception:
                            recovered2 = ""
                        if recovered2:
                            final_chunks.append(recovered2)
                            yield f"data: {json.dumps({'type': 'chunk', 'text': recovered2})}\n\n"
                        else:
                            txt = "El modelo no devolvió texto en este intento. Reintentá."
                            final_chunks.append(txt)
                            yield f"data: {json.dumps({'type': 'chunk', 'text': txt})}\n\n"
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        except Exception as e:
            had_tool_errors = True
            yield f"data: {json.dumps({'type': 'error', 'text': f'Stream error: {e}'})}\n\n"
        emitted_final = True
        break

    if not emitted_final:
        if last_tool_result:
            summary = _summarize_tool_result(last_tool_name, last_tool_result)
            final_chunks.append(summary)
            yield f"data: {json.dumps({'type': 'chunk', 'text': summary})}\n\n"
        else:
            txt = "No se genero una respuesta util. Proba de nuevo."
            final_chunks.append(txt)
            yield f"data: {json.dumps({'type': 'chunk', 'text': txt})}\n\n"

    final_text = "".join(final_chunks)
    if is_research and final_text and not _extract_urls(final_text) and last_tool_result:
        sources = _extract_urls(last_tool_result, limit=5)
        if sources:
            src_text = "\n\nFuentes:\n" + "\n".join(f"- {u}" for u in sources)
            yield f"data: {json.dumps({'type': 'chunk', 'text': src_text})}\n\n"
            final_text += src_text

    confidence = _confidence_from_context(
        tool_calls=tool_calls,
        had_errors=had_tool_errors,
        research_request=is_research,
        answer_text=final_text,
        web_result_text=last_tool_result or "",
    )
    yield f"data: {json.dumps({'type': 'confidence', 'score': confidence, 'tool_calls': tool_calls})}\n\n"

    if conversation_id:
        try:
            fid = _safe_folder_id(folder_id)
            _append_memory(conversation_id, fid, "user", message)
            _append_memory(conversation_id, fid, "assistant", final_text)
        except Exception:
            pass

    _record_router_metric(
        task_area,
        model_used,
        not had_tool_errors,
        int((time.time() - started_at) * 1000),
        llm_retries_total,
        "normal",
        route_reason,
    )

    yield f"data: {json.dumps({'type': 'done'})}\n\n"

async def _run_internal_agent_once(
    message: str,
    history: list[dict],
    system_prompt: str = "",
    model_override: str = "",
    harness_override: str = "",
    folder_id: str = "",
    sandbox_root: str = "",
    conversation_id: str = "",
    dry_run: bool = False,
    cancel_event: Optional[asyncio.Event] = None,
) -> dict:
    text_chunks: list[str] = []
    steps: list[dict] = []
    error_text = ""
    confidence = None
    async for raw in _agent_stream_normal(
        message,
        history,
        system_prompt,
        model_override,
        harness_override,
        folder_id,
        sandbox_root,
        conversation_id,
        dry_run,
        cancel_event=cancel_event,
    ):
        if not raw.startswith("data: "):
            continue
        payload = raw[6:].strip()
        if not payload:
            continue
        try:
            ev = json.loads(payload)
        except Exception:
            continue
        et = ev.get("type")
        if et == "chunk":
            text_chunks.append(ev.get("text", ""))
        elif et == "step":
            steps.append({"tool": ev.get("text", ""), "args": ev.get("args", {})})
        elif et == "error":
            error_text = ev.get("text", "")
        elif et == "confidence":
            confidence = ev.get("score")
    return {
        "text": "".join(text_chunks).strip(),
        "steps": steps,
        "error": error_text.strip(),
        "confidence": confidence,
    }


def _extract_json_object(text: str) -> dict:
    src = (text or "").strip()
    if not src:
        return {}
    try:
        return json.loads(src)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", src)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def _plan_markdown_from_json(plan: dict) -> str:
    """
    Renderiza salida de modo plan en formato secuencial (una pregunta por turno).
    Formato esperado (recomendado):
    {
      "phase": "question" | "final",
      "stage": {
        "name": "...",
        "goal": "...",
        "alternatives": [{"title":"...","tradeoff":"..."}],
        "question": "..."
      },
      "final": {
        "summary": "...",
        "question": "¿Querés ejecutar el plan, editarlo o descartarlo?"
      }
    }
    """
    phase = str(plan.get("phase") or "").strip().lower()
    out: list[str] = []

    if phase == "final":
        final = plan.get("final") if isinstance(plan.get("final"), dict) else {}
        summary = str(final.get("summary") or plan.get("summary") or "").strip()
        question = str(final.get("question") or plan.get("final_question") or "").strip()
        out.append("## Plan consolidado")
        if summary:
            out.append(summary)
            out.append("")
        out.append(question or "¿Querés ejecutar el plan, editarlo o descartarlo?")
        return "\n".join(out).strip()

    stage = plan.get("stage") if isinstance(plan.get("stage"), dict) else {}
    name = str(stage.get("name") or plan.get("stage_name") or "Siguiente decisión").strip()
    goal = str(stage.get("goal") or plan.get("goal") or "").strip()
    alts = stage.get("alternatives")
    if not isinstance(alts, list):
        alts = plan.get("alternatives") if isinstance(plan.get("alternatives"), list) else []
    question = str(stage.get("question") or plan.get("question") or "").strip()

    out.append("## Plan propuesto")
    out.append(f"### {name}")
    if goal:
        out.append(f"- Objetivo: {goal}")
    if alts:
        out.append("- Alternativas:")
        for j, a in enumerate(alts, 1):
            if isinstance(a, dict):
                title = str(a.get("title") or f"Opción {j}").strip()
                tradeoff = str(a.get("tradeoff") or "").strip()
            else:
                title = str(a).strip() or f"Opción {j}"
                tradeoff = ""
            out.append(f"  - {j}. {title}" + (f" — {tradeoff}" if tradeoff else ""))
    out.append(f"- Decisión requerida: {question or '¿Qué opción elegís para continuar?'}")
    return "\n".join(out).strip()


def _plan_text_has_options(text: str) -> bool:
    t = (text or "").lower()
    has_consolidated = "plan consolidado" in t
    has_final = "ejecutar el plan" in t and "editar el plan" in t and "descartar" in t
    has_opts = ("alternativa" in t) or ("opción" in t) or ("opcion" in t)
    has_decision = ("decisión" in t) or ("decision" in t) or ("eleg" in t) or ("pregunta" in t)
    return has_consolidated or has_final or (has_opts and has_decision)


def _count_plan_decisions(history: list[dict], current_message: str = "") -> int:
    """
    Cuenta decisiones ya tomadas en modo plan a partir de mensajes de usuario.
    """
    patt = re.compile(
        r"(elijo esta alternativa|elijo|opción elegida|opcion elegida|otra:|mi elección|mi eleccion)",
        re.IGNORECASE,
    )
    n = 0
    for h in history:
        if str(h.get("role") or "") != "user":
            continue
        content = str(h.get("content") or "")
        if patt.search(content):
            n += 1
    if patt.search(current_message or ""):
        n += 1
    return n


async def _plan_stream(
    message: str,
    history: list[dict],
    system_prompt: str = "",
    model_override: str = "",
    harness_override: str = "",
    cancel_event: Optional[asyncio.Event] = None,
) -> AsyncGenerator[str, None]:
    from guardrails.validator import validate_input
    safety = validate_input(message)
    if not safety.get("valid", True):
        err = safety.get("error", "Query rejected by safety filter.")
        yield f"data: {json.dumps({'type': 'error', 'text': err})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    started_at = time.time()
    client, model = _get_client()
    task_area, route_conf, route_reason = _classify_task_area(message, mode="plan")
    route = _resolve_task_route(task_area)
    route = _route_with_model_override(route, model_override)
    model_chain = _build_model_chain(model, route)
    model_used = model_chain[0]
    llm_retries_total = 0
    decision_count = _count_plan_decisions(history, message)
    max_plan_decisions = 3
    force_final = decision_count >= max_plan_decisions
    yield f"data: {json.dumps({'type': 'step', 'text': 'task_router', 'args': {'area': task_area, 'confidence': route_conf, 'reason': route_reason, 'primary_model': route.get('primary_model'), 'fallback_models': route.get('fallback_models'), 'profile': route.get('profile')}})}\n\n"
    plan_protocol = (
        "Modo plan activo. Debés planificar de forma secuencial y pedir decisiones del usuario.\n"
        "No ejecutes herramientas.\n"
        "IMPORTANTE: hacé UNA sola pregunta por respuesta.\n"
        "Leé el historial para saber qué decisiones ya tomó el usuario y avanzá a la siguiente etapa.\n"
        "Si todavía faltan decisiones, devolvé solo la etapa actual en JSON puro:\n"
        "{\n"
        "  \"phase\": \"question\",\n"
        "  \"stage\": {\n"
        "    \"name\": \"...\",\n"
        "    \"goal\": \"...\",\n"
        "    \"alternatives\": [\n"
        "      {\"title\": \"...\", \"tradeoff\": \"...\"},\n"
        "      {\"title\": \"...\", \"tradeoff\": \"...\"}\n"
        "    ],\n"
        "    \"question\": \"...\"\n"
        "  }\n"
        "}\n"
        "Cuando ya tengas todas las decisiones del usuario, devolvé solo el cierre en JSON puro:\n"
        "{\n"
        "  \"phase\": \"final\",\n"
        "  \"final\": {\n"
        "    \"summary\": \"...\",\n"
        "    \"question\": \"¿Querés ejecutar el plan, editarlo o descartarlo?\"\n"
        "  }\n"
        "}\n"
        "Reglas:\n"
        "- En phase=question incluí 2 a 4 alternativas.\n"
        "- No incluyas todas las etapas juntas.\n"
        "- No agregues listas finales de acciones en texto fuera de question.\n"
        f"- Ya hay {decision_count} decisiones tomadas. Si hay {max_plan_decisions} o más, devolvé phase=final.\n"
        "- Si ya hay 2 o más decisiones, preferí cerrar con phase=final salvo que falte un dato crítico."
    )
    final_system = f"{_compose_system_prompt(system_prompt, harness_override)}\n\n{plan_protocol}"
    messages: list[dict] = [{"role": "system", "content": final_system}]
    for h in history[-14:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    try:
        plan_text = ""
        resp, model_used, retries, _errors = await _chat_create_with_fallback(
            client,
            model_chain,
            cancel_event=cancel_event,
            messages=messages,
            stream=False,
            timeout=60,
        )
        llm_retries_total += retries
        content = getattr(getattr(resp.choices[0], "message", None), "content", "") if getattr(resp, "choices", None) else ""
        plan_json = _extract_json_object(content)
        if plan_json and isinstance(plan_json, dict):
            plan_text = _plan_markdown_from_json(plan_json)
        else:
            plan_text = str(content or "").strip()

        phase = str(plan_json.get("phase") if isinstance(plan_json, dict) else "").strip().lower()
        if force_final and phase != "final":
            strict_final_messages = messages + [{
                "role": "user",
                "content": (
                    "Cierre obligatorio: ya se tomaron suficientes decisiones.\n"
                    "Respondé SOLO con JSON válido y phase=final.\n"
                    "No hagas más preguntas de etapa."
                ),
            }]
            resp_final, model_used_final, retries_final, _errors_final = await _chat_create_with_fallback(
                client,
                model_chain,
                cancel_event=cancel_event,
                messages=strict_final_messages,
                stream=False,
                timeout=60,
            )
            model_used = model_used_final or model_used
            llm_retries_total += retries_final
            content_final = getattr(getattr(resp_final.choices[0], "message", None), "content", "") if getattr(resp_final, "choices", None) else ""
            plan_json_final = _extract_json_object(content_final)
            if plan_json_final and isinstance(plan_json_final, dict):
                plan_text = _plan_markdown_from_json(plan_json_final)
            else:
                plan_text = str(content_final or plan_text).strip()

        if not _plan_text_has_options(plan_text):
            strict_messages = messages + [{
                "role": "user",
                "content": (
                    "Rehacelo en formato secuencial de modo plan.\n"
                    "Debe haber UNA sola pregunta en esta respuesta.\n"
                    "Devolvé JSON válido con phase=question o phase=final."
                ),
            }]
            resp2, model_used2, retries2, _errors2 = await _chat_create_with_fallback(
                client,
                model_chain,
                cancel_event=cancel_event,
                messages=strict_messages,
                stream=False,
                timeout=60,
            )
            model_used = model_used2 or model_used
            llm_retries_total += retries2
            content2 = getattr(getattr(resp2.choices[0], "message", None), "content", "") if getattr(resp2, "choices", None) else ""
            plan_json2 = _extract_json_object(content2)
            if plan_json2 and isinstance(plan_json2, dict):
                plan_text = _plan_markdown_from_json(plan_json2)
            else:
                plan_text = str(content2 or plan_text).strip()

        if not _plan_text_has_options(plan_text):
            plan_text = (
                "## Plan consolidado\n\n"
                "Ya tenemos decisiones suficientes para cerrar esta planificación.\n\n"
                "¿Querés ejecutar el plan, editarlo o descartarlo?"
                if force_final
                else
                "## Plan propuesto\n\n"
                "### Siguiente decisión\n"
                "- Alternativas:\n"
                "  - 1. Enfoque rápido — menor detalle, salida inmediata.\n"
                "  - 2. Enfoque equilibrado — equilibrio entre calidad y tiempo.\n"
                "  - 3. Enfoque profundo — más variantes y comparación detallada.\n"
                "- Decisión requerida: ¿Cuál alternativa elegís para avanzar?"
            )

        yield f"data: {json.dumps({'type': 'chunk', 'text': plan_text})}\n\n"
    except Exception as e:
        if isinstance(e, asyncio.CancelledError):
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        yield f"data: {json.dumps({'type': 'error', 'text': f'Plan mode error: {e}'})}\n\n"
        _record_router_metric(task_area, model_used, False, int((time.time() - started_at) * 1000), llm_retries_total, "plan", str(e))
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    _record_router_metric(task_area, model_used, True, int((time.time() - started_at) * 1000), llm_retries_total, "plan", route_reason)
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


async def _iterate_stream(
    message: str,
    history: list[dict],
    system_prompt: str = "",
    model_override: str = "",
    harness_override: str = "",
    folder_id: str = "",
    sandbox_root: str = "",
    conversation_id: str = "",
    dry_run: bool = False,
    cancel_event: Optional[asyncio.Event] = None,
) -> AsyncGenerator[str, None]:
    from guardrails.validator import validate_input

    safety = validate_input(message)
    if not safety.get("valid", True):
        err = safety.get("error", "Query rejected by safety filter.")
        yield f"data: {json.dumps({'type': 'error', 'text': err})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    started_at = time.time()
    client, model = _get_client()
    task_area, route_conf, route_reason = _classify_task_area(message, mode="iterate")

    # Fast-path: iterative execution is useful for actionable tasks.
    # For plain conversational prompts, bypass iterator planning/execution
    # and answer directly to avoid unnecessary latency and "Plan de ejecucion" noise.
    if task_area == "chat_general":
        async for ev in _agent_stream_normal(
            message,
            history,
            system_prompt,
            model_override,
            harness_override,
            folder_id,
            sandbox_root,
            conversation_id,
            dry_run,
            simple_chat=True,
            cancel_event=cancel_event,
        ):
            yield ev
        return

    route = _resolve_task_route(task_area)
    route = _route_with_model_override(route, model_override)
    model_chain = _build_model_chain(model, route)
    model_used = model_chain[0]
    llm_retries_total = 0
    yield f"data: {json.dumps({'type': 'step', 'text': 'task_router', 'args': {'area': task_area, 'confidence': route_conf, 'reason': route_reason, 'primary_model': route.get('primary_model'), 'fallback_models': route.get('fallback_models'), 'profile': route.get('profile')}})}\n\n"
    sys_prompt = _compose_system_prompt(system_prompt, harness_override)
    plan_req = (
        "Genera un plan de ejecucion en JSON puro con esta forma:\n"
        "{\"objective\":\"...\",\"stages\":[{\"name\":\"...\",\"goal\":\"...\",\"depends_on\":[],\"parallelizable\":false,\"checkpoint\":\"...\"}]}\n"
        "maximo 8 etapas. depends_on contiene nombres de etapas previas. Sin texto extra."
    )
    planning_messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"{plan_req}\n\nTarea: {message}"}]
    stages = [{"name": "Resolver tarea", "goal": message, "depends_on": [], "parallelizable": False, "checkpoint": "tarea_completa"}]
    objective = message

    try:
        plan_resp, model_used, retries, _errors = await _chat_create_with_fallback(
            client,
            model_chain,
            cancel_event=cancel_event,
            messages=planning_messages,
            stream=False,
            timeout=60,
        )
        llm_retries_total += retries
        content = getattr(getattr(plan_resp.choices[0], "message", None), "content", "") if getattr(plan_resp, "choices", None) else ""
        plan_json = _extract_json_object(content)
        if isinstance(plan_json, dict):
            objective = str(plan_json.get("objective") or message)
            raw_stages = plan_json.get("stages")
            if isinstance(raw_stages, list) and raw_stages:
                parsed = []
                for s in raw_stages[:8]:
                    if not isinstance(s, dict):
                        continue
                    name = str(s.get("name") or "").strip()
                    goal = str(s.get("goal") or "").strip()
                    if name and goal:
                        deps = s.get("depends_on")
                        dep_names = [str(d).strip() for d in deps] if isinstance(deps, list) else []
                        dep_names = [d for d in dep_names if d]
                        parsed.append({
                            "name": name,
                            "goal": goal,
                            "depends_on": dep_names,
                            "parallelizable": bool(s.get("parallelizable", False)),
                            "checkpoint": str(s.get("checkpoint") or f"{name.lower().replace(' ', '_')}_ok"),
                        })
                if parsed:
                    stages = parsed
    except Exception as e:
        _record_router_metric(task_area, model_used, False, int((time.time() - started_at) * 1000), llm_retries_total, "iterate", str(e))
        pass

    plan_md = ["## Plan de ejecucion (Iterador)\n", f"**Objetivo:** {objective}\n"]
    for i, s in enumerate(stages, 1):
        dep = ", ".join(s.get("depends_on") or []) or "ninguna"
        par = "si" if s.get("parallelizable") else "no"
        plan_md.append(f"{i}. **{s['name']}** - {s['goal']} (deps: {dep}, paralelo: {par})")
    yield f"data: {json.dumps({'type': 'chunk', 'text': '\\n'.join(plan_md) + '\\n\\n'})}\n\n"

    exec_history = history[-10:]
    max_retries = max(1, min(int(os.getenv("AGENT_ITERATOR_STAGE_RETRIES", "2")), 4))
    done: dict[str, dict] = {}
    pending = list(stages)
    # Use a lighter validator chain to reduce per-stage latency.
    validate_route = _resolve_task_route("chat_general")
    validate_chain = _build_model_chain(model, validate_route)

    async def execute_stage(stage: dict, idx: int) -> tuple[bool, str, str, list[str]]:
        stage_name = stage.get("name", "")
        stage_goal = stage.get("goal", "")
        logs = [f"### Etapa {idx}/{len(stages)}: {stage_name}\n"]
        stage_ok = False
        last_output = ""
        for attempt in range(1, max_retries + 1):
            stage_prompt = (
                f"Objetivo global: {objective}\\n"
                f"Etapa actual: {stage_name}\\n"
                f"Meta de etapa: {stage_goal}\\n"
                f"Intento {attempt}/{max_retries}. Ejecuta las acciones necesarias usando herramientas y reporta resultado."
            )
            result = await _run_internal_agent_once(
                stage_prompt,
                exec_history,
                system_prompt,
                model_override,
                harness_override,
                folder_id,
                sandbox_root,
                conversation_id,
                dry_run,
                cancel_event=cancel_event,
            )
            last_output = result.get("text") or result.get("error") or ""
            if result.get("error"):
                logs.append(f"Intento {attempt}: error -> {result['error']}\n")
            elif last_output:
                logs.append(f"Intento {attempt}: {last_output}\n")

            validate_prompt = (
                "Evalua si la etapa esta cumplida. Responde JSON puro:\n"
                "{\"passed\": true|false, \"reason\": \"...\"}\\n\\n"
                f"Etapa: {stage_name}\\n"
                f"Meta: {stage_goal}\\n"
                f"Salida: {last_output[:3000]}"
            )
            passed = False
            reason = ""
            try:
                val_resp, model_used, retries, _errors = await _chat_create_with_fallback(
                    client,
                    validate_chain,
                    cancel_event=cancel_event,
                    messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": validate_prompt}],
                    stream=False,
                    timeout=20,
                )
                llm_retries_total += retries
                val_content = getattr(getattr(val_resp.choices[0], "message", None), "content", "") if getattr(val_resp, "choices", None) else ""
                val_json = _extract_json_object(val_content)
                passed = bool(val_json.get("passed"))
                reason = str(val_json.get("reason") or "")
            except Exception:
                passed = bool(last_output and "error" not in last_output.lower())
                reason = "Validacion heuristica aplicada."

            if passed:
                stage_ok = True
                ok_reason = reason or "ok"
                logs.append(f"Etapa validada: {ok_reason}\n")
                break
            else:
                fail_reason = reason or "sin razon"
                logs.append(f"Etapa no validada: {fail_reason}. Reintentando...\n")
        return stage_ok, last_output, stage.get("checkpoint", ""), logs

    while pending:
        ready = [s for s in pending if all(dep in done for dep in (s.get("depends_on") or []))]
        if not ready:
            names = ", ".join(str(s.get("name", "")) for s in pending)
            yield f"data: {json.dumps({'type': 'error', 'text': f'No hay etapas ejecutables por dependencias. Pendientes: {names}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # By default run serially to keep artifact ordering coherent.
        # Can be switched back with AGENT_ITERATOR_PARALLEL=true.
        allow_parallel = (os.getenv("AGENT_ITERATOR_PARALLEL", "false") or "false").strip().lower() in ("1", "true", "yes")
        if allow_parallel:
            parallel_batch = [s for s in ready if s.get("parallelizable")]
            serial_batch = [s for s in ready if not s.get("parallelizable")]
            batch = parallel_batch if parallel_batch else serial_batch[:1]
        else:
            batch = ready[:1]

        tasks = []
        for s in batch:
            idx = stages.index(s) + 1
            tasks.append(execute_stage(s, idx))

        results = []
        if len(tasks) == 1:
            results.append(await tasks[0])
        else:
            results = list(await asyncio.gather(*tasks))

        for stage_obj, stage_result in zip(batch, results):
            stage_name = str(stage_obj.get("name") or "")
            stage_ok, last_output, checkpoint, logs = stage_result
            for log_text in logs:
                yield f"data: {json.dumps({'type': 'chunk', 'text': log_text})}\n\n"
            if not stage_ok:
                yield f"data: {json.dumps({'type': 'chunk', 'text': f'No se pudo completar la etapa \"{stage_name}\" tras {max_retries} intentos.\\n\\n'})}\n\n"
                _save_snapshot(conversation_id, {
                    "objective": objective,
                    "status": "failed",
                    "failed_stage": stage_name,
                    "stages": stages,
                    "done": done,
                })
                _record_router_metric(task_area, model_used, False, int((time.time() - started_at) * 1000), llm_retries_total, "iterate", f"stage_failed:{stage_name}")
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            done[stage_name] = {"output": last_output, "checkpoint": checkpoint}
            pending = [p for p in pending if p is not stage_obj]
            exec_history = (exec_history + [{"role": "assistant", "content": last_output}])[-12:]
            _save_snapshot(conversation_id, {
                "objective": objective,
                "status": "running",
                "stages": stages,
                "done": done,
            })

    _save_snapshot(conversation_id, {
        "objective": objective,
        "status": "completed",
        "stages": stages,
        "done": done,
    })
    _record_router_metric(task_area, model_used, True, int((time.time() - started_at) * 1000), llm_retries_total, "iterate", route_reason)
    yield f"data: {json.dumps({'type': 'chunk', 'text': '## Iteracion finalizada\\nSe completaron y validaron todas las etapas del plan.'})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"

async def _agent_stream(
    message: str,
    history: list[dict],
    system_prompt: str = "",
    model_override: str = "",
    harness_override: str = "",
    llamacpp_overrides: Optional[dict[str, Any]] = None,
    folder_id: str = "",
    sandbox_root: str = "",
    mode: str = "normal",
    conversation_id: str = "",
    dry_run: bool = False,
    internet_enabled: bool = True,
    tools_mode: str = "auto",
) -> AsyncGenerator[str, None]:
    run_id = uuid.uuid4().hex[:12]
    cancel_event = _register_run_cancel(run_id)
    run_started_perf = time.perf_counter()
    run_started_ms = int(time.time() * 1000)
    phase_starts: dict[str, float] = {}
    phase_durations: dict[str, int] = {}
    trace: dict[str, Any] = {
        "run_id": run_id,
        "conversation_id": conversation_id,
        "folder_id": _safe_folder_id(folder_id),
        "sandbox_root": sandbox_root,
        "mode": (mode or "normal").strip().lower(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "started_at_ms": run_started_ms,
        "input": {"message": message, "history_size": len(history)},
        "internet_enabled": bool(internet_enabled),
        "tools_mode": str(tools_mode or "auto"),
        "timing": {},
        "events": [],
    }

    def _now_ms() -> int:
        return int(time.time() * 1000)

    def _elapsed_ms() -> int:
        return int((time.perf_counter() - run_started_perf) * 1000)

    def _trace_event(ev: dict[str, Any]) -> None:
        item = dict(ev or {})
        item.setdefault("ts_ms", _now_ms())
        item.setdefault("dt_ms_from_start", _elapsed_ms())
        trace["events"].append(item)
        _devlog_emit_trace({
            "run_id": run_id,
            "conversation_id": conversation_id,
            **item,
        })

    def _phase_start(name: str, args: Optional[dict[str, Any]] = None) -> None:
        if name in phase_starts:
            return
        phase_starts[name] = time.perf_counter()
        _trace_event({
            "type": "phase.start",
            "text": name,
            "args": args or {},
        })

    def _phase_end(name: str, args: Optional[dict[str, Any]] = None) -> None:
        started = phase_starts.pop(name, None)
        duration_ms: Optional[int] = None
        if started is not None:
            duration_ms = int((time.perf_counter() - started) * 1000)
            phase_durations[f"{name}_ms"] = duration_ms
        payload: dict[str, Any] = {
            "type": "phase.end",
            "text": name,
            "args": args or {},
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        _trace_event(payload)

    async def _stream_and_trace(inner: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
        router_phase_open = False
        llm_phase_open = False
        first_chunk_recorded = False
        try:
            async for ev in inner:
                if ev.startswith("data: "):
                    payload = ev[6:].strip()
                    if payload:
                        try:
                            parsed = json.loads(payload)
                            if isinstance(parsed, dict):
                                ev_type = str(parsed.get("type") or "")
                                ev_text = str(parsed.get("text") or "")
                                ev_args = parsed.get("args")
                                if ev_type == "step" and ev_text == "task_router":
                                    if not router_phase_open:
                                        _phase_start("router", ev_args if isinstance(ev_args, dict) else {})
                                        router_phase_open = True
                                elif ev_type == "chunk":
                                    chunk_text = str(parsed.get("text") or "")
                                    if not llm_phase_open:
                                        if router_phase_open:
                                            _phase_end("router", {"reason": "first_chunk"})
                                            router_phase_open = False
                                        _phase_start("llm_call")
                                        llm_phase_open = True
                                    if chunk_text.strip() and not first_chunk_recorded:
                                        first_chunk_recorded = True
                                        ttft = _elapsed_ms()
                                        trace["timing"]["ttft_ms"] = ttft
                                        _trace_event({
                                            "type": "phase.mark",
                                            "text": "first_token",
                                            "args": {"ttft_ms": ttft},
                                        })
                                elif ev_type == "error":
                                    if router_phase_open:
                                        _phase_end("router", {"reason": "error"})
                                        router_phase_open = False
                                    if llm_phase_open:
                                        _phase_end("llm_call", {"reason": "error"})
                                        llm_phase_open = False
                                elif ev_type == "done":
                                    if router_phase_open:
                                        _phase_end("router", {"reason": "done"})
                                        router_phase_open = False
                                    if llm_phase_open:
                                        _phase_end("llm_call", {"reason": "done"})
                                        llm_phase_open = False
                                _trace_event(parsed)
                            else:
                                _trace_event({"type": "raw", "payload": str(parsed)[:800]})
                        except Exception:
                            _trace_event({"type": "raw", "payload": payload[:800]})
                yield ev
        finally:
            # Close any lingering phases on abrupt stream termination.
            if "router" in phase_starts:
                _phase_end("router", {"reason": "stream_end"})
            if "llm_call" in phase_starts:
                _phase_end("llm_call", {"reason": "stream_end"})
            trace["finished_at"] = datetime.now().isoformat(timespec="seconds")
            trace["finished_at_ms"] = _now_ms()
            trace["timing"]["total_ms"] = _elapsed_ms()
            for k, v in phase_durations.items():
                trace["timing"][k] = v
            _persist_trace(run_id, trace)
            _emit_telemetry("run_completed", {
                "run_id": run_id,
                "conversation_id": conversation_id,
                "mode": trace.get("mode"),
                "event_count": len(trace.get("events") or []),
            })

    _trace_event({"type": "run", "run_id": run_id, "text": "run_start", "args": {"mode_requested": trace.get("mode")}})
    yield f"data: {json.dumps({'type': 'run', 'run_id': run_id})}\n\n"

    try:
        m = (mode or "normal").strip().lower()
        requested_tools_mode = str(tools_mode or "auto").strip().lower()
        if requested_tools_mode not in ("auto", "with_tools", "without_tools"):
            requested_tools_mode = "auto"
        depth_route = "detailed"
        depth_reason = "depth_router_default"
        # Compute effective path first.
        # In normal mode we delegate quick-vs-detailed routing to a tiny LLM router.
        effective_simple = (m == "simple")
        if m == "normal" and requested_tools_mode != "with_tools":
            _phase_start("depth_router")
            try:
                depth_route, depth_reason = await _llm_route_response_depth(
                    message,
                    history,
                    str(model_override or ""),
                    cancel_event=cancel_event,
                )
            except Exception as e:
                depth_route, depth_reason = "detailed", f"depth_router_error:{_format_runtime_error(e)}"
            _phase_end("depth_router", {"route": depth_route, "reason": depth_reason})
            yield f"data: {json.dumps({'type': 'step', 'text': 'response.depth_router', 'args': {'route': depth_route, 'reason': depth_reason}})}\n\n"
            effective_simple = depth_route == "quick"

        # llama.cpp auto-switch by behavior/model override.
        # For simple smalltalk without explicit override, skip expensive switch/reload.
        should_switch = not (effective_simple and not str(model_override or "").strip() and not (llamacpp_overrides or {}))
        if should_switch:
            _phase_start("model_switch", {"model_override": str(model_override or "")})
            ok_switch, switch_info = await _ensure_llamacpp_model_for_override(model_override, llamacpp_overrides)
            _phase_end("model_switch", {"ok": bool(ok_switch), "detail": str(switch_info or "")})
            if not ok_switch:
                yield f"data: {json.dumps({'type': 'error', 'text': switch_info})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            if switch_info not in ("provider_not_llamacpp", "no_override", "already_selected"):
                yield f"data: {json.dumps({'type': 'step', 'text': 'llamacpp.model_switch', 'args': {'detail': switch_info}})}\n\n"
            # Always run warmup in llama.cpp after a switch check (even if already_selected),
            # so we avoid first-call stalls/empty completions on cold model state.
            if (Config.LLM_PROVIDER or "").strip().lower() == "llamacpp":
                _phase_start("warmup", {"model_alias": str(Config.LLAMACPP_MODEL_ALIAS or "")})
                ok_warm, warm_info = await _ensure_llamacpp_warmup(str(Config.LLAMACPP_MODEL_ALIAS or "modelo"))
                _phase_end("warmup", {"ok": bool(ok_warm), "detail": str(warm_info or "")})
                if not ok_warm:
                    yield f"data: {json.dumps({'type': 'error', 'text': f'No se pudo completar warmup del modelo: {warm_info}'})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return
        elif (Config.LLM_PROVIDER or "").strip().lower() == "llamacpp":
            # If no switch happened for this request, still do explicit warmup for
            # the currently active model used by the chat.
            _maybe_autostart_llamacpp(force=False, reason="chat_request")
            _phase_start("warmup", {"model_alias": str(Config.LLAMACPP_MODEL_ALIAS or "")})
            ok_warm, warm_info = await _ensure_llamacpp_warmup(str(Config.LLAMACPP_MODEL_ALIAS or "modelo"))
            _phase_end("warmup", {"ok": bool(ok_warm), "detail": str(warm_info or "")})
            if not ok_warm:
                yield f"data: {json.dumps({'type': 'error', 'text': f'No se pudo completar warmup del modelo: {warm_info}'})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

        if m == "plan":
            trace["mode_effective"] = "plan"
            async for ev in _stream_and_trace(_plan_stream(message, history, system_prompt, model_override, harness_override, cancel_event=cancel_event)):
                yield ev
            return
        if m == "iterate":
            trace["mode_effective"] = "iterate"
            async for ev in _stream_and_trace(_iterate_stream(message, history, system_prompt, model_override, harness_override, folder_id, sandbox_root, conversation_id, dry_run, cancel_event=cancel_event)):
                yield ev
            return
        if m == "simple":
            trace["mode_effective"] = "simple"
            async for ev in _stream_and_trace(_agent_stream_normal(message, history, system_prompt, model_override, harness_override, folder_id, sandbox_root, conversation_id, dry_run, simple_chat=True, internet_enabled=internet_enabled, tools_mode=tools_mode, cancel_event=cancel_event)):
                yield ev
            return

        if m == "normal" and effective_simple and requested_tools_mode != "with_tools":
            trace["mode_effective"] = "simple_auto_llm_router"
            async for ev in _stream_and_trace(_agent_stream_normal(message, history, system_prompt, model_override, harness_override, folder_id, sandbox_root, conversation_id, dry_run, simple_chat=True, internet_enabled=internet_enabled, tools_mode=tools_mode, cancel_event=cancel_event)):
                yield ev
            return

        # Auto-escalate clearly multi-step build requests to iterator mode so the
        # agent keeps executing beyond a single command (useful in Dev/Código).
        if m == "normal" and _looks_like_multistep_build_task(message):
            trace["mode_effective"] = "iterate_auto"
            async for ev in _stream_and_trace(_iterate_stream(message, history, system_prompt, model_override, harness_override, folder_id, sandbox_root, conversation_id, dry_run, cancel_event=cancel_event)):
                yield ev
            return

        trace["mode_effective"] = "normal"
        async for ev in _stream_and_trace(_agent_stream_normal(message, history, system_prompt, model_override, harness_override, folder_id, sandbox_root, conversation_id, dry_run, internet_enabled=internet_enabled, tools_mode=tools_mode, cancel_event=cancel_event)):
            yield ev
    except asyncio.CancelledError:
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return
    finally:
        _unregister_run_cancel(run_id)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(application: FastAPI):
    _reload_config_runtime()
    _maybe_autostart_llamacpp(force=True, reason="lifespan")

    yield

    # ── Shutdown: kill managed llama.cpp ─────────────────────────────────────
    if _llamacpp_proc and _llamacpp_proc.poll() is None:
        print("[unlz] Stopping llama.cpp…")
        _llamacpp_proc.terminate()
        try:
            _llamacpp_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _llamacpp_proc.kill()


app = FastAPI(title="UNLZ Agent Server", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat")
async def chat(req: ChatRequest):
    _reload_config_runtime()
    return StreamingResponse(
        _agent_stream(
            req.message,
            req.history,
            req.system_prompt,
            req.model_override,
            req.harness_override,
            req.llamacpp_overrides,
            req.folder_id,
            req.sandbox_root,
            req.mode,
            req.conversation_id,
            req.dry_run,
            req.internet_enabled,
            req.tools_mode,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/actions/run_windows_command")
async def action_run_windows_command(req: CommandActionRequest):
    payload = _run_windows_command({
        "command": req.command,
        "cwd": req.cwd,
        "sandbox_root": req.sandbox_root,
        "timeout_sec": req.timeout_sec,
        "idempotency_key": req.idempotency_key,
        "approved": True,
    })
    try:
        return json.loads(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"invalid command action result: {e}")


@app.get("/health")
async def health():
    _reload_config_runtime()
    provider = Config.LLM_PROVIDER
    components: dict = {}

    if provider == "llamacpp":
        # Self-heal: if llama.cpp is configured but down, retry start in background
        # with cooldown, so the user doesn't need to press "Start" manually.
        global _llamacpp_health_autostart_last_ts
        now = time.time()
        # Throttle health-driven autostart; frontend polls /health frequently.
        if (now - _llamacpp_health_autostart_last_ts) >= 20:
            _llamacpp_health_autostart_last_ts = now
            _maybe_autostart_llamacpp(force=False, reason="health")
        rt = _llamacpp_runtime_state()
        ok = rt.get("state") == "ready"
        components["llm"] = {
            "status": "ok" if ok else ("warning" if rt.get("state") == "loading" else "error"),
            "details": str(rt.get("details") or ""),
            "state": rt.get("state"),
        }
    elif provider == "ollama":
        ok = _http_reachable(f"{Config.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=1.5)
        components["llm"] = {
            "status": "ok" if ok else "error",
            "details": f"Ollama — {Config.OLLAMA_MODEL}" if ok else "Ollama unreachable",
            "state": "ready" if ok else "not_loaded",
        }
    else:
        has_key = bool(Config.OPENAI_API_KEY)
        components["llm"] = {
            "status": "ok" if has_key else "warning",
            "details": "OpenAI configured" if has_key else "OpenAI key missing",
            "state": "ready" if has_key else "not_loaded",
        }

    rag_ok = os.path.exists(Config.RAG_STORAGE_PATH)
    components["rag"] = {
        "status": "ok" if rag_ok else "warning",
        "details": "Vector store ready" if rag_ok else "Run ingestion first",
    }

    data_ok = os.path.exists(Config.DATA_DIR)
    components["knowledge"] = {
        "status": "ok" if data_ok else "warning",
        "details": f"{len(list(Path(Config.DATA_DIR).iterdir()))} files" if data_ok else "Empty",
    }

    all_ok = all(v["status"] == "ok" for v in components.values())
    return {"status": "online" if all_ok else "degraded", "components": components}


@app.get("/connectors/health")
async def connectors_health():
    return {
        "status": "ok",
        "metrics": _CONNECTOR_METRICS,
    }


@app.get("/runs/{run_id}")
async def get_run_trace(run_id: str):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", (run_id or "").strip())
    p = _trace_path(safe)
    if not p.exists():
        raise HTTPException(status_code=404, detail="run trace not found")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"trace read error: {e}")


@app.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", (run_id or "").strip())
    if not safe:
        raise HTTPException(status_code=400, detail="invalid run id")
    ok = _set_run_cancel(safe)
    return {"status": "cancelling" if ok else "not_found", "run_id": safe}


@app.get("/snapshots")
async def list_snapshots_endpoint():
    return _list_snapshots()


@app.get("/snapshots/{conversation_id}")
async def get_snapshot(conversation_id: str):
    data = _load_snapshot(conversation_id)
    if not data:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return data


@app.post("/snapshots/{conversation_id}")
async def save_snapshot(conversation_id: str, payload: dict):
    _save_snapshot(conversation_id, payload or {})
    return {"success": True}


@app.get("/router/config")
async def get_router_config():
    return _load_task_router()


@app.post("/router/config")
async def save_router_config(payload: dict):
    if not isinstance(payload, dict) or not isinstance(payload.get("areas"), dict):
        raise HTTPException(status_code=400, detail="invalid router config")
    _save_task_router(payload)
    return {"success": True}


@app.get("/router/metrics")
async def get_router_metrics():
    return _router_metrics_summary()


@app.post("/router/recalibrate")
async def recalibrate_router(payload: dict | None = None):
    payload = payload or {}
    min_samples = max(4, int(payload.get("min_samples", 12)))
    return _recalibrate_router(min_samples=min_samples)


@app.get("/settings")
async def get_settings():
    env_path = Path(__file__).parent / ".env"
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
    _upsert_env_settings(payload)
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
# Harness management (native / little-coder / future harnesses)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/harnesses/status")
async def harnesses_status():
    _reload_config_runtime()
    _ensure_harness_dirs()
    meta = _read_harness_meta()
    claude_bin = _claude_code_bin()
    claude_installed = _claude_code_installed()
    claude_meta = (meta.get("claude-code") or {}) if isinstance(meta, dict) else {}
    claude_version = _claude_code_version(claude_bin) or str(claude_meta.get("version") or "")
    opencode_bin = _opencode_bin()
    opencode_installed = _opencode_installed()
    opencode_meta = (meta.get("opencode") or {}) if isinstance(meta, dict) else {}
    opencode_version = _opencode_version(opencode_bin) or str(opencode_meta.get("version") or "")
    little_dir = _little_coder_install_dir()
    little_installed = _little_coder_installed()
    little_meta = (meta.get("little-coder") or {}) if isinstance(meta, dict) else {}
    options = [
        {
            "id": "native",
            "label": "UNLZ-AGENT nativo",
            "installed": True,
            "version": "builtin",
            "path": "",
        },
        {
            "id": "claude-code",
            "label": "claude-code",
            "installed": claude_installed,
            "version": claude_version,
            "path": claude_bin,
        },
        {
            "id": "opencode",
            "label": "opencode",
            "installed": opencode_installed,
            "version": opencode_version,
            "path": opencode_bin,
        },
        {
            "id": "little-coder",
            "label": "little-coder",
            "installed": little_installed,
            "version": str(little_meta.get("version") or ""),
            "path": str(little_dir),
        },
    ]
    return {
        "active": (getattr(Config, "AGENT_HARNESS", "native") or "native").strip().lower(),
        "options": options,
    }


@app.post("/harnesses/install")
async def harnesses_install(req: HarnessInstallRequest):
    _reload_config_runtime()
    _ensure_harness_dirs()
    harness_id = (req.harness_id or "").strip().lower()
    if harness_id == "claude-code":
        install_errors: list[str] = []

        # 1) Preferred on Windows: winget
        try:
            if os.name == "nt" and shutil.which("winget"):
                proc = subprocess.run(
                    [
                        "winget", "install", "-e", "--id", "Anthropic.ClaudeCode",
                        "--accept-source-agreements", "--accept-package-agreements",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=360,
                )
                if proc.returncode != 0:
                    install_errors.append(f"winget: {(proc.stderr or proc.stdout or '').strip()[:400]}")
        except Exception as e:
            install_errors.append(f"winget exception: {e}")

        claude_bin = _claude_code_bin()

        # 2) Official script fallback
        if not claude_bin and os.name == "nt":
            try:
                ps_cmd = "irm https://claude.ai/install.ps1 | iex"
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=420,
                )
                if proc.returncode != 0:
                    install_errors.append(f"install.ps1: {(proc.stderr or proc.stdout or '').strip()[:400]}")
            except Exception as e:
                install_errors.append(f"install.ps1 exception: {e}")
            claude_bin = _claude_code_bin()

        # 3) NPM legacy fallback
        if not claude_bin and shutil.which("npm"):
            try:
                proc = subprocess.run(
                    ["npm", "install", "-g", "@anthropic-ai/claude-code"],
                    capture_output=True,
                    text=True,
                    timeout=420,
                )
                if proc.returncode != 0:
                    install_errors.append(f"npm: {(proc.stderr or proc.stdout or '').strip()[:400]}")
            except Exception as e:
                install_errors.append(f"npm exception: {e}")
            claude_bin = _claude_code_bin()

        if not claude_bin:
            detail = " | ".join([x for x in install_errors if x]) or "Unknown installation failure"
            raise HTTPException(500, f"No se pudo instalar claude-code: {detail}")

        version = _claude_code_version(claude_bin)
        meta = _read_harness_meta()
        if not isinstance(meta, dict):
            meta = {}
        meta["claude-code"] = {
            "version": version,
            "source": "official",
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "path": claude_bin,
        }
        _write_harness_meta(meta)
        _upsert_env_settings({
            "HARNESS_CLAUDE_CODE_BIN": claude_bin,
        })
        _reload_config_runtime()
        return {
            "status": "installed",
            "harness_id": "claude-code",
            "path": claude_bin,
            "version": version,
        }

    if harness_id == "opencode":
        install_errors: list[str] = []

        op_bin = _opencode_bin()

        # 2) npm fallback(s)
        npm_bin = _npm_bin()
        if not op_bin and npm_bin:
            for pkg in ("opencode-ai", "@opencode-ai/cli", "@opencode/cli"):
                try:
                    proc = subprocess.run(
                        [npm_bin, "install", "-g", pkg],
                        capture_output=True,
                        text=True,
                        timeout=420,
                    )
                    if proc.returncode != 0:
                        install_errors.append(f"npm {pkg}: {(proc.stderr or proc.stdout or '').strip()[:240]}")
                except Exception as e:
                    install_errors.append(f"npm {pkg} exception: {e}")
                op_bin = _opencode_bin()
                if op_bin:
                    break
        elif not op_bin:
            install_errors.append("npm no encontrado (instalá Node.js LTS o agregá npm.cmd al PATH)")

        if not op_bin:
            detail = " | ".join([x for x in install_errors if x]) or "Unknown installation failure"
            raise HTTPException(500, f"No se pudo instalar opencode: {detail}")

        version = _opencode_version(op_bin)
        meta = _read_harness_meta()
        if not isinstance(meta, dict):
            meta = {}
        meta["opencode"] = {
            "version": version,
            "source": "official",
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "path": op_bin,
        }
        _write_harness_meta(meta)
        _upsert_env_settings({
            "HARNESS_OPENCODE_BIN": op_bin,
        })
        _reload_config_runtime()
        return {
            "status": "installed",
            "harness_id": "opencode",
            "path": op_bin,
            "version": version,
        }

    if harness_id != "little-coder":
        raise HTTPException(400, f"Unsupported harness: {harness_id}")

    target_dir = _little_coder_install_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    # Download latest main snapshot from GitHub.
    zip_url = "https://codeload.github.com/itayinbarr/little-coder/zip/refs/heads/main"
    with tempfile.TemporaryDirectory(prefix="unlz-harness-") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "little-coder-main.zip"
        req_dl = Request(zip_url, headers={"User-Agent": "unlz-agent"})
        try:
            with urlopen(req_dl, timeout=180) as resp:
                zip_path.write_bytes(resp.read())
        except Exception as e:
            raise HTTPException(502, f"Download failed: {e}")

        extract_root = tmp_path / "extract"
        extract_root.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_root)
        except Exception as e:
            raise HTTPException(500, f"Extraction failed: {e}")

        candidates = [p for p in extract_root.iterdir() if p.is_dir()]
        if not candidates:
            raise HTTPException(500, "Invalid little-coder archive layout")
        src_dir = candidates[0]

        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_dir, target_dir)

    meta = _read_harness_meta()
    if not isinstance(meta, dict):
        meta = {}
    meta["little-coder"] = {
        "version": f"main-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "source": "https://github.com/itayinbarr/little-coder",
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "path": str(target_dir),
    }
    _write_harness_meta(meta)

    _upsert_env_settings({
        "HARNESS_LITTLE_CODER_DIR": str(target_dir),
    })
    _reload_config_runtime()

    return {
        "status": "installed",
        "harness_id": "little-coder",
        "path": str(target_dir),
        "version": str(meta["little-coder"].get("version") or ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# llama.cpp process management
# ─────────────────────────────────────────────────────────────────────────────

_llamacpp_proc: Optional[subprocess.Popen] = None
_llamacpp_switch_lock = asyncio.Lock()
_llamacpp_switching = False
_llamacpp_switching_target = ""
_llamacpp_switching_message = ""
_llamacpp_active_overrides: dict[str, Any] = {}
_llamacpp_warmup_lock = asyncio.Lock()
_llamacpp_warming = False
_llamacpp_warming_message = ""
_llamacpp_warm_signature = ""
_llamacpp_autostart_lock = threading.Lock()
_llamacpp_autostart_last_try_ts = 0.0
_llamacpp_autostart_fail_streak = 0
_llamacpp_health_autostart_last_ts = 0.0


def _maybe_autostart_llamacpp(force: bool = False, reason: str = "runtime") -> tuple[bool, str]:
    """
    Best-effort managed autostart for llama.cpp.
    Uses a cooldown to avoid restart storms when config is invalid.
    """
    global _llamacpp_autostart_last_try_ts, _llamacpp_autostart_fail_streak
    _reload_config_runtime()

    if (Config.LLM_PROVIDER or "").lower() != "llamacpp":
        return False, "provider_not_llamacpp"
    if not bool(getattr(Config, "LLAMACPP_AUTO_START", True)):
        return False, "autostart_disabled"
    if _llamacpp_api_healthy(timeout=0.9):
        _llamacpp_autostart_fail_streak = 0
        return False, "already_healthy"
    if _llamacpp_switching:
        return False, "switch_in_progress"

    exe = str(Config.LLAMACPP_EXECUTABLE or "").strip()
    model = str(Config.LLAMACPP_MODEL_PATH or "").strip()
    if not exe or not os.path.isfile(exe):
        return False, "missing_executable"
    if not model or not os.path.isfile(model):
        return False, "missing_model"
    build_num = _llamacpp_executable_build_number(exe)
    if not _llamacpp_is_model_compatible_with_build(model, str(Config.LLAMACPP_MODEL_ALIAS or ""), build_num):
        switched, detail = _auto_switch_to_compatible_model(reason=reason)
        if switched:
            exe = str(Config.LLAMACPP_EXECUTABLE or "").strip()
            model = str(Config.LLAMACPP_MODEL_PATH or "").strip()
            build_num = _llamacpp_executable_build_number(exe)
        else:
            # Avoid restart loops with incompatible binary/model combinations.
            _llamacpp_autostart_fail_streak = max(_llamacpp_autostart_fail_streak, 6)
            return False, f"incompatible_binary:b{build_num}:{detail}"

    if _llamacpp_proc and _llamacpp_proc.poll() is None:
        listeners = _pids_listening_on_tcp_port(Config.LLAMACPP_PORT)
        if listeners:
            rt = _llamacpp_runtime_state()
            if str(rt.get("state") or "") == "loading":
                return False, "managed_process_loading"
        # Managed process alive but no listener/health: recycle it.
        _llamacpp_stop_internal()
    if len(_pids_listening_on_tcp_port(Config.LLAMACPP_PORT)) > 0:
        return False, "external_listener_present"

    now = time.time()
    base_cooldown = max(3, int(getattr(Config, "LLAMACPP_AUTO_START_COOLDOWN_SEC", 12)))
    fail_backoff = min(120, base_cooldown * (2 ** min(_llamacpp_autostart_fail_streak, 3)))
    cooldown = base_cooldown if _llamacpp_autostart_fail_streak <= 0 else fail_backoff
    if not force and (now - _llamacpp_autostart_last_try_ts) < cooldown:
        return False, "cooldown_active"

    with _llamacpp_autostart_lock:
        now = time.time()
        if not force and (now - _llamacpp_autostart_last_try_ts) < cooldown:
            return False, "cooldown_active"
        _llamacpp_autostart_last_try_ts = now
        try:
            if _llamacpp_proc and _llamacpp_proc.poll() is None:
                _llamacpp_stop_internal()
            res = _llamacpp_start_internal()
            # Verify readiness briefly to avoid "started but dead" loops.
            deadline = time.time() + 12
            while time.time() < deadline:
                if _llamacpp_api_healthy(timeout=1.0):
                    _llamacpp_autostart_fail_streak = 0
                    detail = f"auto-started ({reason})"
                    print(f"[unlz] llama.cpp {detail} — {Config.LLAMACPP_MODEL_ALIAS}")
                    return True, str(res.get("status") or "started")
                time.sleep(0.6)
            _llamacpp_autostart_fail_streak += 1
            _llamacpp_stop_internal()
            return False, "start_unhealthy"
        except Exception as e:
            _llamacpp_autostart_fail_streak += 1
            print(f"[unlz] llama.cpp autostart failed ({reason}): {e}")
            return False, f"start_failed:{e}"


def _pids_listening_on_tcp_port(port: int) -> set[int]:
    pids: set[int] = set()
    try:
        out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, encoding="utf-8", errors="ignore")
    except Exception:
        return pids
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.search(r"^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$", line, flags=re.IGNORECASE)
        if not m:
            continue
        local_port = int(m.group(1))
        pid = int(m.group(2))
        if local_port == int(port) and pid > 0:
            pids.add(pid)
    return pids


def _kill_pid_tree(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        if os.name == "nt":
            # /T kills child processes too. We don't fail hard on non-zero exit.
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return True
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


def _normalize_llamacpp_overrides(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    try:
        if raw.get("context_size") is not None and str(raw.get("context_size")).strip() != "":
            out["context_size"] = int(raw.get("context_size"))
    except Exception:
        pass
    try:
        if raw.get("n_gpu_layers") is not None and str(raw.get("n_gpu_layers")).strip() != "":
            out["n_gpu_layers"] = int(raw.get("n_gpu_layers"))
    except Exception:
        pass
    if "flash_attn" in raw and raw.get("flash_attn") is not None:
        val = raw.get("flash_attn")
        if isinstance(val, bool):
            out["flash_attn"] = val
        elif isinstance(val, str):
            out["flash_attn"] = val.strip().lower() in ("1", "true", "yes", "on")
    ctk = str(raw.get("cache_type_k") or "").strip()
    if ctk:
        out["cache_type_k"] = ctk
    ctv = str(raw.get("cache_type_v") or "").strip()
    if ctv:
        out["cache_type_v"] = ctv
    ea = str(raw.get("extra_args") or "").strip()
    if ea:
        out["extra_args"] = ea
    return out


def _llamacpp_effective_runtime(overrides: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    ov = _normalize_llamacpp_overrides(overrides)
    return {
        "context_size": int(ov.get("context_size", Config.LLAMACPP_CONTEXT_SIZE)),
        "n_gpu_layers": int(ov.get("n_gpu_layers", Config.LLAMACPP_N_GPU_LAYERS)),
        "flash_attn": bool(ov.get("flash_attn", Config.LLAMACPP_FLASH_ATTN)),
        "cache_type_k": str(ov.get("cache_type_k", Config.LLAMACPP_CACHE_TYPE_K or "")).strip(),
        "cache_type_v": str(ov.get("cache_type_v", Config.LLAMACPP_CACHE_TYPE_V or "")).strip(),
        "extra_args": str(ov.get("extra_args", Config.LLAMACPP_EXTRA_ARGS or "")).strip(),
    }


def _runtime_signature(model_path: str, model_alias: str, runtime_cfg: dict[str, Any]) -> str:
    payload = {
        "model_path": str(model_path or "").strip().lower(),
        "model_alias": _slug_alias(model_alias or ""),
        "runtime": runtime_cfg,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _llamacpp_warmup_sync(timeout_sec: int = 180) -> tuple[bool, str]:
    """
    Force a tiny completion to warm model weights + template path.
    This is intentionally outside request-level generation timeout budgets.
    """
    base = f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}"
    url = f"{base}/v1/chat/completions"
    model_alias = str(Config.LLAMACPP_MODEL_ALIAS or "").strip()
    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": "Warmup only."},
            {"role": "user", "content": "ok"},
        ],
        "max_tokens": 1,
        "temperature": 0,
        "stream": False,
    }
    if model_alias:
        payload["model"] = model_alias
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=max(10, int(timeout_sec))) as resp:
            body = (resp.read() or b"").decode("utf-8", errors="ignore")
            if 200 <= int(getattr(resp, "status", 0) or 0) < 300:
                # Accept partial/minimal JSON as successful warmup.
                if ("\"choices\"" in body) or ("\"content\"" in body) or ("\"id\"" in body):
                    return True, "ok"
                return True, "ok_minimal"
            return False, f"http_{getattr(resp, 'status', '0')}"
    except Exception as e:
        return False, str(e)


async def _ensure_llamacpp_warmup(target_label: str = "") -> tuple[bool, str]:
    global _llamacpp_warming, _llamacpp_warming_message, _llamacpp_warm_signature
    if (Config.LLM_PROVIDER or "").strip().lower() != "llamacpp":
        return True, "provider_not_llamacpp"
    runtime_cfg = _llamacpp_effective_runtime(_llamacpp_active_overrides or {})
    sig = _runtime_signature(Config.LLAMACPP_MODEL_PATH or "", Config.LLAMACPP_MODEL_ALIAS or "", runtime_cfg)
    if _llamacpp_warm_signature == sig:
        return True, "already_warmed"
    if not _llamacpp_api_healthy(timeout=1.0):
        return False, "llamacpp_not_ready"

    async with _llamacpp_warmup_lock:
        runtime_cfg = _llamacpp_effective_runtime(_llamacpp_active_overrides or {})
        sig = _runtime_signature(Config.LLAMACPP_MODEL_PATH or "", Config.LLAMACPP_MODEL_ALIAS or "", runtime_cfg)
        if _llamacpp_warm_signature == sig:
            return True, "already_warmed"
        label = (target_label or str(Config.LLAMACPP_MODEL_ALIAS or "modelo")).strip()
        _llamacpp_warming = True
        _llamacpp_warming_message = f"Cargando el modelo {label}…"
        try:
            ok, detail = await asyncio.to_thread(_llamacpp_warmup_sync, 180)
            if ok:
                _llamacpp_warm_signature = sig
                return True, "warmed"
            return False, f"warmup_failed: {detail}"
        finally:
            _llamacpp_warming = False
            _llamacpp_warming_message = ""


def _llamacpp_executable_build_number(exe_path: str) -> int:
    """
    Best-effort extraction of llama.cpp build id from executable path,
    e.g. "...\\llama.cpp-b8553\\llama-server.exe" -> 8553.
    """
    try:
        m = re.search(r"b(\d{3,6})", str(exe_path or ""), flags=re.IGNORECASE)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0


def _llamacpp_model_needs_newer_build(model_path: str, model_alias: str) -> bool:
    """
    Heuristic guard for models unsupported by older llama.cpp builds.
    Current known case: Gemma 4 (arch gemma4) requires newer builds.
    """
    s = f"{str(model_path or '')} {str(model_alias or '')}".lower()
    return ("gemma-4" in s) or ("gemma4" in s)


def _is_mmproj_candidate(model_entry: dict[str, Any]) -> bool:
    name = str(model_entry.get("name") or "").lower()
    stem = str(model_entry.get("stem") or "").lower()
    alias = str(model_entry.get("alias") or "").lower()
    blob = f"{name}|{stem}|{alias}"
    return "mmproj" in blob


def _strip_quant_tail(alias: str) -> str:
    s = _slug_alias(alias or "")
    # Remove trailing quant-like suffixes (q5-k-p, iq4-xs, f16, bf16, etc.)
    s = re.sub(r"-(?:ud-)?q\d[\w-]*$", "", s)
    s = re.sub(r"-iq\d[\w-]*$", "", s)
    s = re.sub(r"-(?:f16|bf16|fp16|fp8|int8|int4)$", "", s)
    return s.strip("-")


def _pick_best_model_match(target_raw: str, models: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """
    Resolve model_override to best local GGUF candidate.
    Excludes mmproj entries and supports fuzzy family fallback.
    """
    target_raw = str(target_raw or "").strip()
    if not target_raw:
        return None

    clean_models = [m for m in models if not _is_mmproj_candidate(m)]
    if not clean_models:
        return None

    target = _slug_alias(target_raw)
    target_low = target_raw.lower()

    # 1) Exact alias
    for c in clean_models:
        if c.get("alias", "") == target:
            return c

    # 2) Exact stem/name text
    for c in clean_models:
        stem = str(c.get("stem", "")).lower()
        name = str(c.get("name", "")).lower()
        if target_low == stem or target_low == name:
            return c

    # 3) Substring blob
    for c in clean_models:
        blob = f"{c.get('alias','')}|{str(c.get('stem','')).lower()}|{str(c.get('name','')).lower()}"
        if target_low in blob or target in blob:
            return c

    # 4) Family fallback (strip quant tails)
    core = _strip_quant_tail(target)
    if core:
        family = []
        for c in clean_models:
            a = str(c.get("alias") or "")
            if a.startswith(core) or core in a:
                family.append(c)
        if family:
            # Prefer same family with largest size (better quality).
            family.sort(key=lambda x: float(x.get("size_gb") or 0.0), reverse=True)
            return family[0]

    # 5) Coarse fallback by main model family hints
    hints = [h for h in ("qwen3.6-27b", "qwen3.6", "qwen") if h in target]
    if hints:
        for h in hints:
            fam = [c for c in clean_models if h in str(c.get("alias") or "")]
            if fam:
                fam.sort(key=lambda x: float(x.get("size_gb") or 0.0), reverse=True)
                return fam[0]

    return None


def _llamacpp_is_model_compatible_with_build(model_path: str, model_alias: str, build_num: int) -> bool:
    if build_num <= 0:
        return True
    if _llamacpp_model_needs_newer_build(model_path, model_alias) and build_num < 8900:
        return False
    return True


def _rank_fallback_candidate(path: str, alias: str, size_gb: float) -> tuple[int, float]:
    blob = f"{str(path or '').lower()} {str(alias or '').lower()}"
    score = 100
    if "qwen3.6" in blob or "qwen3-6" in blob:
        score = 0
    elif "qwen" in blob:
        score = 10
    elif "deepseek" in blob:
        score = 20
    elif "gemma-3" in blob or "gemma3" in blob:
        score = 30
    elif "llama" in blob:
        score = 40
    elif "mistral" in blob:
        score = 50
    # Prefer medium/large local models around ~20GB when tie-breaking.
    size_penalty = abs(float(size_gb or 0.0) - 20.0)
    return (score, size_penalty)


def _pick_compatible_fallback_model(exe_path: str, current_model_path: str) -> Optional[dict[str, Any]]:
    build_num = _llamacpp_executable_build_number(exe_path)
    models = _scan_gguf_models()
    current_norm = str(current_model_path or "").strip().lower()
    candidates: list[dict[str, Any]] = []
    for m in models:
        mpath = str(m.get("path") or "").strip()
        if not mpath:
            continue
        if current_norm and mpath.lower() == current_norm:
            continue
        if not os.path.isfile(mpath):
            continue
        malias = str(m.get("alias") or _slug_alias(Path(mpath).stem)).strip()
        if not _llamacpp_is_model_compatible_with_build(mpath, malias, build_num):
            continue
        candidates.append(m)
    if not candidates:
        return None
    candidates.sort(
        key=lambda m: _rank_fallback_candidate(
            str(m.get("path") or ""),
            str(m.get("alias") or ""),
            float(m.get("size_gb") or 0.0),
        )
    )
    return candidates[0]


def _auto_switch_to_compatible_model(reason: str = "compat") -> tuple[bool, str]:
    """
    Persistently switch LLAMACPP_MODEL_PATH/ALIAS to a compatible local GGUF
    when current model is incompatible with current llama.cpp build.
    """
    _reload_config_runtime()
    exe = str(Config.LLAMACPP_EXECUTABLE or "").strip()
    current_model = str(Config.LLAMACPP_MODEL_PATH or "").strip()
    if not exe or not os.path.isfile(exe):
        return False, "missing_executable"
    if not current_model:
        return False, "missing_current_model"
    pick = _pick_compatible_fallback_model(exe, current_model)
    if not pick:
        return False, "no_compatible_fallback"
    new_path = str(pick.get("path") or "").strip()
    new_alias = str(pick.get("alias") or "").strip() or _slug_alias(Path(new_path).stem)
    _upsert_env_settings({
        "LLAMACPP_MODEL_PATH": new_path,
        "LLAMACPP_MODEL_ALIAS": new_alias,
    })
    _reload_config_runtime()
    print(
        f"[unlz] modelo incompatible detectado; fallback automático aplicado ({reason}): "
        f"{new_alias} @ {new_path}"
    )
    return True, new_alias


def _build_llamacpp_args(overrides: Optional[dict[str, Any]] = None) -> list[str]:
    runtime_cfg = _llamacpp_effective_runtime(overrides)
    model_hint = f"{Config.LLAMACPP_MODEL_ALIAS} {Config.LLAMACPP_MODEL_PATH}".lower()
    is_vision = any(k in model_hint for k in ("vision", "-vl", "_vl", "qwen2.5-vl", "gemma-4-vision"))

    args = [
        Config.LLAMACPP_EXECUTABLE,
        "-m", Config.LLAMACPP_MODEL_PATH,
        "--alias", Config.LLAMACPP_MODEL_ALIAS,
        "--host", Config.LLAMACPP_HOST,
        "--port", str(Config.LLAMACPP_PORT),
        "-c", str(runtime_cfg["context_size"]),
        "-ngl", str(runtime_cfg["n_gpu_layers"]),
    ]
    if runtime_cfg["flash_attn"]:
        # Newer llama.cpp builds require an explicit value.
        args += ["--flash-attn", "on"]
    if runtime_cfg["cache_type_k"]:
        args += ["--cache-type-k", str(runtime_cfg["cache_type_k"])]
    if runtime_cfg["cache_type_v"]:
        args += ["--cache-type-v", str(runtime_cfg["cache_type_v"])]
    if runtime_cfg["extra_args"]:
        raw_tokens = str(runtime_cfg["extra_args"]).split()
        if is_vision:
            args += raw_tokens
        else:
            filtered: list[str] = []
            i = 0
            while i < len(raw_tokens):
                tok = raw_tokens[i]
                low = tok.lower()
                if low in ("--image-min-tokens", "--image-max-tokens", "--batch-size", "--ubatch-size"):
                    i += 2  # drop flag + value
                    continue
                filtered.append(tok)
                i += 1
            args += filtered
    return args


def _llamacpp_runtime_state() -> dict:
    """
    Runtime state for UI blocking:
    - ready: model API available
    - loading: llama.cpp process reachable but model/API still loading, or auto-switch in progress
    - not_loaded: unavailable/stopped/misconfigured
    """
    if _llamacpp_switching:
        target = _llamacpp_switching_target or "modelo solicitado"
        detail = _llamacpp_switching_message or f"Cambiando a {target}…"
        return {"state": "loading", "details": detail}
    if _llamacpp_warming:
        detail = _llamacpp_warming_message or "Cargando el modelo, espere por favor…"
        return {"state": "loading", "details": detail}

    if not Config.LLAMACPP_EXECUTABLE or not os.path.isfile(Config.LLAMACPP_EXECUTABLE):
        return {"state": "not_loaded", "details": "llama.cpp no configurado (falta ejecutable)."}
    if not Config.LLAMACPP_MODEL_PATH or not os.path.isfile(Config.LLAMACPP_MODEL_PATH):
        return {"state": "not_loaded", "details": "Modelo no cargado (falta LLAMACPP_MODEL_PATH válido)."}
    build_num = _llamacpp_executable_build_number(str(Config.LLAMACPP_EXECUTABLE or ""))
    if _llamacpp_model_needs_newer_build(
        str(Config.LLAMACPP_MODEL_PATH or ""),
        str(Config.LLAMACPP_MODEL_ALIAS or ""),
    ) and build_num and build_num < 8900:
        return {
            "state": "not_loaded",
            "details": f"llama.cpp b{build_num} no soporta este modelo (Gemma 4). Actualizá llama.cpp.",
        }

    if _llamacpp_api_healthy(timeout=1.0):
        return {"state": "ready", "details": f"llama.cpp — {Config.LLAMACPP_MODEL_ALIAS}"}

    base = f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}"
    status_h, body_h = _http_get_text(f"{base}/health", timeout=1.0)
    body_l = (body_h or "").lower()
    managed_running = bool(_llamacpp_proc and _llamacpp_proc.poll() is None)
    has_listener = len(_pids_listening_on_tcp_port(Config.LLAMACPP_PORT)) > 0

    if status_h > 0:
        if status_h == 503 or "load" in body_l or "loading" in body_l:
            return {"state": "loading", "details": "Modelo cargando, esperá por favor…"}
        if managed_running or has_listener:
            return {"state": "loading", "details": "Servidor llama.cpp iniciando…"}
        return {"state": "not_loaded", "details": f"llama.cpp no listo (health {status_h})."}

    if managed_running:
        return {"state": "loading", "details": "Modelo cargando, esperá por favor…"}
    return {"state": "not_loaded", "details": f"llama.cpp no disponible (port {Config.LLAMACPP_PORT})."}


def _llamacpp_start_internal(overrides: Optional[dict[str, Any]] = None) -> dict:
    global _llamacpp_proc, _llamacpp_active_overrides, _llamacpp_warm_signature
    _reload_config_runtime()
    if not Config.LLAMACPP_EXECUTABLE:
        raise HTTPException(400, "LLAMACPP_EXECUTABLE not configured")
    if not os.path.isfile(Config.LLAMACPP_EXECUTABLE):
        raise HTTPException(400, f"Executable not found: {Config.LLAMACPP_EXECUTABLE}")
    if not os.path.isfile(Config.LLAMACPP_MODEL_PATH):
        raise HTTPException(400, f"Model not found: {Config.LLAMACPP_MODEL_PATH}")
    build_num = _llamacpp_executable_build_number(Config.LLAMACPP_EXECUTABLE)
    if not _llamacpp_is_model_compatible_with_build(
        Config.LLAMACPP_MODEL_PATH,
        str(Config.LLAMACPP_MODEL_ALIAS or ""),
        build_num,
    ):
        switched, detail = _auto_switch_to_compatible_model(reason="manual_start")
        if switched:
            _reload_config_runtime()
            build_num = _llamacpp_executable_build_number(Config.LLAMACPP_EXECUTABLE)
            if not _llamacpp_is_model_compatible_with_build(
                Config.LLAMACPP_MODEL_PATH,
                str(Config.LLAMACPP_MODEL_ALIAS or ""),
                build_num,
            ):
                raise HTTPException(
                    400,
                    f"Modelo incompatible con tu llama.cpp actual (b{build_num}). Actualizá llama.cpp.",
                )
        else:
            raise HTTPException(
                400,
                f"Modelo incompatible con tu llama.cpp actual (b{build_num}) y no se encontró fallback compatible ({detail}).",
            )

    if _llamacpp_proc and _llamacpp_proc.poll() is None:
        # Avoid stale "already running": recycle a zombie managed process that
        # has no healthy API nor active listener.
        if _llamacpp_api_healthy(timeout=0.9):
            return {"status": "already_running", "pid": _llamacpp_proc.pid}
        listeners = _pids_listening_on_tcp_port(Config.LLAMACPP_PORT)
        if listeners:
            return {"status": "already_running", "pid": _llamacpp_proc.pid}
        _llamacpp_stop_internal()

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    normalized_overrides = _normalize_llamacpp_overrides(overrides)

    def _spawn(local_overrides: dict[str, Any]) -> subprocess.Popen:
        return subprocess.Popen(
            _build_llamacpp_args(local_overrides),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )

    _llamacpp_proc = _spawn(normalized_overrides)
    _llamacpp_active_overrides = normalized_overrides
    _llamacpp_warm_signature = ""

    # If process exits immediately, retry once with safer args (drop extra_args).
    time.sleep(1.0)
    if _llamacpp_proc.poll() is not None:
        safe_overrides = dict(normalized_overrides)
        safe_overrides["extra_args"] = ""
        _llamacpp_proc = _spawn(safe_overrides)
        _llamacpp_active_overrides = safe_overrides
        _llamacpp_warm_signature = ""
        time.sleep(1.0)
        if _llamacpp_proc.poll() is not None:
            rc = _llamacpp_proc.poll()
            _llamacpp_proc = None
            raise HTTPException(
                500,
                f"llama.cpp no pudo iniciar (exit {rc}). Revisá modelo/args en Configuración.",
            )

    return {
        "status": "started",
        "pid": _llamacpp_proc.pid,
        "url": f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}/v1",
    }


def _llamacpp_stop_internal() -> dict:
    global _llamacpp_proc, _llamacpp_warm_signature
    _reload_config_runtime()
    killed_pids: list[int] = []
    managed_pid: Optional[int] = None

    if _llamacpp_proc is not None and _llamacpp_proc.poll() is None:
        managed_pid = _llamacpp_proc.pid
        try:
            _llamacpp_proc.terminate()
            _llamacpp_proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            try:
                _llamacpp_proc.kill()
                _llamacpp_proc.wait(timeout=2)
            except Exception:
                pass
        except Exception:
            pass
        finally:
            if managed_pid:
                killed_pids.append(managed_pid)
            _llamacpp_proc = None
            _llamacpp_warm_signature = ""
    else:
        _llamacpp_proc = None
        _llamacpp_warm_signature = ""

    port_pids = _pids_listening_on_tcp_port(Config.LLAMACPP_PORT)
    for pid in sorted(port_pids):
        if _kill_pid_tree(pid):
            killed_pids.append(pid)

    running = False
    for _ in range(12):
        running = _llamacpp_api_healthy(timeout=0.5)
        if not running:
            break
        time.sleep(0.25)

    if not killed_pids and not running:
        return {"status": "not_running", "running": False, "killed_pids": []}
    if running:
        return {"status": "still_running", "running": True, "killed_pids": sorted(set(killed_pids))}
    return {"status": "stopped", "running": False, "killed_pids": sorted(set(killed_pids))}


async def _ensure_llamacpp_model_for_override(
    model_override: str,
    runtime_overrides: Optional[dict[str, Any]] = None,
) -> tuple[bool, str]:
    """
    Ensure llama.cpp runtime matches request:
    - optional model switch by model_override
    - optional runtime arg overrides (behavior-level)
    Returns (ok, message).
    """
    if Config.LLM_PROVIDER != "llamacpp":
        return True, "provider_not_llamacpp"

    target_raw = str(model_override or "").strip()
    wanted_overrides = _normalize_llamacpp_overrides(runtime_overrides)
    picked = None
    target_path = str(Config.LLAMACPP_MODEL_PATH or "").strip()
    target_alias = str(Config.LLAMACPP_MODEL_ALIAS or "").strip()

    if target_raw:
        candidates = _scan_gguf_models()
        picked = _pick_best_model_match(target_raw, candidates)
        if picked is None:
            return False, f"No encontré un GGUF que coincida con '{target_raw}'."
        target_path = str(picked.get("path") or "").strip()
        target_alias = str(picked.get("alias") or "").strip() or _slug_alias(Path(target_path).stem)

    if not target_path:
        return False, "Ruta de modelo destino inválida."

    global _llamacpp_switching, _llamacpp_switching_target, _llamacpp_switching_message, _llamacpp_active_overrides
    async with _llamacpp_switch_lock:
        _reload_config_runtime()
        prev_provider = str(Config.LLM_PROVIDER or "llamacpp").strip() or "llamacpp"
        prev_model_path = str(Config.LLAMACPP_MODEL_PATH or "").strip()
        prev_model_alias = str(Config.LLAMACPP_MODEL_ALIAS or "").strip()
        prev_overrides = dict(_llamacpp_active_overrides or {})

        current_sig = _runtime_signature(
            Config.LLAMACPP_MODEL_PATH or "",
            Config.LLAMACPP_MODEL_ALIAS or "",
            _llamacpp_effective_runtime(prev_overrides),
        )
        target_sig = _runtime_signature(
            target_path,
            target_alias,
            _llamacpp_effective_runtime(wanted_overrides),
        )
        if current_sig == target_sig and _llamacpp_api_healthy(timeout=1.0):
            return True, "already_selected"

        switch_label = target_alias or target_raw or str(Config.LLAMACPP_MODEL_ALIAS or "local-model")
        _llamacpp_switching = True
        _llamacpp_switching_target = switch_label
        _llamacpp_switching_message = f"Cambiando configuración de {switch_label}…"
        try:
            # Persist only model/provider; runtime overrides are request-scoped.
            env_payload = {"LLM_PROVIDER": "llamacpp"}
            if target_path and target_path != prev_model_path:
                env_payload["LLAMACPP_MODEL_PATH"] = target_path
            if target_alias and target_alias != prev_model_alias:
                env_payload["LLAMACPP_MODEL_ALIAS"] = target_alias
            if len(env_payload) > 1:
                _upsert_env_settings(env_payload)
            else:
                _reload_config_runtime()

            _llamacpp_switching_message = "Reiniciando llama.cpp…"
            _llamacpp_stop_internal()
            _llamacpp_start_internal(wanted_overrides)
            _llamacpp_switching_message = "Modelo cargando, esperá por favor…"

            deadline = time.time() + 180
            while time.time() < deadline:
                if _llamacpp_api_healthy(timeout=1.2):
                    _llamacpp_switching_message = "Cargando el modelo, espere por favor…"
                    ok_warm, warm_info = await _ensure_llamacpp_warmup(switch_label)
                    if not ok_warm:
                        return False, f"Warmup falló para '{switch_label}': {warm_info}"
                    _reload_config_runtime()
                    return True, f"Modelo activo: {Config.LLAMACPP_MODEL_ALIAS}"
                await asyncio.sleep(0.7)

            # rollback
            rb_payload = {
                "LLM_PROVIDER": prev_provider,
                "LLAMACPP_MODEL_ALIAS": prev_model_alias,
            }
            if prev_model_path:
                rb_payload["LLAMACPP_MODEL_PATH"] = prev_model_path
            _upsert_env_settings(rb_payload)
            _llamacpp_switching_message = "Restaurando modelo anterior…"
            _llamacpp_stop_internal()
            _llamacpp_start_internal(prev_overrides)
            rb_deadline = time.time() + 60
            while time.time() < rb_deadline:
                if _llamacpp_api_healthy(timeout=1.0):
                    break
                await asyncio.sleep(0.6)
            return False, f"Timeout cargando modelo '{switch_label}'. Se restauró el modelo anterior."
        except HTTPException as he:
            try:
                rb_payload = {
                    "LLM_PROVIDER": prev_provider,
                    "LLAMACPP_MODEL_ALIAS": prev_model_alias,
                }
                if prev_model_path:
                    rb_payload["LLAMACPP_MODEL_PATH"] = prev_model_path
                _upsert_env_settings(rb_payload)
                _llamacpp_stop_internal()
                _llamacpp_start_internal(prev_overrides)
            except Exception:
                pass
            return False, str(he.detail)
        except Exception as e:
            try:
                rb_payload = {
                    "LLM_PROVIDER": prev_provider,
                    "LLAMACPP_MODEL_ALIAS": prev_model_alias,
                }
                if prev_model_path:
                    rb_payload["LLAMACPP_MODEL_PATH"] = prev_model_path
                _upsert_env_settings(rb_payload)
                _llamacpp_stop_internal()
                _llamacpp_start_internal(prev_overrides)
            except Exception:
                pass
            return False, f"Error cambiando modelo/configuración: {e}"
        finally:
            _llamacpp_switching = False
            _llamacpp_switching_target = ""
            _llamacpp_switching_message = ""


@app.post("/llamacpp/start")
async def llamacpp_start():
    return _llamacpp_start_internal()


@app.post("/llamacpp/stop")
async def llamacpp_stop():
    return _llamacpp_stop_internal()


@app.get("/llamacpp/status")
async def llamacpp_status():
    _reload_config_runtime()
    base = f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}"
    running = _llamacpp_api_healthy(timeout=1.0)
    managed = bool(_llamacpp_proc and _llamacpp_proc.poll() is None)
    return {
        "running": running,
        "managed": managed,
        "pid": _llamacpp_proc.pid if managed else None,
        "url": f"{base}/v1",
        "model": Config.LLAMACPP_MODEL_PATH,
        "alias": Config.LLAMACPP_MODEL_ALIAS,
    }


# ─────────────────────────────────────────────────────────────────────────────
# llama.cpp installer/update
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/llamacpp/installer/status")
async def llamacpp_installer_status():
    _reload_config_runtime()
    _ensure_llamacpp_default_dirs()
    if os.name != "nt":
        return {
            "supported": False,
            "reason": "Windows-only installer",
            "installed": False,
            "installed_version": "",
            "latest_version": "",
            "update_available": False,
            "executable": Config.LLAMACPP_EXECUTABLE,
        }

    meta = _read_llamacpp_install_meta()
    install_root = _llamacpp_install_root()
    exe = _find_llama_server_executable(install_root)
    configured_exe = Path(Config.LLAMACPP_EXECUTABLE) if Config.LLAMACPP_EXECUTABLE else None
    if not exe and configured_exe and configured_exe.exists():
        exe = configured_exe

    installed_version = str(meta.get("version", "")).strip()
    if not installed_version and exe:
        m = re.search(r"(b\d{3,6})", str(exe), flags=re.IGNORECASE)
        if m:
            installed_version = m.group(1).lower()

    latest_version = ""
    update_available = False
    release_error = ""
    try:
        latest = _github_latest_llamacpp_release()
        latest_version = str(latest.get("tag_name") or "")
        if latest_version:
            if installed_version:
                update_available = installed_version != latest_version
            else:
                update_available = False
    except Exception as e:
        release_error = str(e)

    return {
        "supported": True,
        "installed": bool(exe and exe.exists()),
        "installed_version": installed_version,
        "latest_version": latest_version,
        "update_available": update_available,
        "executable": str(exe) if exe else Config.LLAMACPP_EXECUTABLE,
        "release_error": release_error,
    }


@app.post("/llamacpp/installer/run")
async def llamacpp_installer_run():
    _reload_config_runtime()
    _ensure_llamacpp_default_dirs()
    if os.name != "nt":
        raise HTTPException(400, "Installer is supported only on Windows.")

    try:
        latest = _github_latest_llamacpp_release()
    except Exception as e:
        raise HTTPException(502, f"Could not query llama.cpp releases: {e}")

    tag = str(latest.get("tag_name") or "").strip()
    assets = latest.get("assets") or []
    asset = _pick_windows_asset(assets)
    if not asset:
        raise HTTPException(502, "No compatible Windows .zip asset found in latest llama.cpp release.")

    asset_url = asset.get("browser_download_url")
    asset_name = asset.get("name") or "llama.cpp-win.zip"
    if not asset_url:
        raise HTTPException(502, "Invalid release asset metadata.")

    install_root = _llamacpp_install_root()
    install_root.mkdir(parents=True, exist_ok=True)
    version_dir = install_root / (tag or "latest")
    version_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="unlz-llamacpp-") as tmp:
        zip_path = Path(tmp) / asset_name
        req = Request(asset_url, headers={"User-Agent": "unlz-agent"})
        try:
            with urlopen(req, timeout=180) as resp:
                zip_path.write_bytes(resp.read())
        except Exception as e:
            raise HTTPException(502, f"Download failed: {e}")

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(version_dir)
        except Exception as e:
            raise HTTPException(500, f"Extraction failed: {e}")

    exe = _find_llama_server_executable(version_dir)
    if not exe:
        exe = _find_llama_server_executable(install_root)
    if not exe:
        raise HTTPException(500, "Installed package does not contain llama-server.exe")

    models_dir = (Config.LLAMACPP_MODELS_DIR or "").strip()
    if not models_dir:
        default_models_dir = _llamacpp_install_root() / "models"
        default_models_dir.mkdir(parents=True, exist_ok=True)
        models_dir = str(default_models_dir)

    model_path = (Config.LLAMACPP_MODEL_PATH or "").strip()
    model_alias = (Config.LLAMACPP_MODEL_ALIAS or "").strip()
    if not model_path or not Path(model_path).exists():
        discovered = _find_first_gguf(Path(models_dir))
        if discovered:
            model_path = str(discovered)
            model_alias = _slug_alias(discovered.stem)
    if not model_alias:
        model_alias = "local-model"

    payload = {
        "LLM_PROVIDER": "llamacpp",
        "LLAMACPP_EXECUTABLE": str(exe),
        "LLAMACPP_MODELS_DIR": models_dir,
        "LLAMACPP_MODEL_ALIAS": model_alias,
    }
    if model_path:
        payload["LLAMACPP_MODEL_PATH"] = model_path
    _upsert_env_settings(payload)

    _write_llamacpp_install_meta({
        "version": tag,
        "asset_name": asset_name,
        "asset_url": asset_url,
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "executable": str(exe),
    })

    return {
        "status": "ok",
        "installed_version": tag,
        "executable": str(exe),
        "models_dir": models_dir,
        "model_path": model_path,
        "model_alias": model_alias,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GGUF model discovery
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/models/gguf")
async def list_gguf_models():
    """Scan filesystem for .gguf files and return metadata."""
    _reload_config_runtime()  # pick up latest .env in case user just saved settings
    return _scan_gguf_models()


@app.get("/local/behaviors")
async def list_local_behaviors():
    """Return machine-local behavior profiles from DATA_DIR/local_behaviors.json."""
    _reload_config_runtime()
    return _load_local_behaviors()


# ─────────────────────────────────────────────────────────────────────────────
# Model Hub
# ─────────────────────────────────────────────────────────────────────────────

try:
    import hub_catalog as _hub_catalog  # type: ignore
    _HUB_OK = True
except ImportError:
    _hub_catalog = None  # type: ignore
    _HUB_OK = False

_hub_downloads: dict[str, dict] = {}   # download_id → progress dict

_HF_QUANT_RE = re.compile(r"(IQ\d+_[A-Z_]+|Q\d+_[A-Z_]+|Q\d+|FP16|BF16|F16)", re.IGNORECASE)


def _hf_guess_quant(filename: str) -> str:
    m = _HF_QUANT_RE.search(filename or "")
    return m.group(1).upper() if m else "unknown"


def _hf_parse_repo_and_filename(q: str) -> tuple[str, str]:
    raw = (q or "").strip()
    if not raw:
        return "", ""

    # URL mode
    if "huggingface.co/" in raw:
        try:
            parsed = urlparse(raw)
            parts = [p for p in (parsed.path or "").split("/") if p]
            if len(parts) >= 2:
                repo = f"{parts[0]}/{parts[1]}"
                filename = ""
                # .../resolve/main/<filename> or .../blob/main/<filename>
                if len(parts) >= 5 and parts[2] in ("resolve", "blob") and parts[3] == "main":
                    filename = "/".join(parts[4:])
                return repo, filename
        except Exception:
            return "", ""

    # Direct repo shorthand: org/repo
    if "/" in raw and " " not in raw and not raw.startswith("http"):
        p = [x for x in raw.split("/") if x]
        if len(p) >= 2:
            return f"{p[0]}/{p[1]}", ""

    return "", ""


def _hf_http_json(url: str, timeout: int = 20) -> Any:
    req = Request(
        url,
        headers={
            "User-Agent": "UNLZ-Agent/2.0",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8", errors="ignore")
    return json.loads(payload or "{}")


def _hf_score_filename(name: str) -> int:
    up = (name or "").upper()
    # Prefer practical quants first, avoid full-precision as default candidate
    if "Q4_K_M" in up:
        return 100
    if "Q5_K_M" in up:
        return 95
    if "Q6_K" in up:
        return 90
    if "Q8_0" in up:
        return 82
    if "Q3_K" in up:
        return 80
    if "IQ4" in up:
        return 78
    if "IQ3" in up:
        return 70
    if "Q2" in up or "IQ2" in up:
        return 55
    if "F16" in up or "BF16" in up or "FP16" in up:
        return 15
    return 40


def _hf_fetch_repo_ggufs(repo: str) -> dict[str, Any]:
    safe_repo = quote(repo, safe="/")
    meta = _hf_http_json(f"https://huggingface.co/api/models/{safe_repo}", timeout=20)
    siblings = meta.get("siblings") or []
    files: list[dict[str, Any]] = []
    for sib in siblings:
        rfilename = (sib or {}).get("rfilename") or ""
        if not rfilename.lower().endswith(".gguf"):
            continue
        size_raw = (sib or {}).get("size")
        size_gb = None
        try:
            if size_raw is not None:
                size_gb = round(float(size_raw) / (1024 ** 3), 2)
        except Exception:
            size_gb = None
        files.append({
            "filename": rfilename,
            "size_gb": size_gb,
            "quant": _hf_guess_quant(rfilename),
        })

    files.sort(key=lambda x: (_hf_score_filename(x.get("filename", "")), x.get("size_gb") or 9999), reverse=True)
    updated = meta.get("lastModified") or meta.get("createdAt") or ""
    return {
        "repo": repo,
        "title": meta.get("id") or repo,
        "downloads": int(meta.get("downloads") or 0),
        "likes": int(meta.get("likes") or 0),
        "updated_at": str(updated),
        "gguf_count": len(files),
        "recommended_filename": (files[0]["filename"] if files else None),
        "files": files[:24],
    }


@app.get("/hub/search")
async def hub_search(q: str = "", limit: int = 8):
    """
    Search Hugging Face models by URL/name and return GGUF alternatives.
    - If query is a HF URL or org/repo, resolves directly.
    - Otherwise uses HF search API and enriches top repos with GGUF file lists.
    """
    q = (q or "").strip()
    if not q:
        raise HTTPException(400, "query is required")
    limit = max(1, min(int(limit or 8), 20))

    repo_hint, file_hint = _hf_parse_repo_and_filename(q)
    repos: list[str] = []
    results: list[dict[str, Any]] = []

    try:
        if repo_hint:
            repos = [repo_hint]
        else:
            sq = quote(q)
            raw = _hf_http_json(
                f"https://huggingface.co/api/models?search={sq}&limit={max(limit * 3, 15)}&sort=downloads&direction=-1",
                timeout=20,
            )
            seen: set[str] = set()
            for item in (raw or []):
                repo = (item or {}).get("id") or (item or {}).get("modelId") or ""
                if not repo or repo in seen:
                    continue
                seen.add(repo)
                repos.append(repo)
                if len(repos) >= limit:
                    break

        for repo in repos:
            try:
                info = _hf_fetch_repo_ggufs(repo)
            except Exception:
                continue
            if info["gguf_count"] <= 0:
                continue
            if repo == repo_hint and file_hint:
                match = next((f for f in info["files"] if f["filename"].lower() == file_hint.lower()), None)
                if match:
                    info["recommended_filename"] = match["filename"]
            results.append(info)
            if len(results) >= limit:
                break
    except Exception as exc:
        raise HTTPException(502, f"HF search failed: {exc}")

    return {"query": q, "results": results}


@app.get("/hub/catalog")
async def hub_get_catalog():
    """Curated model catalog + online-enriched recommendations."""
    if not _HUB_OK:
        raise HTTPException(503, "hub_catalog.py not found next to agent_server.py")

    vram_gb = 0.0
    ram_gb = 0.0
    try:
        vs = _collect_vram_stats()
        vram_gb = float(vs.get("vram_total_gb") or 0)
        import psutil as _psutil
        ram_gb = _psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        pass

    tier = _hub_catalog.classify_hardware(vram_gb, ram_gb)
    runtime_catalog, online_meta = _hub_catalog.get_runtime_catalog()
    recs = _hub_catalog.get_recommendations(vram_gb, ram_gb, runtime_catalog)

    return {
        "hardware": {
            "vram_gb": round(vram_gb, 1),
            "ram_gb": round(ram_gb, 1),
            "tier": tier,
        },
        "catalog": runtime_catalog,
        "recommendations": recs,
        "online": online_meta,
    }


@app.get("/hub/check-update")
async def hub_check_update():
    """Check if current model has an available upgrade."""
    if not _HUB_OK:
        return {"update": None}

    current_path = Config.LLAMACPP_MODEL_PATH or ""
    current_alias = Config.LLAMACPP_MODEL_ALIAS or ""
    # Also try live status for alias
    try:
        base = f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}"
        if _http_reachable(f"{base}/health", timeout=0.5):
            current_alias = Config.LLAMACPP_MODEL_ALIAS or current_alias
    except Exception:
        pass

    runtime_catalog, _online_meta = _hub_catalog.get_runtime_catalog()
    update = _hub_catalog.check_for_update(current_path, current_alias, runtime_catalog)
    return {"update": update, "current_model": current_path}


@app.post("/hub/download")
async def hub_start_download(body: dict):
    """Start a background HuggingFace download. Returns {download_id}."""
    if not _HUB_OK:
        raise HTTPException(503, "hub_catalog not available")

    hf_repo: str = body.get("hf_repo", "").strip()
    filename: str = body.get("filename", "").strip()
    dest_dir: str = (body.get("dest_dir") or Config.LLAMACPP_MODELS_DIR or "").strip()

    if not hf_repo or not filename:
        raise HTTPException(400, "hf_repo and filename are required")
    if not dest_dir:
        raise HTTPException(400, "dest_dir required — set LLAMACPP_MODELS_DIR in Settings")

    os.makedirs(dest_dir, exist_ok=True)
    download_id = str(uuid.uuid4())[:8]
    url = f"https://huggingface.co/{hf_repo}/resolve/main/{filename}"
    dest_path = os.path.join(dest_dir, filename)

    _hub_downloads[download_id] = {
        "id": download_id,
        "url": url,
        "hf_repo": hf_repo,
        "filename": filename,
        "dest_path": dest_path,
        "status": "starting",
        "progress": 0.0,
        "downloaded_gb": 0.0,
        "total_gb": 0.0,
        "speed_mbps": 0.0,
        "eta_s": 0,
        "error": None,
        "cancelled": False,
    }

    asyncio.create_task(_run_hub_download(download_id, url, dest_path))
    return {"download_id": download_id}


async def _run_hub_download(download_id: str, url: str, dest_path: str) -> None:
    info = _hub_downloads[download_id]
    part_path = dest_path + ".part"
    try:
        req = Request(url, headers={"User-Agent": "UNLZ-Agent/2.0"})
        loop = asyncio.get_event_loop()

        def _do_download() -> None:
            with urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0) or 0)
                info["total_gb"] = total / (1024 ** 3)
                info["status"] = "downloading"

                downloaded = 0
                chunk = 1 << 20   # 1 MB
                t_last = time.monotonic()
                bytes_window = 0

                with open(part_path, "wb") as fh:
                    while True:
                        if info["cancelled"]:
                            info["status"] = "cancelled"
                            return
                        data = resp.read(chunk)
                        if not data:
                            break
                        fh.write(data)
                        downloaded += len(data)
                        bytes_window += len(data)
                        now = time.monotonic()
                        dt = now - t_last
                        if dt >= 0.5:
                            info["speed_mbps"] = (bytes_window / dt) / (1024 * 1024)
                            bytes_window = 0
                            t_last = now
                        if total:
                            info["progress"] = downloaded / total
                            remaining = total - downloaded
                            bps = max(info["speed_mbps"] * 1024 * 1024, 1)
                            info["eta_s"] = int(remaining / bps)
                        info["downloaded_gb"] = downloaded / (1024 ** 3)

        await loop.run_in_executor(None, _do_download)

        if not info["cancelled"]:
            if os.path.exists(dest_path):
                os.replace(part_path, dest_path)
            else:
                os.rename(part_path, dest_path)
            info["status"] = "done"
            info["progress"] = 1.0

    except Exception as exc:
        info["status"] = "error"
        info["error"] = str(exc)
        try:
            if os.path.exists(part_path):
                os.remove(part_path)
        except Exception:
            pass


@app.get("/hub/download/{download_id}")
async def hub_download_progress(download_id: str):
    """SSE stream of download progress."""
    if download_id not in _hub_downloads:
        raise HTTPException(404, "Download not found")

    async def _gen():
        while True:
            info = _hub_downloads.get(download_id)
            if info is None:
                break
            payload = {
                "status": info["status"],
                "progress": round(info["progress"], 4),
                "downloaded_gb": round(info["downloaded_gb"], 3),
                "total_gb": round(info["total_gb"], 3),
                "speed_mbps": round(info["speed_mbps"], 2),
                "eta_s": info["eta_s"],
                "error": info["error"],
                "filename": info["filename"],
                "dest_path": info["dest_path"],
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if info["status"] in ("done", "error", "cancelled"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/hub/download/{download_id}")
async def hub_cancel_download(download_id: str):
    """Cancel an active download."""
    if download_id not in _hub_downloads:
        raise HTTPException(404, "Download not found")
    _hub_downloads[download_id]["cancelled"] = True
    return {"status": "cancelling"}


@app.post("/hub/apply/{download_id}")
async def hub_apply_model(download_id: str):
    """Apply a completed download: write .env + restart llama.cpp."""
    if download_id not in _hub_downloads:
        raise HTTPException(404, "Download not found")

    info = _hub_downloads[download_id]
    if info["status"] != "done":
        raise HTTPException(400, f"Download not complete (status={info['status']})")

    dest_path = info["dest_path"]
    if not os.path.exists(dest_path):
        raise HTTPException(400, f"File not found: {dest_path}")

    # Derive alias from filename
    stem = Path(dest_path).stem
    new_alias = _slug_alias(stem)

    # Persist to .env
    _upsert_env_settings({
        "LLAMACPP_MODEL_PATH": dest_path,
        "LLAMACPP_MODEL_ALIAS": new_alias,
    })

    # Restart llama.cpp with new model
    try:
        await llamacpp_stop()
        await asyncio.sleep(1.5)
        await llamacpp_start()
        warning = None
    except Exception as exc:
        warning = str(exc)

    return {"status": "applied", "model_path": dest_path, "alias": new_alias, "warning": warning}


@app.get("/hub/downloads")
async def hub_list_downloads():
    """List all known downloads (active + history)."""
    return list(_hub_downloads.values())


# ─────────────────────────────────────────────────────────────────────────────
# Dev / debug endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _log_path() -> Path:
    """Path to agent_server.log next to agent_server.py."""
    return _runtime_root_dir() / "agent_server.log"


@app.get("/dev/log")
async def dev_get_log(lines: int = 300):
    """Return last N lines of agent_server.log."""
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
    """SSE tail of agent_server.log — polls every second for new lines."""
    p = _log_path()

    async def _gen():
        last_size = 0
        # Send initial tail
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
                    if size < last_size:  # truncated
                        last_size = 0
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
                all_lines = text.splitlines()
                # Approximate: emit new lines since last read
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


@app.get("/dev/traces")
async def dev_list_traces(limit: int = 30):
    """Return metadata for the most recent run traces."""
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
    """Return full trace for a run."""
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
    """Delete all run traces."""
    runs_dir = _runs_dir()
    count = 0
    for f in runs_dir.glob("*.json"):
        try:
            f.unlink()
            count += 1
        except Exception:
            pass
    return {"deleted": count}


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge base
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/files")
async def list_files():
    data_dir = Path(Config.DATA_DIR)
    if not data_dir.exists():
        return []
    return [
        {
            "name": f.name,
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        }
        for f in sorted(data_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        if _is_visible_knowledge_file(f)
    ]


@app.get("/folders/{folder_id}/files")
async def list_folder_files(folder_id: str):
    fid = _safe_folder_id(folder_id)
    if not fid:
        return []
    folder = _folder_docs_dir(fid)
    if not folder.exists():
        return []
    return [
        {
            "name": f.name,
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        }
        for f in sorted(folder.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)
        if f.is_file()
    ]


@app.post("/folders/{folder_id}/upload")
async def upload_folder_file(folder_id: str, file: UploadFile):
    fid = _safe_folder_id(folder_id)
    if not fid:
        raise HTTPException(400, "Invalid folder_id")
    folder = _folder_docs_dir(fid)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / (file.filename or "upload")
    content = await file.read()
    dest.write_bytes(content)
    return {"success": True, "filename": dest.name, "size": len(content)}


@app.post("/upload")
async def upload_file(file: UploadFile):
    data_dir = Path(Config.DATA_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / (file.filename or "upload")
    content = await file.read()
    dest.write_bytes(content)
    return {"success": True, "filename": dest.name, "size": len(content)}


@app.post("/ingest")
async def ingest():
    try:
        from rag_pipeline.ingest import ingest_documents
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, ingest_documents)
        return {"success": True, "message": "Ingestion complete"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/stats")
async def stats():
    import psutil
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.2)
    vram = _collect_vram_stats()
    disks = []
    seen = set()

    for part in psutil.disk_partitions(all=False):
        mountpoint = part.mountpoint
        if not mountpoint:
            continue
        key = mountpoint.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            usage = psutil.disk_usage(mountpoint)
        except Exception:
            continue

        # Windows usually exposes drive letters like C:\, D:\ ...
        name = mountpoint
        if os.name == "nt" and len(mountpoint) >= 2 and mountpoint[1] == ":":
            name = mountpoint[:2].upper()

        disks.append({
            "name": name,
            "mountpoint": mountpoint,
            "total_gb": round(usage.total / 1024 ** 3, 2),
            "used_gb": round(usage.used / 1024 ** 3, 2),
            "percent": usage.percent,
        })

    # Fallback for environments where partition listing returns nothing
    if not disks:
        fallback = psutil.disk_usage("/")
        disks.append({
            "name": "/",
            "mountpoint": "/",
            "total_gb": round(fallback.total / 1024 ** 3, 2),
            "used_gb": round(fallback.used / 1024 ** 3, 2),
            "percent": fallback.percent,
        })

    total_disk_gb = round(sum(d["total_gb"] for d in disks), 2)
    used_disk_gb = round(sum(d["used_gb"] for d in disks), 2)
    total_percent = round((used_disk_gb / total_disk_gb) * 100, 1) if total_disk_gb else 0.0

    return {
        "cpu_percent": cpu,
        "ram_total_gb": round(mem.total / 1024 ** 3, 2),
        "ram_used_gb": round(mem.used / 1024 ** 3, 2),
        "ram_percent": mem.percent,
        "vram_total_gb": vram["vram_total_gb"],
        "vram_used_gb": vram["vram_used_gb"],
        "vram_percent": vram["vram_percent"],
        "gpus": vram["gpus"],
        "disk_total_gb": total_disk_gb,  # backward-compatible aggregate
        "disk_used_gb": used_disk_gb,    # backward-compatible aggregate
        "disk_percent": total_percent,   # backward-compatible aggregate
        "disks": disks,
    }


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("AGENT_SERVER_PORT", "7719"))
    try:
        _ensure_llamacpp_default_dirs()
    except Exception as e:
        print(f"[unlz] llama.cpp dir init warning: {e}")
    print(f"UNLZ Agent Server v2 — port {port}")
    print(f"Provider : {Config.LLM_PROVIDER}")
    print(f"Language : {Config.AGENT_LANGUAGE}")
    print(f"Harness  : {getattr(Config, 'AGENT_HARNESS', 'native')}")
    print(f"llama.cpp dir : {_llamacpp_install_root()}")
    if Config.LLM_PROVIDER == "llamacpp":
        print(f"Model    : {Config.LLAMACPP_MODEL_ALIAS} @ {Config.LLAMACPP_MODEL_PATH}")
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
