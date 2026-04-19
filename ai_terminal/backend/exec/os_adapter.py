"""Platform abstraction: metrics, process list, command translation."""
from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from typing import List, Optional

import psutil

try:
    import GPUtil
    _GPU_AVAILABLE = True
except ImportError:
    _GPU_AVAILABLE = False

_IS_WINDOWS = platform.system().lower() == "windows"

# Previous I/O snapshots for rate calculation
_prev_disk_io = None
_prev_net_io = None
_prev_time: Optional[float] = None


@dataclass
class DiskInfo:
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float
    read_mb_s: float = 0.0
    write_mb_s: float = 0.0


@dataclass
class NetworkInfo:
    sent_mb_s: float
    recv_mb_s: float


@dataclass
class MetricsSnapshot:
    cpu_percent: float
    ram_percent: float
    gpu_percent: Optional[float]
    disk: DiskInfo
    network: NetworkInfo
    process_count: int
    os_type: str


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float
    status: str


def get_metrics() -> MetricsSnapshot:
    global _prev_disk_io, _prev_net_io, _prev_time
    import time

    now = time.time()
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk_usage = psutil.disk_usage("/")

    disk_read_mb_s = disk_write_mb_s = 0.0
    net_sent_mb_s = net_recv_mb_s = 0.0

    try:
        curr_disk = psutil.disk_io_counters()
        curr_net = psutil.net_io_counters()
        if _prev_disk_io and _prev_net_io and _prev_time:
            dt = max(now - _prev_time, 0.001)
            disk_read_mb_s = (curr_disk.read_bytes - _prev_disk_io.read_bytes) / dt / 1e6
            disk_write_mb_s = (curr_disk.write_bytes - _prev_disk_io.write_bytes) / dt / 1e6
            net_sent_mb_s = (curr_net.bytes_sent - _prev_net_io.bytes_sent) / dt / 1e6
            net_recv_mb_s = (curr_net.bytes_recv - _prev_net_io.bytes_recv) / dt / 1e6
        _prev_disk_io = curr_disk
        _prev_net_io = curr_net
        _prev_time = now
    except Exception:
        pass

    gpu_pct: Optional[float] = None
    if _GPU_AVAILABLE:
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu_pct = round(gpus[0].load * 100, 1)
        except Exception:
            pass

    return MetricsSnapshot(
        cpu_percent=round(cpu, 1),
        ram_percent=round(mem.percent, 1),
        gpu_percent=gpu_pct,
        disk=DiskInfo(
            total_gb=round(disk_usage.total / 1e9, 1),
            used_gb=round(disk_usage.used / 1e9, 1),
            free_gb=round(disk_usage.free / 1e9, 1),
            percent=disk_usage.percent,
            read_mb_s=round(max(disk_read_mb_s, 0), 2),
            write_mb_s=round(max(disk_write_mb_s, 0), 2),
        ),
        network=NetworkInfo(
            sent_mb_s=round(max(net_sent_mb_s, 0), 2),
            recv_mb_s=round(max(net_recv_mb_s, 0), 2),
        ),
        process_count=len(psutil.pids()),
        os_type=platform.system(),
    )


def get_process_list(limit: int = 20) -> List[ProcessInfo]:
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
        try:
            i = p.info
            procs.append(
                ProcessInfo(
                    pid=i["pid"],
                    name=i["name"] or "",
                    cpu_percent=i["cpu_percent"] or 0.0,
                    memory_mb=round(i["memory_info"].rss / 1e6 if i["memory_info"] else 0, 1),
                    status=i["status"] or "",
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(procs, key=lambda p: p.cpu_percent, reverse=True)[:limit]


def translate_command(command: str) -> str:
    """Map Unix ↔ Windows commands where needed."""
    if not _IS_WINDOWS:
        return command
    parts = command.strip().split(None, 1)
    if not parts:
        return command
    mappings = {"ls": "dir", "cat": "type", "clear": "cls", "rm": "del", "cp": "copy", "mv": "move"}
    if parts[0].lower() in mappings:
        rest = f" {parts[1]}" if len(parts) > 1 else ""
        return mappings[parts[0].lower()] + rest
    return command


def get_git_branch(cwd: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=2, cwd=cwd
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None
