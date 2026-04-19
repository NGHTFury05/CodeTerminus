"""Session file persistence — save/load .aits (AI Terminal Session) files."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import settings


def _session_path(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
    return settings.SESSIONS_DIR / f"{safe}.aits"


def list_sessions() -> List[Dict[str, Any]]:
    sessions = []
    for p in sorted(settings.SESSIONS_DIR.glob("*.aits")):
        try:
            data = json.loads(p.read_text())
            sessions.append(
                {
                    "name": data.get("name", p.stem),
                    "id": data.get("id", p.stem),
                    "command_count": len(data.get("commands", [])),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                }
            )
        except Exception:
            pass
    return sessions


def save_session(name: str, commands: List[str], session_id: Optional[str] = None) -> str:
    sid = session_id or str(uuid.uuid4())
    data = {
        "id": sid,
        "name": name,
        "commands": commands,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "version": "1.0",
    }
    _session_path(name).write_text(json.dumps(data, indent=2))
    return sid


def load_session(name: str) -> Optional[Dict[str, Any]]:
    path = _session_path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def append_to_session(name: str, command: str) -> None:
    data = load_session(name)
    if data:
        data["commands"].append(command)
        data["updated_at"] = datetime.utcnow().isoformat()
        _session_path(name).write_text(json.dumps(data, indent=2))


def export_session(name: str) -> Optional[bytes]:
    path = _session_path(name)
    return path.read_bytes() if path.exists() else None


def delete_session(name: str) -> bool:
    path = _session_path(name)
    if path.exists():
        path.unlink()
        return True
    return False
