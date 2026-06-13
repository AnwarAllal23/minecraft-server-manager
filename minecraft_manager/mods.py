from __future__ import annotations

import re
import shutil
from datetime import datetime
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def find_duplicate_mods(server_folder: Path) -> Dict[str, List[Path]]:
    mods_dir = server_folder / "mods"
    if not mods_dir.exists():
        return {}

    by_modid: Dict[str, List[Path]] = defaultdict(list)
    for jar in sorted(mods_dir.glob("*.jar")):
        for modid in sorted(set(modids_from_jar(jar))):
            by_modid[modid].append(jar)
    duplicates: Dict[str, List[Path]] = {}
    for modid, jars in by_modid.items():
        unique = _unique_paths(jars)
        if len(unique) > 1:
            duplicates[modid] = unique
    return duplicates


def modids_from_jar(jar: Path) -> List[str]:
    try:
        with zipfile.ZipFile(jar, "r") as zf:
            metadata_files = [name for name in ("META-INF/mods.toml", "META-INF/neoforge.mods.toml") if name in zf.namelist()]
            if not metadata_files:
                return []
            content = "\n".join(zf.read(name).decode("utf-8", errors="replace") for name in metadata_files)
    except (OSError, zipfile.BadZipFile):
        return []
    return list(dict.fromkeys(_modids_from_mods_toml(content)))


def _modids_from_mods_toml(content: str) -> List[str]:
    modids: List[str] = []
    inside_mod_block = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == "[[mods]]":
            inside_mod_block = True
            continue
        if stripped.startswith("[[") and stripped != "[[mods]]":
            inside_mod_block = False
            continue
        if not inside_mod_block:
            continue
        match = re.match(r"modId\s*=\s*[\"']([^\"']+)[\"']", stripped)
        if match:
            modids.append(match.group(1))
            inside_mod_block = False
    return modids


def format_duplicate_mods(duplicates: Dict[str, List[Path]]) -> str:
    lines: List[str] = []
    for modid, jars in sorted(duplicates.items()):
        lines.append(f"- {modid}:")
        for jar in jars:
            lines.append(f"  {jar.name}")
    return "\n".join(lines)


def disable_duplicate_mods(server_folder: Path) -> List[Path]:
    duplicates = find_duplicate_mods(server_folder)
    if not duplicates:
        return []

    mods_dir = server_folder / "mods"
    disabled_dir = server_folder / "mods_disabled_duplicates" / datetime.now().strftime("%Y%m%d-%H%M%S")
    to_disable: Dict[Path, Path] = {}
    for jars in duplicates.values():
        keep = _choose_mod_to_keep(jars)
        for jar in jars:
            if jar.resolve() != keep.resolve():
                to_disable[jar.resolve()] = jar

    moved: List[Path] = []
    for jar in sorted(to_disable.values()):
        if not jar.exists():
            continue
        disabled_dir.mkdir(parents=True, exist_ok=True)
        target = disabled_dir / jar.name
        counter = 2
        while target.exists():
            target = disabled_dir / f"{jar.stem}-{counter}{jar.suffix}"
            counter += 1
        shutil.move(str(jar), str(target))
        moved.append(target)

    if moved and not any(mods_dir.glob("*.jar")):
        raise RuntimeError("Tous les mods auraient été désactivés, opération annulée.")
    return moved


def _unique_paths(paths: List[Path]) -> List[Path]:
    seen = set()
    unique: List[Path] = []
    for path in paths:
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _choose_mod_to_keep(jars: List[Path]) -> Path:
    return sorted(jars, key=_mod_sort_key, reverse=True)[0]


def _mod_sort_key(jar: Path) -> tuple:
    try:
        stat = jar.stat()
        mtime = stat.st_mtime
        size = stat.st_size
    except OSError:
        mtime = 0
        size = 0
    return (_version_key(jar.name), mtime, size, jar.name.lower())


def _version_key(name: str) -> tuple:
    numbers = re.findall(r"\d+", name)
    return tuple(int(number) for number in numbers[-4:])
