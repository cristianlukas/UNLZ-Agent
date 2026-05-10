from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_opencode_1_profiles(path: str) -> list[dict[str, Any]]:
    """Load and normalize OpenCode launcher profiles for `1_*` entries.

    Purpose:
        Reads a JSON profile map and extracts only top-level profiles whose key
        starts with `1_`, returning a compact normalized structure used by the
        backend launcher/catalog flow.

    Parameters:
        path (str): JSON file path containing profile definitions.

    Returns:
        list[dict[str, Any]]: Normalized profile list with `profile_name`,
        `alias`, `opencode_model_id`, `model_folder`, and `ctx`.

    Raises:
        This function catches missing-file and JSON parse errors internally and
        returns an empty list on invalid input.
    """
    p = Path(path)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, dict):
        return []

    out: list[dict[str, Any]] = []
    for profile_name, cfg in raw.items():
        if not str(profile_name).startswith("1_"):
            continue
        if not isinstance(cfg, dict):
            continue
        out.append({
            "profile_name": str(profile_name),
            "alias": str(cfg.get("alias") or "").strip(),
            "opencode_model_id": str(cfg.get("opencode_model_id") or "").strip(),
            "model_folder": str(cfg.get("model_folder") or "").strip(),
            "ctx": int(cfg.get("ctx") or 131072),
        })
    return out
