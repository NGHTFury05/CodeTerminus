"""Streaming subprocess sandbox with cwd tracking and interrupt support."""
from __future__ import annotations

import asyncio
import os
import platform
import signal
import time
from dataclasses import dataclass
from typing import AsyncIterator, Dict, Optional

from backend.config import settings
from backend.exec.os_adapter import translate_command

_IS_WINDOWS = platform.system().lower() == "windows"


@dataclass
class OutputChunk:
    text: str
    stream: str  # 'stdout' | 'stderr' | 'system'
    exit_code: Optional[int] = None
    duration_ms: Optional[float] = None
    cwd: Optional[str] = None  # populated when cd changes directory


class Sandbox:
    """One execution context per terminal session. Tracks cwd, streams output."""

    def __init__(self, session_id: str, initial_cwd: Optional[str] = None, timeout: Optional[int] = None):
        self.session_id = session_id
        self.cwd: str = initial_cwd or os.getcwd()
        self.timeout: int = timeout or settings.MAX_CMD_TIMEOUT
        self._process: Optional[asyncio.subprocess.Process] = None
        self._env: Dict[str, str] = os.environ.copy()

    # ── cd handling ───────────────────────────────────────────────────────────
    def _is_cd(self, cmd: str) -> bool:
        s = cmd.strip()
        return s == "cd" or s.startswith("cd ") or s.startswith("cd\t")

    def _handle_cd(self, command: str) -> OutputChunk:
        parts = command.strip().split(None, 1)
        target = os.path.expanduser("~") if len(parts) == 1 else os.path.expandvars(
            os.path.expanduser(parts[1].strip())
        )
        if not os.path.isabs(target):
            target = os.path.join(self.cwd, target)
        target = os.path.normpath(target)
        if os.path.isdir(target):
            self.cwd = target
            return OutputChunk(text="", stream="system", exit_code=0, cwd=target)
        else:
            return OutputChunk(
                text=f"cd: no such file or directory: {parts[1] if len(parts) > 1 else ''}\n",
                stream="stderr",
                exit_code=1,
            )

    # ── Main streaming execute ────────────────────────────────────────────────
    async def run(self, command: str) -> AsyncIterator[OutputChunk]:
        """Stream stdout/stderr chunks; final chunk carries exit_code + duration_ms."""
        command = translate_command(command.strip())

        if self._is_cd(command):
            yield self._handle_cd(command)
            return

        queue: asyncio.Queue[Optional[OutputChunk]] = asyncio.Queue()
        start = time.perf_counter()

        try:
            if _IS_WINDOWS:
                proc = await asyncio.create_subprocess_shell(
                    f'cmd /c "{command}"',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.cwd,
                    env=self._env,
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.cwd,
                    env=self._env,
                )
        except Exception as e:
            yield OutputChunk(text=f"Failed to start: {e}\n", stream="stderr", exit_code=-1)
            return

        self._process = proc

        async def pump(stream: asyncio.StreamReader, name: str) -> None:
            try:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    await queue.put(OutputChunk(text=line.decode("utf-8", errors="replace"), stream=name))
            except Exception:
                pass
            finally:
                await queue.put(None)  # sentinel

        t1 = asyncio.create_task(pump(proc.stdout, "stdout"))
        t2 = asyncio.create_task(pump(proc.stderr, "stderr"))
        done_sentinels = 0

        while done_sentinels < 2:
            remaining = self.timeout - (time.perf_counter() - start)
            if remaining <= 0:
                proc.kill()
                yield OutputChunk(text=f"\n⏱ Timed out after {self.timeout}s\n", stream="system")
                break
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=max(remaining, 0.1))
                if chunk is None:
                    done_sentinels += 1
                else:
                    yield chunk
            except asyncio.TimeoutError:
                proc.kill()
                yield OutputChunk(text=f"\n⏱ Timed out after {self.timeout}s\n", stream="system")
                break

        await asyncio.gather(t1, t2, return_exceptions=True)
        await proc.wait()
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        self._process = None
        yield OutputChunk(text="", stream="system", exit_code=proc.returncode, duration_ms=duration_ms)

    # ── Interrupt ─────────────────────────────────────────────────────────────
    async def interrupt(self) -> bool:
        """Send SIGINT to the running process. Returns True if one was running."""
        if self._process and self._process.returncode is None:
            try:
                if _IS_WINDOWS:
                    self._process.terminate()
                else:
                    self._process.send_signal(signal.SIGINT)
                return True
            except ProcessLookupError:
                pass
        return False
