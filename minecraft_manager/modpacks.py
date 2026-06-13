from __future__ import annotations

import json
import shutil
import urllib.request
import zipfile
from pathlib import Path
from typing import List


class ModpackError(RuntimeError):
    pass


def _safe_target(base: Path, relative: str) -> Path:
    target = (base / relative).resolve()
    base_resolved = base.resolve()
    if base_resolved != target and base_resolved not in target.parents:
        raise ModpackError(f"Chemin dangereux dans le modpack: {relative}")
    return target


def _extract_member(zf: zipfile.ZipFile, member: zipfile.ZipInfo, destination: Path, relative: str) -> None:
    if member.is_dir():
        _safe_target(destination, relative).mkdir(parents=True, exist_ok=True)
        return
    target = _safe_target(destination, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member, "r") as src, target.open("wb") as dst:
        shutil.copyfileobj(src, dst)


def _download_file(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response, target.open("wb") as fh:
        shutil.copyfileobj(response, fh)


def import_modpack(archive_path: str, server_folder: Path) -> List[str]:
    if not archive_path:
        return []

    archive = Path(archive_path).expanduser()
    if not archive.exists():
        raise ModpackError(f"Modpack introuvable: {archive}")

    notes: List[str] = []
    with zipfile.ZipFile(archive, "r") as zf:
        root_prefix = _single_root_prefix(zf)
        names = [_strip_prefix(name, root_prefix) for name in zf.namelist()]
        if "modrinth.index.json" in names:
            notes.extend(_import_modrinth_pack(zf, server_folder, root_prefix))
        elif "manifest.json" in names and any(name.startswith("overrides/") for name in names):
            notes.extend(_extract_prefixed_folder(zf, server_folder, "overrides/", root_prefix))
            notes.append("Modpack CurseForge: overrides importés. Les mods du manifeste nécessitent souvent le launcher CurseForge.")
        else:
            notes.extend(_extract_server_zip(zf, server_folder, root_prefix))
    return notes


def _single_root_prefix(zf: zipfile.ZipFile) -> str:
    roots = set()
    for name in zf.namelist():
        if name.startswith("__MACOSX/") or name.endswith(".DS_Store"):
            continue
        parts = [part for part in name.split("/") if part]
        if parts:
            roots.add(parts[0])
    if len(roots) != 1:
        return ""
    root = next(iter(roots))
    root_prefix = f"{root}/"
    server_markers = {
        "mods",
        "config",
        "defaultconfigs",
        "kubejs",
        "server.properties",
        "startserver.sh",
        "startserver.bat",
        "startserver.cmd",
        "start.bat",
        "start.cmd",
        "run.bat",
        "run.cmd",
        "start.ps1",
        "run.ps1",
        "user_jvm_args.txt",
    }
    names = {_strip_prefix(name, root_prefix).split("/", 1)[0] for name in zf.namelist() if name.startswith(root_prefix)}
    has_forge_installer = any(_strip_prefix(name, root_prefix).startswith("forge-") and name.endswith("-installer.jar") for name in zf.namelist())
    return root_prefix if has_forge_installer or bool(server_markers & names) else ""


def _strip_prefix(name: str, prefix: str) -> str:
    return name[len(prefix):] if prefix and name.startswith(prefix) else name


def _extract_server_zip(zf: zipfile.ZipFile, server_folder: Path, root_prefix: str = "") -> List[str]:
    count = 0
    for member in zf.infolist():
        name = _strip_prefix(member.filename, root_prefix)
        if not name:
            continue
        if name.startswith("__MACOSX/") or name.endswith(".DS_Store"):
            continue
        _extract_member(zf, member, server_folder, name)
        count += 1
    flatten_note = "dossier racine aplati, " if root_prefix else ""
    return [f"Modpack serveur importé ({flatten_note}{count} élément(s))."]


def _extract_prefixed_folder(zf: zipfile.ZipFile, server_folder: Path, prefix: str, root_prefix: str = "") -> List[str]:
    count = 0
    for member in zf.infolist():
        name = _strip_prefix(member.filename, root_prefix)
        if not name.startswith(prefix):
            continue
        relative = name[len(prefix):]
        if not relative:
            continue
        _extract_member(zf, member, server_folder, relative)
        count += 1
    return [f"Dossier {prefix.rstrip('/')} importé ({count} élément(s))."]


def _import_modrinth_pack(zf: zipfile.ZipFile, server_folder: Path, root_prefix: str = "") -> List[str]:
    index = json.loads(zf.read(f"{root_prefix}modrinth.index.json").decode("utf-8"))
    notes: List[str] = []
    for prefix in ("overrides/", "server-overrides/"):
        if any(_strip_prefix(name, root_prefix).startswith(prefix) for name in zf.namelist()):
            notes.extend(_extract_prefixed_folder(zf, server_folder, prefix, root_prefix))

    downloaded = 0
    skipped = 0
    for file_info in index.get("files", []):
        env = file_info.get("env") or {}
        if env.get("server") == "unsupported":
            skipped += 1
            continue
        downloads = file_info.get("downloads") or []
        if not downloads:
            skipped += 1
            continue
        target = _safe_target(server_folder, file_info.get("path", ""))
        _download_file(downloads[0], target)
        downloaded += 1

    notes.append(f"Modpack Modrinth importé: {downloaded} fichier(s) téléchargé(s), {skipped} ignoré(s).")
    return notes
