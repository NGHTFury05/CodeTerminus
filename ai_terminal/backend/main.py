"""FastAPI app — WebSocket gateway, REST API, static file server."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.exec.os_adapter import get_metrics
from backend.plugins import registry
from backend.router.command_router import CommandRouter, SessionState
from backend.storage import db as dbmod
from backend.storage import sessions as sessions_mod


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    await dbmod.init_db()
    registry.load_plugins()
    print("\n✅  CodeTerminus AI Terminal Agent is ready")
    print(f"   Profile : {settings.SECURITY_PROFILE}")
    print(f"   AI      : {'OpenRouter' if settings.OPENROUTER_API_KEY else '—'}  LM Studio: {'✔' if settings.LM_STUDIO_AVAILABLE else '—'}")
    print(f"   Vector  : {'ChromaDB' if settings.USE_VECTOR_STORE else 'disabled'}\n")
    yield
    print("🛑 Shutting down…")


app = FastAPI(title="CodeTerminus", lifespan=lifespan)

# Static frontend
_frontend = Path(__file__).parent.parent / "frontend"
if _frontend.exists():
    app.mount("/static", StaticFiles(directory=str(_frontend)), name="static")

# In-memory session states (survive reconnects within the same process)
_sessions: dict[str, SessionState] = {}


# ── HTML entry point ──────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    index = _frontend / "index.html"
    if index.exists():
        return HTMLResponse(content=index.read_text())
    return HTMLResponse("<p>Frontend not built yet. See ai_terminal/frontend/.</p>")


# ── REST endpoints ─────────────────────────────────────────────────────────────
@app.get("/api/sessions")
async def api_sessions():
    return sessions_mod.list_sessions()


@app.get("/api/history/{session_id}")
async def api_history(session_id: str, limit: int = 20):
    return await dbmod.get_recent_commands(session_id, limit=limit)


@app.get("/api/metrics")
async def api_metrics():
    m = get_metrics()
    return {
        "cpu": m.cpu_percent, "ram": m.ram_percent, "gpu": m.gpu_percent,
        "disk_read_mb_s": m.disk.read_mb_s, "disk_write_mb_s": m.disk.write_mb_s,
        "disk_percent": m.disk.percent,
        "net_sent_mb_s": m.network.sent_mb_s, "net_recv_mb_s": m.network.recv_mb_s,
        "process_count": m.process_count,
    }


@app.post("/api/sessions/{name}/export")
async def api_export(name: str):
    data = sessions_mod.export_session(name)
    if data is None:
        return {"error": "Session not found"}
    return {"name": name, "data": data.decode()}


@app.delete("/api/sessions/{name}")
async def api_delete_session(name: str):
    ok = sessions_mod.delete_session(name)
    return {"deleted": ok}


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    if session_id not in _sessions:
        _sessions[session_id] = SessionState(session_id=session_id)
    state = _sessions[session_id]
    router = CommandRouter(state)

    async def send(msg: dict):
        try:
            await websocket.send_text(json.dumps(msg))
        except Exception:
            pass

    # ── Background metrics task ───────────────────────────────────────────────
    async def push_metrics():
        while True:
            try:
                m = get_metrics()
                await send({
                    "type": "metrics",
                    "cpu": m.cpu_percent, "ram": m.ram_percent, "gpu": m.gpu_percent,
                    "disk_read_mb_s": m.disk.read_mb_s, "disk_write_mb_s": m.disk.write_mb_s,
                    "disk_percent": m.disk.percent,
                    "net_sent_mb_s": m.network.sent_mb_s, "net_recv_mb_s": m.network.recv_mb_s,
                    "process_count": m.process_count,
                })
                await asyncio.sleep(2)
            except Exception:
                break

    metrics_task = asyncio.create_task(push_metrics())

    # ── Initial state push ────────────────────────────────────────────────────
    await send({"type": "cwd_change", "cwd": state.cwd})
    await send({"type": "sessions", "sessions": sessions_mod.list_sessions()})
    history = await dbmod.get_recent_commands(session_id, limit=15)
    await send({"type": "history", "items": history})
    await send({
        "type": "output_chunk", "stream": "system",
        "text": (
            "\r\n\x1b[1;36m╔══════════════════════════════════════════╗\r\n"
            "║  \x1b[1;37mCodeTerminus\x1b[1;36m — AI Terminal Agent         ║\r\n"
            "║  \x1b[0;32mType naturally or use direct commands\x1b[1;36m    ║\r\n"
            "║  \x1b[0;33mCtrl+K\x1b[1;36m = Command Palette                  ║\r\n"
            "╚══════════════════════════════════════════╝\x1b[0m\r\n\r\n"
        ),
    })

    # ── Message loop ──────────────────────────────────────────────────────────
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            t = msg.get("type")

            if t == "input":
                text = msg.get("text", "").strip()
                if not text:
                    continue
                async for out in router.handle(text):
                    await send(out)
                # Refresh history after each command
                history = await dbmod.get_recent_commands(session_id, limit=15)
                await send({"type": "history", "items": history})

            elif t == "confirm":
                action = msg.get("action", "approve")
                edited = msg.get("payload")
                if action == "approve" and state.current_plan:
                    async for out in router.execute_plan():
                        await send(out)
                    history = await dbmod.get_recent_commands(session_id, limit=15)
                    await send({"type": "history", "items": history})
                else:
                    async for out in router.handle_confirm(action, edited):
                        await send(out)

            elif t == "ctrl_c":
                interrupted = await state.sandbox.interrupt()
                if interrupted:
                    await send({"type": "output_chunk", "text": "^C\r\n", "stream": "system"})

            elif t == "meta":
                action = msg.get("action", "")
                session_name = msg.get("session", "")
                if action == "record_start" and session_name:
                    state.recording = True
                    state.recording_name = session_name
                    state.recording_commands = []
                    await send({"type": "recording_status", "recording": True, "name": session_name})
                    await send({"type": "output_chunk", "text": f"\r\n🔴 Recording: {session_name}\r\n", "stream": "system"})
                elif action == "record_stop":
                    if state.recording:
                        sessions_mod.save_session(state.recording_name, state.recording_commands)
                        state.recording = False
                        await send({"type": "recording_status", "recording": False})
                        await send({"type": "sessions", "sessions": sessions_mod.list_sessions()})
                elif action == "replay" and session_name:
                    async for out in router.handle(f"replay {session_name}"):
                        await send(out)

            elif t == "ping":
                await send({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws] Error in session {session_id}: {e}")
    finally:
        metrics_task.cancel()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
