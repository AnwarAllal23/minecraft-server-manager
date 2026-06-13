from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from .models import ServerProfile


BACKUP_ITEMS = [
    "world",
    "server.properties",
    "whitelist.json",
    "ops.json",
    "banned-players.json",
    "banned-ips.json",
    "mods",
    "plugins",
    "datapacks",
]


def backups_dir(profile: ServerProfile) -> Path:
    path = profile.folder_path / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_backup(profile: ServerProfile, label: str = "manual") -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = backups_dir(profile) / f"{profile.name}-{label}-{stamp}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in BACKUP_ITEMS:
            source = profile.folder_path / item
            if not source.exists():
                continue
            if source.is_dir():
                for child in source.rglob("*"):
                    if child.is_file():
                        zf.write(child, child.relative_to(profile.folder_path))
            else:
                zf.write(source, source.relative_to(profile.folder_path))
    return archive


def restore_backup(profile: ServerProfile, archive: Path) -> None:
    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(profile.folder_path)


def backup_files(profile: ServerProfile) -> list[Path]:
    return sorted(backups_dir(profile).glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
