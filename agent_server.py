"""
UNLZ Agent Server — replaces n8n.
FastAPI + OpenAI-compatible tool-calling loop + SSE streaming.
Supports llamacpp / ollama / openai as LLM providers.
"""
from __future__ import annotations

import asyncio
import http.client
import json
import os
import re
import sys
import tempfile
import zipfile
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# ── Redirect stdout/stderr to log when not running in a real terminal ─────────
# Covers: Tauri subprocess (CREATE_NO_WINDOW), background launch, etc.
# os.isatty(1) checks the actual fd, not the Python wrapper.
_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_server.log")
_FORCE_LOG_FILE = os.getenv("UNLZ_FORCE_LOG_FILE", "0").strip().lower() in ("1", "true", "yes")
try:
    _is_tty = os.isatty(sys.stdout.fileno())
except (AttributeError, OSError):
    _is_tty = False

if _FORCE_LOG_FILE or not _is_tty:
    _log_fh = open(_LOG_PATH, "a", encoding="utf-8", buffering=1)
    sys.stdout = _log_fh
    sys.stderr = _log_fh
import subprocess
from pathlib import Path
from typing import AsyncGenerator, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Project root on sys.path
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

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
    load_dotenv(override=True)
    Config.VECTOR_DB_PROVIDER = os.getenv("VECTOR_DB_PROVIDER", "chroma").lower()
    Config.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
    Config.AGENT_LANGUAGE = os.getenv("AGENT_LANGUAGE", "en").lower()
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
    return Path(__file__).parent / ".env"


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
    return Path(Config.BASE_DIR) / "tools" / "llama.cpp"


def _llamacpp_install_meta_path() -> Path:
    return _llamacpp_install_root() / "install.json"


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
        return "No web results found."

    n = max(1, min(int(max_results or 4), 8))
    engine = (os.getenv("WEB_SEARCH_ENGINE", Config.WEB_SEARCH_ENGINE) or "google").lower()
    errors: list[str] = []

    def search_google() -> list[dict]:
        # Optional dependency: googlesearch-python
        from googlesearch import search  # type: ignore
        items = []
        for idx, url in enumerate(search(q, num_results=n)):
            if idx >= n:
                break
            items.append({"title": "Google result", "body": "", "href": url})
        return items

    def search_duckduckgo() -> list[dict]:
        # Prefer the renamed package when available, keep backward compatibility.
        try:
            from ddgs import DDGS  # type: ignore
        except Exception:
            from duckduckgo_search import DDGS  # type: ignore
        return list(DDGS().text(q, max_results=n) or [])

    strategies = []
    if engine == "google":
        strategies = [("google", search_google), ("duckduckgo", search_duckduckgo)]
    elif engine == "duckduckgo":
        strategies = [("duckduckgo", search_duckduckgo), ("google", search_google)]
    else:
        strategies = [("google", search_google), ("duckduckgo", search_duckduckgo)]

    for name, fn in strategies:
        try:
            results = fn()
            if results:
                return "\n\n".join(
                    f"**{r.get('title', 'Result')}**\n{r.get('body', '')}\n{r.get('href', '')}"
                    for r in results[:n]
                )
        except Exception as e:
            errors.append(f"{name}: {e}")

    if errors:
        return f"WEB_SEARCH_UNAVAILABLE: No web results found. ({'; '.join(errors[:2])})"
    return "WEB_SEARCH_UNAVAILABLE: No web results found."

# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []        # [{role, content}, ...]
    system_prompt: str = ""         # override default system prompt (from Behavior)
    folder_id: str = ""             # optional folder scope for folder-only docs
    mode: str = "normal"            # normal | plan | iterate


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
                },
                "required": ["command"],
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


def _execution_mode() -> str:
    mode = os.getenv("AGENT_EXECUTION_MODE", Config.AGENT_EXECUTION_MODE).strip().lower()
    return mode if mode in ("confirm", "autonomous") else "confirm"


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

    mode = _execution_mode()
    if mode == "confirm":
        return json.dumps({
            "status": "needs_confirmation",
            "mode": mode,
            "command": command,
            "message": (
                "Execution mode is 'confirm'. Ask the user to switch to 'autonomous' in Settings "
                "if they want commands to run automatically."
            ),
        }, ensure_ascii=False)

    cwd = str(args.get("cwd") or "").strip()
    if cwd:
        run_cwd = os.path.abspath(os.path.expanduser(cwd))
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
        return json.dumps({
            "status": "executed",
            "mode": mode,
            "command": command,
            "cwd": run_cwd,
            "returncode": completed.returncode,
            "stdout": out,
            "stderr": err,
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({
            "status": "timeout",
            "command": command,
            "cwd": run_cwd,
            "timeout_sec": timeout_sec,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "command": command}, ensure_ascii=False)


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
        return (
            "Modo de ejecución actual: `Preguntar antes de ejecutar`.\n\n"
            "Para que lo ejecute automáticamente, cambiá en Configuración a `Agente autónomo` "
            "y repetí la instrucción."
        )
    if status == "timeout":
        return f"El comando superó el tiempo límite.\n\nComando: `{command}`"
    if status == "blocked":
        return "El comando fue bloqueado por política de seguridad."
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


def execute_tool(name: str, args: dict, folder_id: str = "") -> str:
    try:
        if name == "search_local_knowledge":
            from rag_pipeline.retriever import search_documents
            results = search_documents(args.get("query", ""))
            if not results:
                return "No relevant documents found in the knowledge base."
            return "\n\n".join(
                f"[Document {i + 1}]:\n{r.get('page_content') or r.get('content') or json.dumps(r)}"
                for i, r in enumerate(results[:4])
            )

        elif name == "web_search":
            return _web_search(args.get("query", ""), args.get("max_results", 4))

        elif name == "get_current_time":
            from datetime import datetime
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        elif name == "get_system_stats":
            import psutil
            mem = psutil.virtual_memory()
            vram = _collect_vram_stats()
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
                return "Knowledge base is empty."
            files = [f.name for f in data_dir.iterdir() if f.is_file()]
            return json.dumps(files) if files else "No files in knowledge base."

        elif name == "search_folder_documents":
            return _search_folder_documents(
                folder_id=folder_id,
                query=args.get("query", ""),
                max_results=args.get("max_results", 4),
            )

        elif name == "run_windows_command":
            return _run_windows_command(args)

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        return f"Tool error ({name}): {e}"


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
        "If run_windows_command returns needs_confirmation, ask the user to switch execution mode to autonomous. "
        "Use tools proactively to answer accurately. "
        "Format responses in Markdown. Be concise and precise."
    ),
    "es": (
        "Eres un asistente inteligente de la Universidad Nacional de Lomas de Zamora (UNLZ). "
        "Tenés acceso a herramientas: búsqueda de conocimiento local (RAG), búsqueda web, hora, stats del sistema y ejecución de comandos en terminal de Windows. "
        "No digas que no tenés acceso a internet: si el usuario pide investigar o buscar online, tenés que usar web_search. "
        "Cuando el usuario te pida realizar una acción en su máquina, usá run_windows_command en lugar de solo explicar pasos. "
        "Si run_windows_command devuelve needs_confirmation, pedile al usuario cambiar el modo de ejecución a autonomous. "
        "Usá las herramientas proactivamente para responder con precisión. "
        "Formateá las respuestas en Markdown. Sé conciso y preciso."
    ),
    "zh": (
        "您是洛马斯·德萨莫拉国立大学的智能助手。"
        "您可以使用工具：本地知识搜索(RAG)、网络搜索、时间查询、系统状态。"
        "主动使用工具以准确回答。用Markdown格式化回答。简洁精确。"
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Agent streaming generator
# ─────────────────────────────────────────────────────────────────────────────

def _compose_system_prompt(system_prompt: str = "") -> str:
    lang = Config.AGENT_LANGUAGE
    base_prompt = _PROMPTS.get(lang, _PROMPTS["en"])
    if system_prompt:
        return (
            f"{base_prompt}\n\n"
            "Behavior profile (additional instructions):\n"
            f"{system_prompt}"
        )
    return base_prompt


async def _agent_stream_normal(
    message: str,
    history: list[dict],
    system_prompt: str = "",
    folder_id: str = "",
) -> AsyncGenerator[str, None]:
    """
    Multi-step tool-calling agent. Yields SSE data lines.
    Event types: step | chunk | error | done
    """
    # Safety check
    from guardrails.validator import validate_input
    safety = validate_input(message)
    if not safety.get("valid", True):
        err = safety.get("error", "Query rejected by safety filter.")
        yield f"data: {json.dumps({'type': 'error', 'text': err})}\n\n"
        return

    client, model = _get_client()

    system_prompt = _compose_system_prompt(system_prompt)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for h in history[-12:]:   # keep last 12 turns to avoid blowing context
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    loop = asyncio.get_event_loop()
    last_tool_name: str | None = None
    last_tool_result: str | None = None
    force_tools = _is_research_request(message) or _is_action_request(message)
    available_tools = _tools_for_message(message)
    if _safe_folder_id(folder_id):
        # Folder-scoped conversations should use only folder documents for KB queries.
        available_tools = [
            t for t in available_tools
            if t.get("function", {}).get("name") != "search_local_knowledge"
        ]
    emitted_final = False
    invalid_shape_count = 0

    for iteration in range(6):  # max 6 tool-call rounds
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=available_tools,
                # Force at least one tool call for research-like prompts, then
                # allow the model to produce a final answer in later rounds.
                tool_choice="required" if (force_tools and iteration == 0) else "auto",
                stream=False,
                timeout=90,
            )
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': f'LLM error: {e}'})}\n\n"
            return

        try:
            choices = getattr(resp, "choices", None)
        except BaseException:
            choices = None

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

        try:
            choice = choices[0]
            msg = getattr(choice, "message", None)
            finish_reason = getattr(choice, "finish_reason", None)
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': f'LLM choices parsing error: {e}'})}\n\n"
            return

        # ── Tool calls ──────────────────────────────────────────────────────
        msg_tool_calls = getattr(msg, "tool_calls", None) if msg else None
        if finish_reason == "tool_calls" and msg_tool_calls:
            # Append assistant turn with tool_calls
            messages.append({
                "role": "assistant",
                "content": (getattr(msg, "content", "") or ""),
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg_tool_calls
                ],
            })

            for tc in msg_tool_calls:
                fn = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    fn_args = {}

                yield f"data: {json.dumps({'type': 'step', 'text': fn, 'args': fn_args})}\n\n"
                await asyncio.sleep(0)

                result = await loop.run_in_executor(None, execute_tool, fn, fn_args, folder_id)
                last_tool_name = fn
                last_tool_result = result

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

                if fn == "web_search" and isinstance(result, str) and result.startswith("WEB_SEARCH_UNAVAILABLE"):
                    text = (
                        "La búsqueda web falló en este momento y no pude obtener resultados reales.\n\n"
                        f"Detalle técnico: `{result}`\n\n"
                        "Probá de nuevo en unos segundos o cambiá `WEB_SEARCH_ENGINE` en Configuración."
                    )
                    yield f"data: {json.dumps({'type': 'chunk', 'text': text})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

            # Fast-path for terminal actions: return deterministic status message
            # instead of waiting for a second LLM pass that may return empty output.
            if last_tool_name == "run_windows_command" and last_tool_result:
                summary = _summarize_windows_command_result(last_tool_result)
                yield f"data: {json.dumps({'type': 'chunk', 'text': summary})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            continue  # next iteration with tool results in context

        # ── Final response: stream it ────────────────────────────────────────
        try:
            emitted_any = False
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                timeout=120,
            )
            async for chunk in stream:
                chunk_choices = getattr(chunk, "choices", None)
                if not chunk_choices:
                    continue
                delta = getattr(chunk_choices[0], "delta", None)
                delta_content = getattr(delta, "content", None) if delta else None
                if delta_content:
                    emitted_any = True
                    yield f"data: {json.dumps({'type': 'chunk', 'text': delta_content})}\n\n"
                    await asyncio.sleep(0)
            if not emitted_any:
                if last_tool_result:
                    summary = _summarize_tool_result(last_tool_name, last_tool_result)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': summary})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'chunk', 'text': 'No pude ejecutar la acción automáticamente. Reintentá o reformulá con más detalle.'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': f'Stream error: {e}'})}\n\n"
        emitted_final = True
        break

    if not emitted_final:
        if last_tool_result:
            summary = _summarize_tool_result(last_tool_name, last_tool_result)
            yield f"data: {json.dumps({'type': 'chunk', 'text': summary})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'chunk', 'text': 'No se generó una respuesta útil. Probá de nuevo.'})}\n\n"

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


async def _run_internal_agent_once(
    message: str,
    history: list[dict],
    system_prompt: str = "",
    folder_id: str = "",
) -> dict:
    text_chunks: list[str] = []
    steps: list[dict] = []
    error_text = ""
    async for raw in _agent_stream_normal(message, history, system_prompt, folder_id):
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
    return {
        "text": "".join(text_chunks).strip(),
        "steps": steps,
        "error": error_text.strip(),
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
) -> AsyncGenerator[str, None]:
    from guardrails.validator import validate_input
    safety = validate_input(message)
    if not safety.get("valid", True):
        err = safety.get("error", "Query rejected by safety filter.")
        yield f"data: {json.dumps({'type': 'error', 'text': err})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    client, model = _get_client()
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
    final_system = f"{_compose_system_prompt(system_prompt)}\n\n{plan_protocol}"
    messages: list[dict] = [{"role": "system", "content": final_system}]
    for h in history[-14:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": message})

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            timeout=120,
        )
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

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


async def _iterate_stream(
    message: str,
    history: list[dict],
    system_prompt: str = "",
    folder_id: str = "",
) -> AsyncGenerator[str, None]:
    from guardrails.validator import validate_input
    safety = validate_input(message)
    if not safety.get("valid", True):
        err = safety.get("error", "Query rejected by safety filter.")
        yield f"data: {json.dumps({'type': 'error', 'text': err})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    client, model = _get_client()
    sys_prompt = _compose_system_prompt(system_prompt)

    plan_req = (
        "Generá un plan de ejecución en JSON puro con esta forma:\n"
        "{\"objective\":\"...\",\"stages\":[{\"name\":\"...\",\"goal\":\"...\"}]}\n"
        "Máximo 6 etapas. Sin texto extra."
    )
    planning_messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": f"{plan_req}\n\nTarea: {message}"}]
    stages = [{"name": "Resolver tarea", "goal": message}]
    objective = message
    try:
        plan_resp = await client.chat.completions.create(
            model=model,
            messages=planning_messages,
            stream=False,
            timeout=60,
        )
        content = getattr(getattr(plan_resp.choices[0], "message", None), "content", "") if getattr(plan_resp, "choices", None) else ""
        plan_json = _extract_json_object(content)
        if isinstance(plan_json, dict):
            objective = str(plan_json.get("objective") or message)
            raw_stages = plan_json.get("stages")
            if isinstance(raw_stages, list) and raw_stages:
                parsed = []
                for s in raw_stages[:6]:
                    if not isinstance(s, dict):
                        continue
                    name = str(s.get("name") or "").strip()
                    goal = str(s.get("goal") or "").strip()
                    if name and goal:
                        parsed.append({"name": name, "goal": goal})
                if parsed:
                    stages = parsed
    except Exception:
        pass

    plan_md = [f"## Plan de ejecución (Iterador)\n", f"**Objetivo:** {objective}\n"]
    for i, s in enumerate(stages, 1):
        plan_md.append(f"{i}. **{s['name']}** — {s['goal']}")
    yield f"data: {json.dumps({'type': 'chunk', 'text': '\\n'.join(plan_md) + '\\n\\n'})}\n\n"

    exec_history = history[-10:]
    max_retries = 2
    for i, stage in enumerate(stages, 1):
        stage_name = stage.get("name", "")
        stage_goal = stage.get("goal", "")
        yield f"data: {json.dumps({'type': 'chunk', 'text': f'### Etapa {i}/{len(stages)}: {stage_name}\\n'})}\n\n"
        stage_ok = False
        last_output = ""
        for attempt in range(1, max_retries + 1):
            stage_prompt = (
                f"Objetivo global: {objective}\n"
                f"Etapa actual: {stage_name}\n"
                f"Meta de etapa: {stage_goal}\n"
                f"Intento {attempt}/{max_retries}. Ejecutá las acciones necesarias usando herramientas y reportá resultado."
            )
            result = await _run_internal_agent_once(stage_prompt, exec_history, system_prompt, folder_id)
            last_output = result.get("text") or result.get("error") or ""
            if result.get("error"):
                yield f"data: {json.dumps({'type': 'chunk', 'text': f'Intento {attempt}: error -> {result['error']}\\n'})}\n\n"
            elif last_output:
                yield f"data: {json.dumps({'type': 'chunk', 'text': f'Intento {attempt}: {last_output}\\n'})}\n\n"

            validate_prompt = (
                "Evaluá si la etapa está cumplida. Respondé JSON puro:\n"
                "{\"passed\": true|false, \"reason\": \"...\"}\n\n"
                f"Etapa: {stage_name}\n"
                f"Meta: {stage_goal}\n"
                f"Salida: {last_output[:3000]}"
            )
            passed = False
            reason = ""
            try:
                val_resp = await client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": validate_prompt}],
                    stream=False,
                    timeout=40,
                )
                val_content = getattr(getattr(val_resp.choices[0], "message", None), "content", "") if getattr(val_resp, "choices", None) else ""
                val_json = _extract_json_object(val_content)
                passed = bool(val_json.get("passed"))
                reason = str(val_json.get("reason") or "")
            except Exception:
                passed = bool(last_output and "error" not in last_output.lower())
                reason = "Validación heurística aplicada."

            if passed:
                stage_ok = True
                ok_reason = reason or "ok"
                yield f"data: {json.dumps({'type': 'chunk', 'text': f'✅ Etapa validada: {ok_reason}\\n\\n'})}\n\n"
                break
            else:
                fail_reason = reason or "sin razón"
                yield f"data: {json.dumps({'type': 'chunk', 'text': f'⚠️ Etapa no validada: {fail_reason}. Reintentando...\\n'})}\n\n"

        if not stage_ok:
            yield f"data: {json.dumps({'type': 'chunk', 'text': f'❌ No se pudo completar la etapa \"{stage_name}\" tras {max_retries} intentos.\\n\\n'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        exec_history = (exec_history + [{"role": "assistant", "content": last_output}])[-12:]

    yield f"data: {json.dumps({'type': 'chunk', 'text': '## Iteración finalizada\\nSe completaron y validaron todas las etapas del plan.'})}\n\n"
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


async def _agent_stream(
    message: str,
    history: list[dict],
    system_prompt: str = "",
    folder_id: str = "",
    mode: str = "normal",
) -> AsyncGenerator[str, None]:
    m = (mode or "normal").strip().lower()
    if m == "plan":
        async for ev in _plan_stream(message, history, system_prompt):
            yield ev
        return
    if m == "iterate":
        async for ev in _iterate_stream(message, history, system_prompt, folder_id):
            yield ev
        return
    async for ev in _agent_stream_normal(message, history, system_prompt, folder_id):
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
        _agent_stream(req.message, req.history, req.system_prompt, req.folder_id, req.mode),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
# llama.cpp process management
# ─────────────────────────────────────────────────────────────────────────────

_llamacpp_proc: Optional[subprocess.Popen] = None


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
    if _llamacpp_proc is None or _llamacpp_proc.poll() is not None:
        _llamacpp_proc = None
        return {"status": "not_running"}
    _llamacpp_proc.terminate()
    try:
        _llamacpp_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _llamacpp_proc.kill()
    _llamacpp_proc = None
    return {"status": "stopped"}


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
        preferred = Path.home() / "Models" / "llamacpp"
        fallback = Path.home() / "Models"
        if preferred.exists():
            models_dir = str(preferred)
        elif fallback.exists():
            models_dir = str(fallback)
        else:
            models_dir = str(preferred)
            preferred.mkdir(parents=True, exist_ok=True)

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
        if f.is_file()
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
    print(f"UNLZ Agent Server v2 — port {port}")
    print(f"Provider : {Config.LLM_PROVIDER}")
    print(f"Language : {Config.AGENT_LANGUAGE}")
    if Config.LLM_PROVIDER == "llamacpp":
        print(f"Model    : {Config.LLAMACPP_MODEL_ALIAS} @ {Config.LLAMACPP_MODEL_PATH}")
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
