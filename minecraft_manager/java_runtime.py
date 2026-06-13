from __future__ import annotations

import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .models import app_data_dir


class JavaNotFoundError(RuntimeError):
    pass


def find_java(version: str = "17") -> str:
    managed = _find_managed_jdk(version)
    if managed:
        return str(managed)
    exact = _find_exact_java_home(version)
    if exact:
        return f"{exact}/bin/java"
    extracted = _find_extracted_jdk(version)
    if extracted:
        return str(extracted)
    if version:
        if not _major(version):
            raise JavaNotFoundError(f"Version Java invalide: {version}.")
        raise JavaNotFoundError(
            f"Java {version} est introuvable. Installe Temurin {version} ou configure un chemin Java compatible."
        )
    java = shutil.which("java")
    return java or "java"


def java_available(version: str) -> bool:
    try:
        find_java(version)
        return True
    except JavaNotFoundError:
        return False


def managed_java_root() -> Path:
    return app_data_dir() / "java"


def download_java(version: str, progress: Optional[Callable[[int, int], None]] = None) -> str:
    major = _major(version)
    if not major:
        raise JavaNotFoundError("Version Java invalide.")
    arch = _adoptium_arch()
    url = f"https://api.adoptium.net/v3/binary/latest/{major}/ga/mac/{arch}/jdk/hotspot/normal/eclipse"
    target_dir = managed_java_root() / major
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"mcm-java-{major}-") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / f"temurin-{major}.tar.gz"
        _download_file(url, archive, progress)
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        with tarfile.open(archive, "r:gz") as tar:
            _safe_extract(tar, extract_dir)
        java = _first_java_in(extract_dir)
        if not java:
            raise JavaNotFoundError("Le JDK téléchargé ne contient pas de binaire Java utilisable.")
        if _java_major(java) != major:
            raise JavaNotFoundError(f"Le JDK téléchargé n’est pas Java {major}.")
        jdk_root = _jdk_root_from_java(java)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / jdk_root.name
        shutil.move(str(jdk_root), str(destination))

    java = _find_managed_jdk(major)
    if not java:
        raise JavaNotFoundError(f"Java {major} a été téléchargé, mais l’application ne le retrouve pas.")
    return str(java)


def _download_file(url: str, destination: Path, progress: Optional[Callable[[int, int], None]]) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "GestionServeursMinecraft/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        with destination.open("wb") as fh:
            while True:
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                fh.write(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)
    if not destination.exists() or destination.stat().st_size == 0:
        raise JavaNotFoundError("Téléchargement Java incomplet.")


def _safe_extract(tar: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in tar.getmembers():
        target = (destination / member.name).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise JavaNotFoundError("Archive Java invalide.") from exc
    tar.extractall(destination)


def _adoptium_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "aarch64"
    return "x64"


def _find_exact_java_home(version: str) -> str:
    major = _major(version)
    if not major:
        return ""
    try:
        output = subprocess.check_output(
            ["/usr/libexec/java_home", "-V"],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    for line in output.splitlines():
        match = re.match(r"\s*(?P<version>\d+(?:\.\d+)*)\s+\([^)]*\).*?\s(?P<home>/.*)$", line)
        if not match:
            continue
        if _major(match.group("version")) == major:
            return match.group("home").strip()
    return ""


def _major(version: str) -> str:
    match = re.match(r"\s*(\d+)(?:\.(\d+))?", str(version))
    if not match:
        return ""
    major = match.group(1)
    minor = match.group(2)
    if major == "1" and minor == "8":
        return "8"
    if major == "1" and minor:
        return ""
    return major


def _find_extracted_jdk(version: str) -> str:
    major = _major(version)
    if not major:
        return ""
    roots = [
        Path.home() / "Downloads",
        Path.home() / "Desktop",
        Path.home() / "Applications",
        Path.home() / "Library" / "Java" / "JavaVirtualMachines",
    ]
    for root in roots:
        if not root.exists():
            continue
        for java in root.glob(f"**/jdk-{major}*/Contents/Home/bin/java"):
            if _java_major(java) == major:
                return str(java)
        for java in root.glob(f"**/*-{major}*/Contents/Home/bin/java"):
            if _java_major(java) == major:
                return str(java)
    return ""


def _find_managed_jdk(version: str) -> str:
    major = _major(version)
    if not major:
        return ""
    root = managed_java_root() / major
    java = _first_matching_java(root, major)
    return str(java) if java else ""


def _first_java_in(root: Path) -> Optional[Path]:
    return _first_matching_java(root, "")


def _jdk_root_from_java(java: Path) -> Path:
    parts = java.parts
    if len(parts) >= 4 and parts[-4:] == ("Contents", "Home", "bin", "java"):
        return java.parents[3]
    if len(parts) >= 2 and parts[-2:] == ("bin", "java"):
        return java.parents[1]
    raise JavaNotFoundError("Structure du JDK téléchargé non reconnue.")


def _first_matching_java(root: Path, major: str) -> Optional[Path]:
    if not root.exists():
        return None
    for java in root.glob("**/Contents/Home/bin/java"):
        if not major or _java_major(java) == major:
            return java
    for java in root.glob("**/bin/java"):
        if not major or _java_major(java) == major:
            return java
    return None


def _java_major(java: Path) -> str:
    try:
        output = subprocess.check_output(
            [str(java), "-version"],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    match = re.search(r'version "(\d+)', output)
    return match.group(1) if match else ""
