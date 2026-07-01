from __future__ import annotations

import socket
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from .i18n import tr
from .java_runtime import JavaNotFoundError, find_java
from .models import ServerProfile
from .setup import find_start_script, is_modded_type


class ServerRunner(QObject):
    log_line = Signal(str)
    state_changed = Signal(str)
    # Emitted with the required Java major version (e.g. "17") when the
    # server cannot start because no matching Java runtime was found. The UI
    # listens for this to offer downloading Temurin automatically instead of
    # just printing an error in the console.
    java_missing = Signal(str)

    def __init__(self, profile: ServerProfile) -> None:
        super().__init__()
        self.profile = profile
        self.process: Optional[QProcess] = None
        self._answered_prompts: set[str] = set()

    @property
    def running(self) -> bool:
        return bool(self.process and self.process.state() != QProcess.NotRunning)

    @property
    def pid(self) -> Optional[int]:
        return int(self.process.processId()) if self.running and self.process else None

    def start(self) -> None:
        if self.running:
            return
        try:
            java = self.profile.java_path or find_java(self.profile.java_version)
            program, args = self._build_command(java)
        except JavaNotFoundError as exc:
            self.log_line.emit(str(exc))
            self.log_line.emit(tr("Installe Java {version}, puis relance le serveur.").format(version=self.profile.java_version))
            self.state_changed.emit("erreur")
            self.java_missing.emit(self.profile.java_version)
            return
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(self.profile.folder_path))
        self.process.setProgram(program)
        self.process.setArguments(args)
        # Forge/NeoForge start scripts (run.sh) call plain "java" themselves,
        # ignoring the Java we just resolved. Prepend that Java's bin
        # directory to PATH so the script picks up the same (correct)
        # runtime instead of whatever "java" the system PATH points to -
        # using the wrong major version here can crash the JVM outright.
        java_bin_dir = str(Path(java).resolve().parent)
        env = QProcessEnvironment.systemEnvironment()
        existing_path = env.value("PATH")
        env.insert("PATH", f"{java_bin_dir}{os.pathsep}{existing_path}" if existing_path else java_bin_dir)
        env.insert("JAVA_HOME", str(Path(java_bin_dir).parent))
        # Force headless mode so the JVM never opens its own window, dock
        # icon or "Minecraft server" console on macOS - everything must stay
        # inside this app. JAVA_TOOL_OPTIONS is honored by the "java" binary
        # no matter how it's invoked, including from run.sh start scripts.
        existing_tool_options = env.value("JAVA_TOOL_OPTIONS")
        # Also force UTF-8 I/O: on Java releases older than 18 (still
        # supported here for Minecraft <=1.16), the JVM's default encoding
        # follows the OS locale, which on non-English Windows is a legacy
        # code page - accented player names/MOTD/log lines would otherwise
        # come out corrupted since the console below always decodes as UTF-8.
        headless_flag = "-Djava.awt.headless=true -Dfile.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8"
        env.insert(
            "JAVA_TOOL_OPTIONS",
            f"{existing_tool_options} {headless_flag}" if existing_tool_options else headless_flag,
        )
        self.process.setProcessEnvironment(env)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.errorOccurred.connect(lambda error: self.log_line.emit(tr("Erreur de lancement Java: {error}").format(error=error)))
        self.process.started.connect(lambda: self.state_changed.emit("demarre"))
        self.process.finished.connect(lambda *_: self.state_changed.emit("arrete"))
        self.process.start()

    def can_launch(self) -> bool:
        if self._start_script_path():
            return True
        if is_modded_type(self.profile.server_type):
            return bool(self._modloader_unix_args_path() or self._modloader_server_jar())
        return self.profile.jar_path.exists()

    def _build_command(self, java: str) -> tuple[str, list[str]]:
        start_script = self._start_script_path()
        if start_script:
            suffix = start_script.suffix.lower()
            if sys.platform.startswith("win"):
                if suffix in {".bat", ".cmd"}:
                    return "cmd.exe", ["/c", start_script.name]
                if suffix == ".ps1":
                    return "powershell.exe", ["-ExecutionPolicy", "Bypass", "-File", start_script.name]
                bash = shutil.which("bash")
                if bash:
                    return bash, [start_script.name]
            return "/bin/bash", [start_script.name]
        return java, self._build_args()

    def _build_args(self) -> list[str]:
        base = [f"-Xms{self.profile.ram_min_gb}G", f"-Xmx{self.profile.ram_max_gb}G"]
        if is_modded_type(self.profile.server_type):
            start_script = self._start_script_path()
            if start_script:
                return [start_script.name]
            unix_args = self._modloader_unix_args_path()
            if unix_args:
                return base + [f"@{unix_args}", "nogui"]
            modloader_jar = self._modloader_server_jar()
            if modloader_jar:
                return base + ["-jar", modloader_jar.name, "nogui"]
        return base + ["-jar", self.profile.jar_file, "nogui"]

    def _start_script_path(self) -> Optional[Path]:
        script = find_start_script(self.profile.folder_path)
        if not script:
            return None
        if sys.platform.startswith("win") and script.suffix.lower() == ".sh" and not shutil.which("bash"):
            return None
        if self.profile.jar_file == "start-script" or script:
            return script
        return None

    def _modloader_unix_args_path(self) -> Optional[str]:
        folder = self.profile.folder_path
        candidates = []
        forge_base = folder / "libraries" / "net" / "minecraftforge" / "forge"
        neoforge_base = folder / "libraries" / "net" / "neoforged" / "neoforge"
        if self.profile.forge_full_version:
            candidates.append(forge_base / self.profile.forge_full_version / "unix_args.txt")
        if self.profile.forge_version:
            candidates.append(neoforge_base / self.profile.forge_version / "unix_args.txt")
        candidates.extend(sorted(forge_base.glob("*/unix_args.txt")))
        candidates.extend(sorted(neoforge_base.glob("*/unix_args.txt")))
        for candidate in candidates:
            if candidate.exists():
                return str(candidate.relative_to(folder))
        return None

    def _modloader_server_jar(self) -> Optional[Path]:
        folder = self.profile.folder_path
        if (
            self.profile.jar_file
            and self.profile.jar_file != "forge-run"
            and self.profile.jar_file != "start-script"
            and not self.profile.jar_file.endswith("-installer.jar")
            and (folder / self.profile.jar_file).exists()
        ):
            return folder / self.profile.jar_file
        jars = [jar for jar in sorted(folder.glob("forge-*.jar")) if not jar.name.endswith("-installer.jar")]
        jars.extend(jar for jar in sorted(folder.glob("neoforge-*.jar")) if not jar.name.endswith("-installer.jar"))
        jars.extend(jar for jar in [folder / "fabric-server-launch.jar", folder / "fabric-server-launcher.jar", folder / "quilt-server-launch.jar", folder / "server.jar"] if jar.exists())
        return jars[0] if jars else None

    def send_command(self, command: str) -> None:
        if not self.running or not self.process:
            return
        self.process.write((command.strip() + "\n").encode("utf-8"))

    def stop(self) -> None:
        if self.running:
            self.send_command("stop")

    def kill(self) -> None:
        if self.running and self.process:
            self.process.kill()

    def _read_output(self) -> None:
        if not self.process:
            return
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._answer_known_prompts(text)
        for line in text.splitlines():
            self.log_line.emit(line)

    def _answer_known_prompts(self, text: str) -> None:
        if not self.process:
            return
        if "Are you sure you want to continue? (Yes/No):" in text and "path-spaces" not in self._answered_prompts:
            self.process.write(b"Yes\n")
            self._answered_prompts.add("path-spaces")
            self.log_line.emit(tr("Chemin avec espaces confirmé automatiquement pour le script du pack."))
        if "Type 'I agree'" in text and "jabba-consent" not in self._answered_prompts:
            self.process.write(b"I agree\n")
            self._answered_prompts.add("jabba-consent")
            self.log_line.emit(tr("Installation Java automatique du pack autorisée."))


def port_is_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) != 0
