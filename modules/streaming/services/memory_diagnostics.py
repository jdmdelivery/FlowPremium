"""Process memory snapshots for FFmpeg / Whisper diagnostics on Render."""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)


def _read_linux_meminfo() -> dict[str, int]:
    data: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split(":")
                if len(parts) != 2:
                    continue
                key = parts[0].strip()
                value_kb = int(parts[1].strip().split()[0])
                data[key] = value_kb
    except OSError:
        pass
    return data


def _rss_bytes() -> int | None:
    try:
        import psutil  # type: ignore

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        pass
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(counters),
                counters.cb,
            )
            return int(counters.WorkingSetSize)
        except Exception:
            pass
    return None


def memory_snapshot() -> dict[str, int | None]:
    rss = _rss_bytes()
    meminfo = _read_linux_meminfo()
    return {
        "rss_bytes": rss,
        "rss_mb": int(rss / (1024 * 1024)) if rss else None,
        "mem_available_kb": meminfo.get("MemAvailable"),
        "mem_total_kb": meminfo.get("MemTotal"),
    }


def log_memory(stage: str, *, episode_id: int | None = None, extra: str = "") -> dict:
    snap = memory_snapshot()
    avail_mb = None
    if snap.get("mem_available_kb"):
        avail_mb = int(snap["mem_available_kb"] / 1024)
    logger.info(
        "[memory] stage=%s episode=%s rss_mb=%s mem_available_mb=%s %s",
        stage,
        episode_id if episode_id is not None else "-",
        snap.get("rss_mb"),
        avail_mb if avail_mb is not None else "-",
        extra,
    )
    return snap


def is_low_ram_instance(threshold_mb: int = 768) -> bool:
    """True on Render free/starter tiers or when VIDEO_HLS_LOW_RAM is set."""
    from flask import current_app

    cfg = current_app.config.get("VIDEO_HLS_LOW_RAM")
    if cfg is not None:
        return bool(cfg)

    meminfo = _read_linux_meminfo()
    available_kb = meminfo.get("MemAvailable") or meminfo.get("MemFree")
    if available_kb is not None:
        return available_kb < threshold_mb * 1024

    total_kb = meminfo.get("MemTotal")
    if total_kb is not None:
        return total_kb < 1024 * 1024

    return True
