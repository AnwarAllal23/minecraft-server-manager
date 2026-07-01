from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

from .i18n import tr
from .models import app_data_dir


class JavaNotFoundError(RuntimeError):
    pass


def find_java(version: str = "17") -> str:
    managed = _find_managed_jdk(version)
    if managed:
        return str(managed)
    exact = _find_platform_java_home(version)
    if exact:
        return str(_java_binary(Path(exact) / "bin"))
    extracted = _find_extracted_jdk(version)
    if extracted:
        return str(extracted)
    system = _find_system_java(version)
    if system:
        return str(system)
    if version:
        if not _major(version):
            raise JavaNotFoundError(tr("Version Java invalide: {version}.").format(version=version))
        raise JavaNotFoundError(
            tr("Java {version} est introuvable. Installe Temurin {version} ou configure un chemin Java compatible.").format(version=version)
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
        raise JavaNotFoundError(tr("Version Java invalide."))

    os_name = _adoptium_os()
    arch = _adoptium_arch()
    archive_ext = "zip" if os_name == "windows" else "tar.gz"
    url = f"https://api.adoptium.net/v3/binary/latest/{major}/ga/{os_name}/{arch}/jdk/hotspot/normal/eclipse"
    target_dir = managed_java_root() / major
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"mcm-java-{major}-") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / f"temurin-{major}.{archive_ext}"
        _download_file(url, archive, progress)
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()
        if archive_ext == "zip":
            with zipfile.ZipFile(archive, "r") as zf:
                _safe_extract_zip(zf, extract_dir)
        else:
            with tarfile.open(archive, "r:gz") as tar:
                _safe_extract_tar(tar, extract_dir)

        java = _first_java_in(extract_dir)
        if not java:
            raise JavaNotFoundError(tr("Le JDK telecharge ne contient pas de binaire Java utilisable."))
        if _java_major(java) != major:
            raise JavaNotFoundError(tr("Le JDK telecharge n'est pas Java {major}.").format(major=major))
        jdk_root = _jdk_root_from_java(java)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / jdk_root.name
        shutil.move(str(jdk_root), str(destination))

    java = _find_managed_jdk(major)
    if not java:
        raise JavaNotFoundError(tr("Java {major} a ete telecharge, mais l'application ne le retrouve pas.").format(major=major))
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
        raise JavaNotFoundError(tr("Telechargement Java incomplet."))


def _safe_extract_tar(tar: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in tar.getmembers():
        target = (destination / member.name).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise JavaNotFoundError(tr("Archive Java invalide.")) from exc
    tar.extractall(destination)


def _safe_extract_zip(zf: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in zf.infolist():
        target = (destination / member.filename).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise JavaNotFoundError(tr("Archive Java invalide.")) from exc
    zf.extractall(destination)


def _adoptium_os() -> str:
    if sys.platform == "darwin":
        return "mac"
    if _is_windows():
        return "windows"
    return "linux"


def _adoptium_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "aarch64"
    return "x64"


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _find_platform_java_home(version: str) -> str:
    if sys.platform == "darwin":
        return _find_macos_java_home(version)
    if _is_windows():
        return _find_windows_java_home(version)
    return _find_unix_java_home(version)


def _find_macos_java_home(version: str) -> str:
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
        if match and _major(match.group("version")) == major:
            return match.group("home").strip()
    return ""


def _find_windows_java_home(version: str) -> str:
    major = _major(version)
    if not major:
        return ""
    for env_name in (f"JAVA_HOME_{major}", "JAVA_HOME"):
        value = os.environ.get(env_name, "")
        home = _valid_java_home(Path(value), major) if value else None
        if home:
            return str(home)

    roots: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        value = os.environ.get(env_name)
        if not value:
            continue
        roots.append(Path(value) / "Eclipse Adoptium")
        roots.append(Path(value) / "Java")
        roots.append(Path(value) / "Programs" / "Eclipse Adoptium")

    for root in roots:
        if not root.exists():
            continue
        for home in sorted(root.glob(f"**/jdk-{major}*")):
            valid = _valid_java_home(home, major)
            if valid:
                return str(valid)
    return ""


def _find_unix_java_home(version: str) -> str:
    major = _major(version)
    if not major:
        return ""
    for env_name in (f"JAVA_HOME_{major}", "JAVA_HOME"):
        value = os.environ.get(env_name, "")
        home = _valid_java_home(Path(value), major) if value else None
        if home:
            return str(home)
    return ""


def _valid_java_home(home: Path, major: str) -> Optional[Path]:
    if not str(home):
        return None
    java = _java_binary(home / "bin")
    if java.exists() and _java_major(java) == major:
        return home
    return None


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
        Path.home() / "AppData" / "Local" / "Programs" / "Eclipse Adoptium",
    ]
    for root in roots:
        if not root.exists():
            continue
        for pattern in _jdk_search_patterns(major):
            for java in root.glob(pattern):
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
    if len(parts) >= 2 and parts[-2] == "bin" and java.name in _java_binary_names():
        return java.parents[1]
    raise JavaNotFoundError(tr("Structure du JDK telecharge non reconnue."))


def _first_matching_java(root: Path, major: str) -> Optional[Path]:
    if not root.exists():
        return None
    for pattern in _jdk_search_patterns(major or "*"):
        for java in root.glob(pattern):
            if not major or _java_major(java) == major:
                return java
    return None


def _jdk_search_patterns(major: str) -> list[str]:
    patterns = []
    version_globs = [f"jdk-{major}*", f"*-{major}*"] if major != "*" else ["jdk-*", "*"]
    for name in _java_binary_names():
        for version_glob in version_globs:
            patterns.append(f"**/{version_glob}/Contents/Home/bin/{name}")
            patterns.append(f"**/{version_glob}/bin/{name}")
        patterns.append(f"**/bin/{name}")
    return patterns


def _java_binary_names() -> tuple[str, ...]:
    return ("java.exe", "java") if _is_windows() else ("java",)


def _java_binary(bin_dir: Path) -> Path:
    for name in _java_binary_names():
        candidate = bin_dir / name
        if candidate.exists():
            return candidate
    return bin_dir / ("java.exe" if _is_windows() else "java")


def _find_system_java(version: str) -> str:
    major = _major(version)
    java = shutil.which("java")
    if not java:
        return ""
    if not major or _java_major(Path(java)) == major:
        return java
    return ""


def _java_major(java: Path) -> str:
    # java.exe is a console-subsystem executable: this is called once per
    # candidate found while searching for a Java runtime, and without
    # CREATE_NO_WINDOW each call can briefly flash a console window on
    # Windows even though stdout/stderr are fully captured here.
    popen_kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if _is_windows() else {}
    try:
        output = subprocess.check_output(
            [str(java), "-version"],
            text=True,
            stderr=subprocess.STDOUT,
            **popen_kwargs,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    match = re.search(r'version "(\d+)', output)
    return match.group(1) if match else ""
