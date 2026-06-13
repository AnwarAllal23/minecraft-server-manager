from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


DEFAULT_PROPERTIES: Dict[str, str] = {
    "server-port": "25565",
    "server-ip": "",
    "online-mode": "true",
    "white-list": "false",
    "max-players": "20",
    "difficulty": "easy",
    "gamemode": "survival",
    "pvp": "true",
    "view-distance": "10",
    "simulation-distance": "10",
    "motd": "Serveur Minecraft",
    "enable-command-block": "false",
    "allow-flight": "false",
    "hardcore": "false",
    "level-name": "world",
    "enable-rcon": "false",
    "rcon.password": "",
    "enforce-secure-profile": "true",
    "prevent-proxy-connections": "false",
}


@dataclass
class PlayerSession:
    pseudo: str
    ip: str
    remote_port: str
    connected_at: str
    disconnected_at: str = ""
    status: str = "connecte"


@dataclass
class ServerProfile:
    name: str
    folder: str
    version: str
    port: int
    ram_min_gb: int
    ram_max_gb: int
    server_type: str = "Vanilla"
    jar_file: str = "server.jar"
    forge_version: str = ""
    forge_full_version: str = ""
    modpack_path: str = ""
    java_version: str = "17"
    java_path: str = ""
    properties: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PROPERTIES))
    players: List[Dict[str, Any]] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def folder_path(self) -> Path:
        return Path(self.folder).expanduser()

    @property
    def jar_path(self) -> Path:
        return self.folder_path / self.jar_file

    @property
    def eula_path(self) -> Path:
        return self.folder_path / "eula.txt"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerProfile":
        merged = dict(DEFAULT_PROPERTIES)
        merged.update(data.get("properties") or {})
        data = dict(data)
        data["properties"] = merged
        return cls(**data)


def app_data_dir() -> Path:
    base = Path.home() / "Library" / "Application Support" / "GestionServeursMinecraft"
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return base
    except (OSError, PermissionError):
        fallback = Path.cwd() / ".app_data"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
