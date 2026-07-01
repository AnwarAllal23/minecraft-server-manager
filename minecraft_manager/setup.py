from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .downloader import ForgeDownloader, VanillaDownloader
from .i18n import tr
from .java_runtime import JavaNotFoundError, find_java
from .models import ServerProfile
from .modpacks import import_modpack
from .mods import find_duplicate_mods, format_duplicate_mods
from .properties import read_properties, write_properties


SUPPORTED_MODLOADERS = ("Forge", "NeoForge", "Fabric", "Quilt", "LegacyFabric")


@dataclass
class ServerImportAnalysis:
    folder: Path
    server_type: str = "Custom"
    minecraft_version: str = "custom"
    modloader_version: str = ""
    java_version: str = "17"
    jar_file: str = ""
    source: str = ""

    @property
    def is_modded(self) -> bool:
        return is_modded_type(self.server_type)

    def summary(self) -> str:
        parts = [self.server_type]
        if self.minecraft_version and self.minecraft_version != "custom":
            parts.append(f"Minecraft {self.minecraft_version}")
        if self.modloader_version:
            parts.append(f"{self.server_type} {self.modloader_version}")
        parts.append(f"Java {self.java_version}")
        return " · ".join(parts)


def is_modded_type(server_type: str) -> bool:
    """Return True if ``server_type`` is one of the modloaders we manage.

    "Vanilla", "Paper" and "Custom" are NOT modded types: only the values in
    SUPPORTED_MODLOADERS go through the Forge/NeoForge/Fabric/Quilt install
    pipeline in create_forge_server(). This is the single switch that decides
    between "plain Minecraft jar" and "run a modloader installer" behaviour,
    so keep it in sync with SUPPORTED_MODLOADERS.
    """
    return canonical_modloader(server_type) in SUPPORTED_MODLOADERS


def canonical_modloader(server_type: str) -> str:
    """Normalize a server type string to its canonical modloader name.

    Comparison is case/space/dash-insensitive (e.g. "neo forge", "NeoForge"
    and "neo-forge" all resolve to "NeoForge"). If ``server_type`` does not
    match a known modloader (e.g. "Vanilla", "Custom"), it is returned
    unchanged so callers can still display/store it as-is.
    """
    normalized = (server_type or "").replace(" ", "").replace("-", "").lower()
    for modloader in SUPPORTED_MODLOADERS:
        if normalized == modloader.replace(" ", "").replace("-", "").lower():
            return modloader
    return server_type or ""


def create_server(profile: ServerProfile, download: bool = True) -> list[str]:
    """Entry point used by the UI to create a server from a fresh profile.

    The profile's ``server_type`` (chosen by the user in the "Nouveau
    serveur" dialog) decides which pipeline runs: a modloader type
    (Forge/NeoForge/Fabric/Quilt/LegacyFabric) goes through
    create_forge_server(), anything else (Vanilla, Custom...) goes through
    create_vanilla_server(). create_vanilla_server() never downloads or runs
    a modloader installer, so a profile created as "Vanilla" always stays a
    plain Minecraft server.
    """
    if is_modded_type(profile.server_type):
        return create_forge_server(profile, download)
    return create_vanilla_server(profile, download)


def create_vanilla_server(profile: ServerProfile, download: bool = True) -> list[str]:
    """Set up a plain Vanilla (or Custom) server: server.jar + properties + eula.

    This intentionally does nothing modloader-related: no installer is
    downloaded or executed here, so the resulting folder only ever contains
    the official Mojang server.jar plus the user's world/config files.
    """
    folder = profile.folder_path
    folder.mkdir(parents=True, exist_ok=True)
    profile.properties["server-port"] = str(profile.port)
    write_properties(folder / "server.properties", profile.properties)
    if not profile.eula_path.exists():
        profile.eula_path.write_text("eula=false\n", encoding="utf-8")
    required_java = required_java_for_minecraft(profile.version)
    if required_java:
        profile.java_version = required_java
    if download and not profile.jar_path.exists():
        VanillaDownloader().download_server(profile.version, profile.jar_path)
    return import_modpack(profile.modpack_path, folder)


def create_forge_server(profile: ServerProfile, download: bool = True) -> list[str]:
    """Set up a modded server (Forge/NeoForge/Fabric/Quilt/LegacyFabric).

    Resolution order, first match wins:
    1. A ready-to-run server pack (start.sh + variables.txt) -> just
       configure it for this app (Java path, RAM, no interactive prompts).
    2. An already-installed modloader under ``libraries/`` -> reuse it.
    3. A modloader installer .jar already present in the folder (e.g. from
       an imported CurseForge pack) -> run it with --installServer.
    4. Otherwise, for Forge only, download the official installer from Maven
       and run it. NeoForge/Fabric/Quilt/LegacyFabric without an installer
       or server pack are not auto-downloaded and raise an error asking the
       user to import the full server pack.
    """
    folder = profile.folder_path
    folder.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    notes.extend(import_modpack(profile.modpack_path, folder))

    properties_path = folder / "server.properties"
    if properties_path.exists():
        profile.properties = read_properties(properties_path)
    profile.properties["server-port"] = str(profile.port)
    write_properties(folder / "server.properties", profile.properties)
    if not profile.eula_path.exists():
        profile.eula_path.write_text("eula=false\n", encoding="utf-8")

    start_script = find_start_script(folder)
    variables = read_serverpack_variables(folder)
    if start_script and variables:
        configure_start_script_server(profile)
        notes.append(tr("Script serveur détecté: {name}.").format(name=start_script.name))
        notes.append(tr("variables.txt configuré pour Java et la RAM de l’application."))
        duplicates = find_duplicate_mods(folder)
        if duplicates:
            notes.append(tr("Mods dupliqués détectés:") + "\n" + format_duplicate_mods(duplicates))
        return notes

    modloader = canonical_modloader(profile.server_type) or "Forge"
    existing_install = existing_modloader_install(folder, modloader)
    embedded_installer = find_modloader_installer(folder, modloader)
    if existing_install:
        modloader, full_version, modloader_version = existing_install
        installer = None
        notes.append(tr("Installation {modloader} déjà présente: {version}.").format(modloader=modloader, version=full_version))
    elif embedded_installer:
        modloader = modloader_from_installer(embedded_installer) or modloader
        modloader_version = modloader_version_from_installer(embedded_installer) or profile.forge_version
        full_version = (
            full_version_from_installer(embedded_installer)
            or _full_version_from_parts(profile.version, modloader_version)
            or modloader_version
        )
        installer = embedded_installer
        notes.append(tr("Installateur {modloader} inclus détecté: {name}.").format(modloader=modloader, name=installer.name))
    else:
        if modloader != "Forge":
            raise RuntimeError(
                tr(
                    "{modloader} est reconnu, mais ce profil n’a pas de script serveur ni d’installateur utilisable. "
                    "Importe le pack serveur complet avec start.sh/variables.txt ou l’installateur serveur inclus."
                ).format(modloader=modloader)
            )
        downloader = ForgeDownloader()
        full_version = downloader.resolve_full_version(profile.version, profile.forge_version)
        modloader_version = full_version.split("-", 1)[1] if "-" in full_version else profile.forge_version
        installer = folder / f"forge-{full_version}-installer.jar"
        if download and not installer.exists():
            try:
                downloader.download_installer(full_version, installer)
            except Exception as exc:
                raise RuntimeError(
                    tr(
                        "Téléchargement Forge impossible. Si ton pack CurseForge contient déjà "
                        "un fichier forge-...-installer.jar, vérifie que tu importes bien le ZIP serveur complet.\n"
                        "Détail: {error}"
                    ).format(error=exc)
                ) from exc

    profile.server_type = modloader
    profile.forge_full_version = full_version
    profile.forge_version = modloader_version or (full_version.split("-", 1)[1] if "-" in full_version else profile.forge_version)
    required_java = required_java_for_minecraft(profile.version)
    if required_java:
        profile.java_version = required_java

    if installer:
        java = profile.java_path or find_java(profile.java_version)
        popen_kwargs = {}
        if sys.platform.startswith("win"):
            # java.exe is a console-subsystem executable: without this flag
            # Windows briefly flashes a console window for the installer,
            # even though its output is fully captured below.
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(
            [java, "-jar", installer.name, "--installServer"],
            cwd=str(folder),
            text=True,
            capture_output=True,
            check=False,
            **popen_kwargs,
        )
        if result.returncode != 0:
            output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
            raise RuntimeError(tr("Installation {modloader} échouée pour {version}.\n{output}").format(modloader=modloader, version=full_version, output=output))
        notes.append(tr("{modloader} {version} installé.").format(modloader=modloader, version=full_version))

    forge_server_jars = sorted(folder.glob(f"forge-{full_version}*-server.jar"))
    if forge_server_jars:
        profile.jar_file = forge_server_jars[0].name
    else:
        profile.jar_file = "forge-run"
    duplicates = find_duplicate_mods(folder)
    if duplicates:
        notes.append(tr("Mods dupliqués détectés:") + "\n" + format_duplicate_mods(duplicates))
    return notes


def _find_forge_installer(folder: Path) -> Optional[Path]:
    return find_forge_installer(folder)


def find_forge_installer(folder: Path) -> Optional[Path]:
    installers = sorted(folder.glob("forge-*-installer.jar"))
    return installers[0] if installers else None


def find_neoforge_installer(folder: Path) -> Optional[Path]:
    installers = sorted(folder.glob("neoforge-*-installer.jar"))
    return installers[0] if installers else None


def find_modloader_installer(folder: Path, preferred: str = "") -> Optional[Path]:
    preferred = canonical_modloader(preferred)
    loaders = [preferred] if preferred in {"Forge", "NeoForge"} else []
    loaders.extend(loader for loader in ("Forge", "NeoForge") if loader not in loaders)
    for loader in loaders:
        installer = find_forge_installer(folder) if loader == "Forge" else find_neoforge_installer(folder)
        if installer:
            return installer
    return None


def _full_version_from_installer(installer: Path) -> Optional[str]:
    return full_version_from_installer(installer)


def full_version_from_installer(installer: Path) -> Optional[str]:
    match = re.match(r"forge-(?P<version>.+)-installer\.jar$", installer.name)
    return match.group("version") if match else None


def modloader_from_installer(installer: Path) -> str:
    if installer.name.startswith("forge-"):
        return "Forge"
    if installer.name.startswith("neoforge-"):
        return "NeoForge"
    return ""


def modloader_version_from_installer(installer: Path) -> str:
    forge_full = full_version_from_installer(installer)
    if forge_full:
        return forge_full.split("-", 1)[1] if "-" in forge_full else forge_full
    match = re.match(r"neoforge-(?P<version>.+)-installer\.jar$", installer.name)
    return match.group("version") if match else ""


def _existing_forge_full_version(folder: Path) -> Optional[str]:
    return existing_forge_full_version(folder)


def existing_forge_full_version(folder: Path) -> Optional[str]:
    base = folder / "libraries" / "net" / "minecraftforge" / "forge"
    if not base.exists():
        return None
    for unix_args in sorted(base.glob("*/unix_args.txt")):
        return unix_args.parent.name
    return None


def existing_neoforge_version(folder: Path) -> Optional[str]:
    base = folder / "libraries" / "net" / "neoforged" / "neoforge"
    if not base.exists():
        return None
    for unix_args in sorted(base.glob("*/unix_args.txt")):
        return unix_args.parent.name
    return None


def existing_modloader_install(folder: Path, preferred: str = "") -> Optional[tuple[str, str, str]]:
    preferred = canonical_modloader(preferred)
    loaders = [preferred] if preferred in {"Forge", "NeoForge"} else []
    loaders.extend(loader for loader in ("Forge", "NeoForge") if loader not in loaders)
    variables = read_serverpack_variables(folder)
    minecraft_version = variables.get("MINECRAFT_VERSION", "")
    for loader in loaders:
        if loader == "Forge":
            full_version = existing_forge_full_version(folder)
            if full_version:
                modloader_version = full_version.split("-", 1)[1] if "-" in full_version else full_version
                return loader, full_version, modloader_version
        if loader == "NeoForge":
            modloader_version = existing_neoforge_version(folder)
            if modloader_version:
                full_version = _full_version_from_parts(minecraft_version, modloader_version) or modloader_version
                return loader, full_version, modloader_version
    return None


def minecraft_version_from_forge_full_version(full_version: str) -> str:
    parts = full_version.split("-")
    return parts[0] if parts else "custom"


def minecraft_version_from_modloader_full_version(full_version: str) -> str:
    if "-" not in full_version:
        return "custom"
    return minecraft_version_from_forge_full_version(full_version)


def required_java_for_minecraft(version: str) -> str:
    parts = _minecraft_version_parts(version)
    if not parts:
        return "17"
    major, minor, patch = parts
    if major > 1:
        return "21"
    if minor > 20 or (minor == 20 and patch >= 5):
        return "21"
    if minor >= 18:
        return "17"
    if minor == 17:
        return "16"
    return "8"


def normalize_java_version(value: str, minecraft_version: str = "") -> str:
    raw = str(value or "").strip().lower()
    raw = raw.replace("java", "").replace("jdk", "").replace("@", "").strip(" =_-")
    match = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", raw)
    if not match:
        return required_java_for_minecraft(minecraft_version)
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    if major == 1 and minor == 8:
        return "8"
    if major == 1 and minor:
        return required_java_for_minecraft(raw)
    if major in {8, 16, 17, 21}:
        return str(major)
    return required_java_for_minecraft(minecraft_version)


def _minecraft_version_parts(version: str) -> tuple[int, int, int]:
    match = re.match(r"\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", version or "")
    if not match:
        return ()
    return tuple(int(part or 0) for part in match.groups())


def _full_version_from_parts(minecraft_version: str, modloader_version: str) -> str:
    if minecraft_version and minecraft_version != "custom" and modloader_version:
        return f"{minecraft_version}-{modloader_version}"
    return ""


def looks_like_forge_server(folder: Path) -> bool:
    return looks_like_modded_server(folder)


def looks_like_modded_server(folder: Path) -> bool:
    return bool(
        existing_modloader_install(folder)
        or find_modloader_installer(folder)
        or find_start_script(folder)
        or (folder / "variables.txt").exists()
        or (folder / "startserver.sh").exists()
        or (folder / "startserver.bat").exists()
        or (folder / "startserver.cmd").exists()
        or (folder / "start.bat").exists()
        or (folder / "start.cmd").exists()
        or (folder / "run.bat").exists()
        or (folder / "run.cmd").exists()
        or (folder / "start.ps1").exists()
        or (folder / "run.ps1").exists()
        or (folder / "user_jvm_args.txt").exists()
        or (folder / "fabric-server-launch.jar").exists()
        or (folder / "fabric-server-launcher.jar").exists()
        or (folder / "quilt-server-launch.jar").exists()
    )


def analyze_server_folder(folder: Path) -> ServerImportAnalysis:
    folder = Path(folder)
    variables = read_serverpack_variables(folder)
    manifest = _read_pack_manifest(folder)
    install = existing_modloader_install(folder, variables.get("MODLOADER", ""))
    installer = find_modloader_installer(folder, variables.get("MODLOADER", ""))

    source = ""
    server_type = canonical_modloader(variables.get("MODLOADER", ""))
    minecraft_version = variables.get("MINECRAFT_VERSION", "")
    modloader_version = variables.get("MODLOADER_VERSION", "")
    java_version = variables.get("RECOMMENDED_JAVA_VERSION", "")

    if variables:
        source = "variables.txt"
    if not server_type and manifest.get("server_type"):
        server_type = manifest["server_type"]
        source = source or "manifest.json"
    if not minecraft_version and manifest.get("minecraft_version"):
        minecraft_version = manifest["minecraft_version"]
        source = source or "manifest.json"
    if not modloader_version and manifest.get("modloader_version"):
        modloader_version = manifest["modloader_version"]
        source = source or "manifest.json"

    if install:
        server_type = server_type or install[0]
        modloader_version = modloader_version or install[2]
        if not minecraft_version:
            minecraft_version = minecraft_version_from_modloader_full_version(install[1])
        source = source or "libraries"
    if installer:
        server_type = server_type or modloader_from_installer(installer)
        modloader_version = modloader_version or modloader_version_from_installer(installer)
        if not minecraft_version:
            minecraft_version = minecraft_version_from_modloader_full_version(full_version_from_installer(installer) or "")
        source = source or installer.name

    detected_file_type, detected_file_version, detected_jar = _detect_modloader_from_files(folder)
    server_type = server_type or detected_file_type
    modloader_version = modloader_version or detected_file_version
    source = source or (tr("fichiers serveur") if detected_file_type else "")

    server_type = server_type if server_type in SUPPORTED_MODLOADERS else ("Forge" if looks_like_modded_server(folder) else "Custom")
    minecraft_version = minecraft_version or "custom"
    java_version = normalize_java_version(java_version, minecraft_version)
    jar_file = "start-script" if find_start_script(folder) else detected_jar
    if not jar_file and server_type in {"Forge", "NeoForge"}:
        jar_file = "forge-run"
    if not jar_file:
        jar_files = [jar for jar in sorted(folder.glob("*.jar")) if not jar.name.endswith("-installer.jar")]
        jar_file = jar_files[0].name if jar_files else ""

    return ServerImportAnalysis(
        folder=folder,
        server_type=server_type,
        minecraft_version=minecraft_version,
        modloader_version=modloader_version,
        java_version=java_version,
        jar_file=jar_file,
        source=source or tr("dossier"),
    )


def _read_pack_manifest(folder: Path) -> dict[str, str]:
    for name in ("manifest.json", "modrinth.index.json"):
        path = folder / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        if name == "manifest.json":
            return _read_curseforge_manifest(data)
        return _read_modrinth_manifest(data)
    return {}


def _read_curseforge_manifest(data: dict) -> dict[str, str]:
    minecraft = data.get("minecraft") or {}
    version = str(minecraft.get("version") or "")
    loaders = minecraft.get("modLoaders") or []
    preferred = next((loader for loader in loaders if loader.get("primary")), loaders[0] if loaders else {})
    server_type, modloader_version = _modloader_from_manifest_id(str(preferred.get("id") or ""))
    return {
        "minecraft_version": version,
        "server_type": server_type,
        "modloader_version": modloader_version,
    }


def _read_modrinth_manifest(data: dict) -> dict[str, str]:
    dependencies = data.get("dependencies") or {}
    candidates = [
        ("neoforge", "NeoForge"),
        ("forge", "Forge"),
        ("fabric-loader", "Fabric"),
        ("quilt-loader", "Quilt"),
    ]
    server_type = ""
    modloader_version = ""
    for key, value in candidates:
        if dependencies.get(key):
            server_type = value
            modloader_version = str(dependencies.get(key) or "")
            break
    return {
        "minecraft_version": str(dependencies.get("minecraft") or ""),
        "server_type": server_type,
        "modloader_version": modloader_version,
    }


def _modloader_from_manifest_id(identifier: str) -> tuple[str, str]:
    normalized = identifier.lower()
    mappings = [
        ("neoforge", "NeoForge"),
        ("forge", "Forge"),
        ("fabric", "Fabric"),
        ("quilt", "Quilt"),
        ("legacyfabric", "LegacyFabric"),
    ]
    for prefix, server_type in mappings:
        if normalized.startswith(prefix):
            return server_type, identifier.split("-", 1)[1] if "-" in identifier else ""
    return "", ""


def _detect_modloader_from_files(folder: Path) -> tuple[str, str, str]:
    if (folder / "fabric-server-launch.jar").exists():
        return "Fabric", _detect_fabric_loader_version(folder), "fabric-server-launch.jar"
    if (folder / "fabric-server-launcher.jar").exists():
        return "Fabric", _detect_fabric_loader_version(folder), "fabric-server-launcher.jar"
    if (folder / "quilt-server-launch.jar").exists():
        return "Quilt", _detect_quilt_loader_version(folder), "quilt-server-launch.jar"
    neo_version = existing_neoforge_version(folder)
    if neo_version:
        return "NeoForge", neo_version, "forge-run"
    forge_full = existing_forge_full_version(folder)
    if forge_full:
        return "Forge", forge_full.split("-", 1)[1] if "-" in forge_full else forge_full, "forge-run"
    return "", "", ""


def _detect_fabric_loader_version(folder: Path) -> str:
    base = folder / "libraries" / "net" / "fabricmc" / "fabric-loader"
    if not base.exists():
        return ""
    versions = sorted(child.name for child in base.iterdir() if child.is_dir())
    return versions[-1] if versions else ""


def _detect_quilt_loader_version(folder: Path) -> str:
    base = folder / "libraries" / "org" / "quiltmc" / "quilt-loader"
    if not base.exists():
        return ""
    versions = sorted(child.name for child in base.iterdir() if child.is_dir())
    return versions[-1] if versions else ""


def _safe_port(value: Optional[str], default: int = 25565) -> int:
    """Parse a server-port value from a possibly hand-edited/foreign server.properties."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def configure_imported_server(folder: Path) -> tuple[ServerProfile, list[str]]:
    props = read_properties(folder / "server.properties")
    notes: list[str] = []
    variables = read_serverpack_variables(folder)
    analysis = analyze_server_folder(folder)

    if analysis.is_modded or looks_like_modded_server(folder):
        install = existing_modloader_install(folder, analysis.server_type)
        forge_full = install[1] if install else ""
        full_from_variables = _full_version_from_parts(analysis.minecraft_version, analysis.modloader_version)
        ram_min, ram_max = _ram_from_java_args(variables.get("JAVA_ARGS", ""))
        profile = ServerProfile(
            name=folder.name,
            folder=str(folder),
            version=analysis.minecraft_version,
            port=_safe_port(props.get("server-port")),
            ram_min_gb=ram_min,
            ram_max_gb=ram_max,
            server_type=analysis.server_type,
            jar_file=analysis.jar_file,
            forge_full_version=forge_full or full_from_variables,
            forge_version=analysis.modloader_version or ((forge_full or "").split("-", 1)[1] if forge_full and "-" in forge_full else ""),
            java_version=analysis.java_version,
            properties=props,
        )
        if analysis.jar_file == "start-script" or analysis.server_type in {"Forge", "NeoForge"}:
            notes.extend(create_forge_server(profile, download=False))
        else:
            profile.properties["server-port"] = str(profile.port)
            write_properties(folder / "server.properties", profile.properties)
            if not profile.eula_path.exists():
                profile.eula_path.write_text("eula=false\n", encoding="utf-8")
            notes.append(tr("{summary} détecté depuis {source}.").format(summary=analysis.summary(), source=analysis.source))
        return profile, notes

    jar_files = [jar for jar in sorted(folder.glob("*.jar")) if not jar.name.endswith("-installer.jar")]
    if not jar_files:
        raise RuntimeError(tr("Aucun fichier serveur .jar utilisable trouvé. Les installateurs Forge ne sont pas lancés comme serveur."))
    profile = ServerProfile(
        name=folder.name,
        folder=str(folder),
        version="custom",
        port=_safe_port(props.get("server-port")),
        ram_min_gb=2,
        ram_max_gb=4,
        server_type="Custom",
        jar_file=jar_files[0].name,
        properties=props,
    )
    return profile, notes


def find_start_script(folder: Path) -> Optional[Path]:
    windows_names = (
        "start.bat",
        "start.cmd",
        "startserver.bat",
        "startserver.cmd",
        "run.bat",
        "run.cmd",
        "start.ps1",
        "run.ps1",
    )
    unix_names = ("start.sh", "startserver.sh", "run.sh")
    names = windows_names + unix_names if sys.platform.startswith("win") else unix_names + windows_names
    for name in names:
        script = folder / name
        if script.exists():
            return script
    return None


def read_serverpack_variables(folder: Path) -> dict[str, str]:
    path = folder / "variables.txt"
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def configure_start_script_server(profile: ServerProfile) -> None:
    folder = profile.folder_path
    script = find_start_script(folder)
    if not script:
        return
    if os.name != "nt":
        script.chmod(script.stat().st_mode | 0o111)
    variables = read_serverpack_variables(folder)
    if variables.get("MINECRAFT_VERSION"):
        profile.version = variables["MINECRAFT_VERSION"]
    if variables.get("MODLOADER"):
        modloader = canonical_modloader(variables["MODLOADER"])
        if is_modded_type(modloader):
            profile.server_type = modloader
    if variables.get("MODLOADER_VERSION"):
        profile.forge_version = variables["MODLOADER_VERSION"]
        profile.forge_full_version = f"{profile.version}-{profile.forge_version}"
    profile.java_version = normalize_java_version(variables.get("RECOMMENDED_JAVA_VERSION", ""), profile.version)
    profile.jar_file = "start-script"
    java_command = _java_command_for_start_script(profile, variables)
    updates = {
        "JAVA": java_command,
        "JAVA_ARGS": f"-Xmx{profile.ram_max_gb}G -Xms{profile.ram_min_gb}G",
        "WAIT_FOR_USER_INPUT": "false",
        "RESTART": "false",
        "SKIP_JAVA_CHECK": "false",
        "RECOMMENDED_JAVA_VERSION": profile.java_version,
        "SERVERSTARTERJAR_FORCE_FETCH": "false",
    }
    if profile.server_type == "Forge":
        updates["USE_SSJ"] = "false"
    _update_serverpack_variables(
        folder / "variables.txt",
        updates,
    )


def _java_command_for_start_script(profile: ServerProfile, variables: dict[str, str]) -> str:
    if profile.java_path:
        return profile.java_path
    try:
        return find_java(profile.java_version)
    except JavaNotFoundError:
        if (profile.folder_path / "install_java.sh").exists() and variables.get("JDK_VENDOR"):
            return "java"
        raise


def _ram_from_java_args(java_args: str) -> tuple[int, int]:
    ram_min = 2
    ram_max = 4
    for flag, amount, unit in re.findall(r"-Xm([sx])(\d+)([gGmM])", java_args or ""):
        gb = int(amount)
        if unit.lower() == "m":
            gb = max(1, round(gb / 1024))
        if flag == "s":
            ram_min = gb
        elif flag == "x":
            ram_max = gb
    if ram_min > ram_max:
        ram_min = ram_max
    return ram_min, ram_max


def _update_serverpack_variables(path: Path, updates: dict[str, str]) -> None:
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    seen = set()
    output = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key, _ = stripped.split("=", 1)
        key = key.strip()
        if key in updates:
            value = updates[key]
            if key in {"JAVA", "JAVA_ARGS"}:
                value = f'"{value}"'
            output.append(f"{key}={value}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            if key in {"JAVA", "JAVA_ARGS"}:
                value = f'"{value}"'
            output.append(f"{key}={value}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
