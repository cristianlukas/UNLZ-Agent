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
import uuid
import zipfile
from datetime import datetime
from urllib.parse import urlparse
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
from typing import Any, AsyncGenerator, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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


def _opencode_bin() -> str:
    configured = (os.getenv("HARNESS_OPENCODE_BIN") or getattr(Config, "HARNESS_OPENCODE_BIN", "") or "").strip()
    if configured and Path(configured).exists():
        return configured
    detected = shutil.which("opencode")
    return detected or ""


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


def _is_smalltalk_request(text: str) -> bool:
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not t:
        return False
    smalltalk_tokens = (
        "hola",
        "buenas",
        "buen día",
        "buen dia",
        "buenas tardes",
        "buenas noches",
        "qué tal",
        "que tal",
        "como estas",
        "cómo estás",
        "como va",
        "cómo va",
        "hello",
        "hi",
        "hey",
        "how are you",
        "good morning",
        "good afternoon",
        "good evening",
    )
    return any(tok in t for tok in smalltalk_tokens)


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
    if mode == "iterate":
        return "resumen_asignacion", 0.6, "mode=iterate"

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


def _build_model_chain(base_model: str, route: dict) -> list[str]:
    chain: list[str] = []
    for m in [route.get("primary_model"), *(route.get("fallback_models") or []), base_model]:
        mm = str(m or "").strip()
        if mm and mm not in chain:
            chain.append(mm)
    return chain or [base_model]


def _route_with_model_override(route: dict, model_override: str) -> dict:
    preferred = str(model_override or "").strip()
    if not preferred:
        return route
    fallback = [str(x) for x in (route.get("fallback_models") or []) if str(x).strip()]
    prev_primary = str(route.get("primary_model") or "").strip()
    if prev_primary and prev_primary != preferred:
        fallback = [prev_primary, *fallback]
    dedup: list[str] = []
    for m in fallback:
        if m and m != preferred and m not in dedup:
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


async def _chat_create_with_fallback(client, model_chain: list[str], **kwargs):
    errors = []
    retries = 0
    for idx, m in enumerate(model_chain):
        try:
            resp = await client.chat.completions.create(model=m, **kwargs)
            return resp, m, retries, errors
        except Exception as e:
            errors.append(f"{m}: {e}")
            retries += 1
            if idx >= len(model_chain) - 1:
                break
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
    folder_id: str = ""             # optional folder scope for folder-only docs
    sandbox_root: str = ""          # optional folder sandbox path (enforced for command/file ops)
    mode: str = "normal"            # normal | plan | iterate | simple
    conversation_id: str = ""
    dry_run: bool = False


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
    r"\bformat\b",
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
    default = "confirm" if mutating else "allow"
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

    # If no sandbox configured, force explicit user decision first.
    if not sandbox_root and not approved:
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
        "You are an intelligent assistant for Universidad Nacional de Lomas de Zamora (UNLZ). "
        "You have access to tools: local knowledge search (RAG), web search, time, system stats, and Windows terminal command execution. "
        "Do not claim you lack internet access. If the user asks to research/search online, you must call web_search. "
        "When the user asks you to perform an action on their machine, use run_windows_command instead of just explaining how. "
        "If run_windows_command returns needs_confirmation, ask the user to approve/reject using confirmation cards in chat. "
        "Use tools proactively to answer accurately. "
        "Format responses in Markdown. Be concise and precise."
    ),
    "es": (
        "Eres un asistente inteligente de la Universidad Nacional de Lomas de Zamora (UNLZ). "
        "Tenés acceso a herramientas: búsqueda de conocimiento local (RAG), búsqueda web, hora, stats del sistema y ejecución de comandos en terminal de Windows. "
        "No digas que no tenés acceso a internet: si el usuario pide investigar o buscar online, tenés que usar web_search. "
        "Cuando el usuario te pida realizar una acción en su máquina, usá run_windows_command en lugar de solo explicar pasos. "
        "Si run_windows_command devuelve needs_confirmation, pedí al usuario aprobar o rechazar desde las tarjetas de confirmación del chat. "
        "Usá las herramientas proactivamente para responder con precisión. "
        "Formateá las respuestas en Markdown. Sé conciso y preciso."
    ),
    "zh": (
        "您是洛马斯·德萨莫拉国立大学的智能助手。"
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

    client, model = _get_client()
    if simple_chat:
        # Fast path: skip task router and model fallback chain.
        task_area = "chat_general"
        route_conf = 1.0
        route_reason = "simple_mode"
        route = {
            "primary_model": model,
            "fallback_models": [],
            "profile": "simple",
        }
        model_chain = [model]
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

    prompt_text = _compose_system_prompt(system_prompt, harness_override)
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
            stream, model_used, retries, _errors = await _chat_create_with_fallback(
                client,
                model_chain,
                messages=messages,
                stream=True,
                timeout=120,
            )
            llm_retries_total += retries
            if retries > 0:
                yield f"data: {json.dumps({'type': 'step', 'text': 'task_router.llm_fallback', 'args': {'used_model': model_used, 'retries': retries}})}\n\n"
            async for chunk in stream:
                chunk_choices = getattr(chunk, "choices", None)
                if not chunk_choices:
                    continue
                delta = getattr(chunk_choices[0], "delta", None)
                delta_content = getattr(delta, "content", None) if delta else None
                if delta_content:
                    final_chunks.append(delta_content)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': delta_content})}\n\n"
                    await asyncio.sleep(0)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': f'Simple chat error: {e}'})}\n\n"
            _record_router_metric(task_area, model_used, False, int((time.time() - started_at) * 1000), llm_retries_total, "simple", str(e))
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

    # Fast-path for greetings/chit-chat: avoid unnecessary tool-calling latency.
    if _is_smalltalk_request(message):
        available_tools = []
        force_tools = False
    else:
        available_tools = _tools_for_message(message)
    if _safe_folder_id(folder_id):
        available_tools = [
            t for t in available_tools
            if t.get("function", {}).get("name") != "search_local_knowledge"
        ]

    loop = asyncio.get_event_loop()
    invalid_shape_count = 0
    emitted_final = False

    for iteration in range(limits["max_iterations"]):
        if (time.time() - started_at) >= limits["max_wall_sec"]:
            yield f"data: {json.dumps({'type': 'error', 'text': 'Agent wall-time limit reached before completion.'})}\n\n"
            break

        try:
            resp, model_used, retries, _errors = await _chat_create_with_fallback(
                client,
                model_chain,
                messages=messages,
                tools=available_tools,
                tool_choice="required" if (force_tools and iteration == 0) else "auto",
                stream=False,
                timeout=90,
            )
            llm_retries_total += retries
            if retries > 0:
                yield f"data: {json.dumps({'type': 'step', 'text': 'task_router.llm_fallback', 'args': {'used_model': model_used, 'retries': retries}})}\n\n"
        except Exception as e2:
            yield f"data: {json.dumps({'type': 'error', 'text': f'LLM error: {e2}'})}\n\n"
            _record_router_metric(task_area, model_used, False, int((time.time() - started_at) * 1000), llm_retries_total, "normal", str(e2))
            return

        choices = getattr(resp, "choices", None)
        if choices is None:
            invalid_shape_count += 1
            if invalid_shape_count <= 2:
                await asyncio.sleep(0.8)
                continue
            preview = str(resp)
            if len(preview) > 240:
                preview = preview[:240] + "..."
            yield f"data: {json.dumps({'type': 'error', 'text': f'LLM invalid response shape: {type(resp).__name__} {preview}'})}\n\n"
            return
        if not choices:
            yield f"data: {json.dumps({'type': 'error', 'text': 'LLM returned empty choices'})}\n\n"
            return

        choice = choices[0]
        msg = getattr(choice, "message", None)
        finish_reason = getattr(choice, "finish_reason", None)
        msg_tool_calls = getattr(msg, "tool_calls", None) if msg else None

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
                    txt = "No pude ejecutar la accion automaticamente. Reintenta o reformula con mas detalle."
                    final_chunks.append(txt)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': txt})}\n\n"
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
) -> dict:
    text_chunks: list[str] = []
    steps: list[dict] = []
    error_text = ""
    confidence = None
    async for raw in _agent_stream_normal(message, history, system_prompt, model_override, harness_override, folder_id, sandbox_root, conversation_id, dry_run):
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


async def _plan_stream(
    message: str,
    history: list[dict],
    system_prompt: str = "",
    model_override: str = "",
    harness_override: str = "",
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
    yield f"data: {json.dumps({'type': 'step', 'text': 'task_router', 'args': {'area': task_area, 'confidence': route_conf, 'reason': route_reason, 'primary_model': route.get('primary_model'), 'fallback_models': route.get('fallback_models'), 'profile': route.get('profile')}})}\n\n"
    plan_protocol = (
        "Modo plan activo. Tu tarea es planificar antes de ejecutar.\n"
        "Reglas:\n"
        "1) Presentá el plan por etapas numeradas.\n"
        "2) En cada etapa, ofrecé 2-4 alternativas con trade-offs.\n"
        "3) Pedí la decisión del usuario antes de pasar a la siguiente etapa.\n"
        "4) Cuando tengas decisiones suficientes, emití 'PLAN FINAL' con todas las decisiones tomadas.\n"
        "5) Terminá con una pregunta explícita con estas opciones:\n"
        "   - Ejecutar el plan (modo agente iterador)\n"
        "   - Editar el plan\n"
        "   - Descartar\n"
        "No ejecutes herramientas en modo plan, solo planificación."
    )
    final_system = f"{_compose_system_prompt(system_prompt, harness_override)}\n\n{plan_protocol}"
    messages: list[dict] = [{"role": "system", "content": final_system}]
    for h in history[-14:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    try:
        stream, model_used, retries, _errors = await _chat_create_with_fallback(
            client,
            model_chain,
            messages=messages,
            stream=True,
            timeout=120,
        )
        llm_retries_total += retries
        async for chunk in stream:
            ch = getattr(chunk, "choices", None)
            if not ch:
                continue
            delta = getattr(ch[0], "delta", None)
            txt = getattr(delta, "content", None) if delta else None
            if txt:
                yield f"data: {json.dumps({'type': 'chunk', 'text': txt})}\n\n"
                await asyncio.sleep(0)
    except Exception as e:
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
    max_retries = 3
    done: dict[str, dict] = {}
    pending = list(stages)

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
            result = await _run_internal_agent_once(stage_prompt, exec_history, system_prompt, model_override, harness_override, folder_id, sandbox_root, conversation_id, dry_run)
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
                    model_chain,
                    messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": validate_prompt}],
                    stream=False,
                    timeout=40,
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

        parallel_batch = [s for s in ready if s.get("parallelizable")]
        serial_batch = [s for s in ready if not s.get("parallelizable")]
        batch = parallel_batch if parallel_batch else serial_batch[:1]

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
    folder_id: str = "",
    sandbox_root: str = "",
    mode: str = "normal",
    conversation_id: str = "",
    dry_run: bool = False,
) -> AsyncGenerator[str, None]:
    run_id = uuid.uuid4().hex[:12]
    trace: dict[str, Any] = {
        "run_id": run_id,
        "conversation_id": conversation_id,
        "folder_id": _safe_folder_id(folder_id),
        "sandbox_root": sandbox_root,
        "mode": (mode or "normal").strip().lower(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "input": {"message": message, "history_size": len(history)},
        "events": [],
    }

    async def _stream_and_trace(inner: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
        try:
            async for ev in inner:
                if ev.startswith("data: "):
                    payload = ev[6:].strip()
                    if payload:
                        try:
                            trace["events"].append(json.loads(payload))
                        except Exception:
                            trace["events"].append({"type": "raw", "payload": payload[:800]})
                yield ev
        finally:
            trace["finished_at"] = datetime.now().isoformat(timespec="seconds")
            _persist_trace(run_id, trace)
            _emit_telemetry("run_completed", {
                "run_id": run_id,
                "conversation_id": conversation_id,
                "mode": trace.get("mode"),
                "event_count": len(trace.get("events") or []),
            })

    yield f"data: {json.dumps({'type': 'run', 'run_id': run_id})}\n\n"

    m = (mode or "normal").strip().lower()
    if m == "plan":
        async for ev in _stream_and_trace(_plan_stream(message, history, system_prompt, model_override, harness_override)):
            yield ev
        return
    if m == "iterate":
        async for ev in _stream_and_trace(_iterate_stream(message, history, system_prompt, model_override, harness_override, folder_id, sandbox_root, conversation_id, dry_run)):
            yield ev
        return
    if m == "simple":
        async for ev in _stream_and_trace(_agent_stream_normal(message, history, system_prompt, model_override, harness_override, folder_id, sandbox_root, conversation_id, dry_run, simple_chat=True)):
            yield ev
        return
    async for ev in _stream_and_trace(_agent_stream_normal(message, history, system_prompt, model_override, harness_override, folder_id, sandbox_root, conversation_id, dry_run)):
        yield ev


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(application: FastAPI):
    # ── Auto-start llama.cpp if configured ───────────────────────────────────
    if Config.LLM_PROVIDER == "llamacpp":
        if Config.LLAMACPP_EXECUTABLE and os.path.isfile(Config.LLAMACPP_EXECUTABLE):
            if Config.LLAMACPP_MODEL_PATH and os.path.isfile(Config.LLAMACPP_MODEL_PATH):
                global _llamacpp_proc
                already_up = False
                already_up = _http_reachable(
                    f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}/health",
                    timeout=1.0,
                )

                if not already_up:
                    print(f"[unlz] Auto-starting llama.cpp — {Config.LLAMACPP_MODEL_ALIAS}")
                    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                    try:
                        _llamacpp_proc = subprocess.Popen(
                            _build_llamacpp_args(),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=flags,
                        )
                        print(f"[unlz] llama.cpp PID {_llamacpp_proc.pid}")
                    except Exception as e:
                        print(f"[unlz] llama.cpp auto-start failed: {e}")
            else:
                print("[unlz] llama.cpp model not found — skipping auto-start")
        else:
            print("[unlz] llama.cpp executable not found — skipping auto-start")

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
            req.folder_id,
            req.sandbox_root,
            req.mode,
            req.conversation_id,
            req.dry_run,
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
        ok = _http_reachable(f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}/health", timeout=1.5)
        components["llm"] = {
            "status": "ok" if ok else "error",
            "details": f"llama.cpp — {Config.LLAMACPP_MODEL_ALIAS}" if ok
                       else f"llama.cpp unreachable (port {Config.LLAMACPP_PORT})",
        }
    elif provider == "ollama":
        ok = _http_reachable(f"{Config.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=1.5)
        components["llm"] = {
            "status": "ok" if ok else "error",
            "details": f"Ollama — {Config.OLLAMA_MODEL}" if ok else "Ollama unreachable",
        }
    else:
        has_key = bool(Config.OPENAI_API_KEY)
        components["llm"] = {
            "status": "ok" if has_key else "warning",
            "details": "OpenAI configured" if has_key else "OpenAI key missing",
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

        # 1) Try official install command via PowerShell (best-effort on Windows)
        if os.name == "nt":
            try:
                ps_cmd = "irm https://opencode.ai/install | iex"
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                    capture_output=True,
                    text=True,
                    timeout=420,
                )
                if proc.returncode != 0:
                    install_errors.append(f"install script: {(proc.stderr or proc.stdout or '').strip()[:400]}")
            except Exception as e:
                install_errors.append(f"install script exception: {e}")

        op_bin = _opencode_bin()

        # 2) npm fallback(s)
        if not op_bin and shutil.which("npm"):
            for pkg in ("opencode-ai", "@opencode-ai/cli", "@opencode/cli"):
                try:
                    proc = subprocess.run(
                        ["npm", "install", "-g", pkg],
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


def _build_llamacpp_args() -> list[str]:
    args = [
        Config.LLAMACPP_EXECUTABLE,
        "-m", Config.LLAMACPP_MODEL_PATH,
        "--alias", Config.LLAMACPP_MODEL_ALIAS,
        "--host", Config.LLAMACPP_HOST,
        "--port", str(Config.LLAMACPP_PORT),
        "-c", str(Config.LLAMACPP_CONTEXT_SIZE),
        "-ngl", str(Config.LLAMACPP_N_GPU_LAYERS),
    ]
    if Config.LLAMACPP_FLASH_ATTN:
        # Newer llama.cpp builds require an explicit value.
        args += ["--flash-attn", "on"]
    if Config.LLAMACPP_CACHE_TYPE_K:
        args += ["--cache-type-k", Config.LLAMACPP_CACHE_TYPE_K]
    if Config.LLAMACPP_CACHE_TYPE_V:
        args += ["--cache-type-v", Config.LLAMACPP_CACHE_TYPE_V]
    if Config.LLAMACPP_EXTRA_ARGS:
        args += Config.LLAMACPP_EXTRA_ARGS.split()
    return args


@app.post("/llamacpp/start")
async def llamacpp_start():
    global _llamacpp_proc
    _reload_config_runtime()

    if not Config.LLAMACPP_EXECUTABLE:
        raise HTTPException(400, "LLAMACPP_EXECUTABLE not configured")
    if not os.path.isfile(Config.LLAMACPP_EXECUTABLE):
        raise HTTPException(400, f"Executable not found: {Config.LLAMACPP_EXECUTABLE}")
    if not os.path.isfile(Config.LLAMACPP_MODEL_PATH):
        raise HTTPException(400, f"Model not found: {Config.LLAMACPP_MODEL_PATH}")

    if _llamacpp_proc and _llamacpp_proc.poll() is None:
        return {"status": "already_running", "pid": _llamacpp_proc.pid}

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    _llamacpp_proc = subprocess.Popen(
        _build_llamacpp_args(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    return {
        "status": "started",
        "pid": _llamacpp_proc.pid,
        "url": f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}/v1",
    }


@app.post("/llamacpp/stop")
async def llamacpp_stop():
    global _llamacpp_proc
    _reload_config_runtime()
    killed_pids: list[int] = []
    managed_pid: Optional[int] = None

    # 1) Stop managed process (if any)
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
    else:
        _llamacpp_proc = None

    # 2) Also kill any process still listening on the configured llama.cpp port.
    # This covers orphan/external llama-server instances that still hold VRAM.
    port_pids = _pids_listening_on_tcp_port(Config.LLAMACPP_PORT)
    for pid in sorted(port_pids):
        if _kill_pid_tree(pid):
            killed_pids.append(pid)

    # 3) Wait a bit for socket/process teardown.
    running = False
    for _ in range(12):
        running = _http_reachable(f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}/health", timeout=0.5)
        if not running:
            break
        time.sleep(0.25)

    if not killed_pids and not running:
        return {"status": "not_running", "running": False, "killed_pids": []}
    if running:
        return {"status": "still_running", "running": True, "killed_pids": sorted(set(killed_pids))}
    return {"status": "stopped", "running": False, "killed_pids": sorted(set(killed_pids))}


@app.get("/llamacpp/status")
async def llamacpp_status():
    _reload_config_runtime()
    base = f"http://{Config.LLAMACPP_HOST}:{Config.LLAMACPP_PORT}"
    running = _http_reachable(f"{base}/health", timeout=1.0)
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

    search_roots: set[Path] = set()

    def add_if_exists(p: Path) -> None:
        try:
            if p.exists():
                search_roots.add(p.resolve())
        except (OSError, PermissionError):
            pass

    # 1. Explicit LLAMACPP_MODELS_DIR (highest priority)
    models_dir = Config.LLAMACPP_MODELS_DIR or os.getenv("LLAMACPP_MODELS_DIR", "")
    if models_dir:
        add_if_exists(Path(models_dir))

    # 2. Derive from current model path (go up to the models root)
    if Config.LLAMACPP_MODEL_PATH:
        p = Path(Config.LLAMACPP_MODEL_PATH)
        add_if_exists(p.parent.parent)  # <root>/<ModelFolder>/<file>.gguf
        add_if_exists(p.parent)

    # 3. Common Windows locations
    userprofile = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    for rel in ("Models\\llamacpp", "Models", "models\\llamacpp", "models"):
        if userprofile:
            add_if_exists(Path(userprofile) / rel)

    # 4. Python home fallback
    try:
        add_if_exists(Path.home() / "Models" / "llamacpp")
        add_if_exists(Path.home() / "Models")
    except Exception:
        pass

    models = []
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
                alias = stem.lower()
                for ch in ("_", ".", " "):
                    alias = alias.replace(ch, "-")
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


