from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, Optional

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None


def available_memory_gb() -> float:
    if psutil:
        return psutil.virtual_memory().available / (1024**3)
    return 0.0

def folder_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def disk_free(path: Path) -> int:
    target = path if path.exists() else path.parent
    return shutil.disk_usage(target).free


class ProcessMonitor:
    def __init__(self) -> None:
        self._process_cache = {}

    def snapshot(self, pid: Optional[int], folder: Path, folder_mb: float = 0.0) -> Dict[str, float]:
        """Collect cheap, instantaneous metrics for the dashboard.

        ``folder_mb`` is not recomputed here: walking the whole server
        folder (mods, world saves, libraries...) can take seconds and would
        freeze the UI if done every refresh tick. Callers compute it in a
        background thread and pass the last known value in.
        """
        ram_mb = 0.0
        cpu = 0.0
        process_count = 0
        if pid and psutil:
            try:
                processes = self._process_tree(pid)
                process_count = len(processes)
                for proc in processes:
                    try:
                        ram_mb += proc.memory_info().rss / (1024**2)
                        cpu += proc.cpu_percent(interval=None)
                    except psutil.Error:
                        continue
            except (psutil.Error, PermissionError, OSError):
                pass
        return {
            "ram_mb": ram_mb,
            "cpu": cpu,
            "process_count": float(process_count),
            "folder_mb": folder_mb,
            "disk_free_gb": disk_free(folder) / (1024**3),
        }

    def _process_tree(self, pid: int):
        root = self._cached_process(pid)
        try:
            children = root.children(recursive=True)
        except (psutil.Error, PermissionError, OSError):
            children = []
        return [root] + [self._cached_process(child.pid) for child in children if child.is_running()]

    def _cached_process(self, pid: int):
        proc = self._process_cache.get(pid)
        if proc and proc.is_running():
            return proc
        proc = psutil.Process(pid)
        self._process_cache[pid] = proc
        return proc
