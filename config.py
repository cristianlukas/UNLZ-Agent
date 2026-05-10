import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def _runtime_root_dir() -> Path:
    """Resolve the runtime root directory for the application.

    Purpose:
        Determines where runtime artifacts (for example `.env`, `data/`) should
        be read from depending on execution context.

    Parameters:
        None.

    Returns:
        Path: Absolute root directory used by the runtime.

    Raises:
        This function does not intentionally raise exceptions.
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


class Config:
    """Centralized runtime configuration loaded from environment variables.

    Purpose:
        Exposes static configuration attributes used across backend and desktop
        runtime initialization.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AttributeError: If calling code expects attributes that are not defined
        in this class.
    """
    AGENT_LANGUAGE = os.getenv("AGENT_LANGUAGE", "es").lower()
    AGENT_EXECUTION_MODE = os.getenv("AGENT_EXECUTION_MODE", "autonomous").lower()
    HARNESS_OPENCODE_BIN = os.getenv("HARNESS_OPENCODE_BIN", "")
    BASE_DIR = str(_runtime_root_dir())
    DATA_DIR = os.path.join(BASE_DIR, "data")
    WINDOW_CONTROLS_SIDE = os.getenv("WINDOW_CONTROLS_SIDE", "right")
    WINDOW_CONTROLS_STYLE = os.getenv("WINDOW_CONTROLS_STYLE", "windows")
    WINDOW_CONTROLS_ORDER = os.getenv("WINDOW_CONTROLS_ORDER", "minimize,maximize,close")


os.makedirs(Config.DATA_DIR, exist_ok=True)
