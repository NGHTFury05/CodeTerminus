"""Assembles the rich context payload injected into every AI prompt."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from backend.config import settings
from backend.exec.os_adapter import get_git_branch
from backend.storage import db as dbmod
from backend.storage import vector_store


async def build(session_id: str, user_input: str, cwd: str) -> Dict[str, Any]:
    """Gather recent history, directory listing, env vars, and similar past commands."""
    recent = await dbmod.get_recent_commands(session_id, limit=8)
    dir_listing = _dir_listing(cwd)
    env = _env_context(cwd)
    similar: List[str] = []
    if settings.USE_VECTOR_STORE:
        results = vector_store.search(user_input, n=3, session_id=session_id)
        similar = [r["text"] for r in results if r.get("score", 0) > 0.45]
    return {
        "os": _os_name(),
        "cwd": cwd,
        "dir_listing": dir_listing,
        "env": env,
        "recent_commands": recent,
        "similar_past_commands": similar,
    }


def format_context_for_prompt(ctx: Dict[str, Any]) -> str:
    """Render context dict as a human-readable prompt section."""
    lines = [f"OS: {ctx['os']}", f"CWD: {ctx['cwd']}"]
    env = ctx.get("env", {})
    if env.get("VIRTUAL_ENV"):
        lines.append(f"Active venv: {env['VIRTUAL_ENV']}")
    if env.get("GIT_BRANCH"):
        lines.append(f"Git branch: {env['GIT_BRANCH']}")
    if ctx.get("dir_listing"):
        lines.append(f"Files in cwd ({len(ctx['dir_listing'])} shown):")
        lines.extend(f"  {e}" for e in ctx["dir_listing"][:12])
    if ctx.get("recent_commands"):
        lines.append("Recent commands:")
        for c in ctx["recent_commands"][-5:]:
            ok = "✓" if c["success"] else "✗"
            lines.append(f"  {ok} {c['raw_input']}  (exit {c['exit_code']})")
    if ctx.get("similar_past_commands"):
        lines.append("Relevant past commands:")
        for c in ctx["similar_past_commands"]:
            lines.append(f"  - {c}")
    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _os_name() -> str:
    import platform
    return platform.system()


def _dir_listing(cwd: str, max_entries: int = 20) -> List[str]:
    try:
        entries = sorted(os.listdir(cwd), key=lambda e: (not os.path.isdir(os.path.join(cwd, e)), e))
        return [
            f"{'[d] ' if os.path.isdir(os.path.join(cwd, e)) else '    '}{e}"
            for e in entries[:max_entries]
        ]
    except Exception:
        return []


def _env_context(cwd: str) -> Dict[str, str]:
    keys = ["VIRTUAL_ENV", "CONDA_DEFAULT_ENV", "PATH", "USER", "HOME", "SHELL", "NODE_ENV"]
    ctx = {k: os.environ[k][:200] for k in keys if k in os.environ}
    branch = get_git_branch(cwd)
    if branch:
        ctx["GIT_BRANCH"] = branch
    return ctx
