from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path
from typing import Dict, List


MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FORGE_PROMOTIONS_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
FORGE_MAVEN_BASE = "https://maven.minecraftforge.net/net/minecraftforge/forge"


class DownloadError(RuntimeError):
    pass


class VanillaDownloader:
    def fetch_manifest(self) -> Dict:
        with urllib.request.urlopen(MANIFEST_URL, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def versions(self) -> List[str]:
        manifest = self.fetch_manifest()
        return [item["id"] for item in manifest.get("versions", []) if item.get("type") == "release"]

    def download_server(self, version: str, destination: Path) -> None:
        manifest = self.fetch_manifest()
        match = next((item for item in manifest.get("versions", []) if item.get("id") == version), None)
        if not match:
            raise DownloadError(f"Version Minecraft introuvable: {version}")

        with urllib.request.urlopen(match["url"], timeout=20) as response:
            version_meta = json.loads(response.read().decode("utf-8"))
        server_info = version_meta.get("downloads", {}).get("server")
        if not server_info or not server_info.get("url"):
            raise DownloadError(f"Aucun server.jar officiel disponible pour {version}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(server_info["url"], timeout=60) as response, destination.open("wb") as fh:
            shutil.copyfileobj(response, fh)


class ForgeDownloader:
    def fetch_promotions(self) -> Dict:
        with urllib.request.urlopen(FORGE_PROMOTIONS_URL, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def resolve_full_version(self, minecraft_version: str, forge_version: str = "") -> str:
        requested = forge_version.strip()
        if requested and requested not in {"latest", "recommended"}:
            if requested.startswith(f"{minecraft_version}-"):
                return requested
            return f"{minecraft_version}-{requested}"

        channel = requested or "recommended"
        promotions = self.fetch_promotions().get("promos", {})
        forge_build = promotions.get(f"{minecraft_version}-{channel}")
        if not forge_build and channel == "recommended":
            forge_build = promotions.get(f"{minecraft_version}-latest")
        if not forge_build:
            raise DownloadError(f"Aucune version Forge {channel} trouvée pour Minecraft {minecraft_version}")
        return f"{minecraft_version}-{forge_build}"

    def installer_url(self, full_version: str) -> str:
        return f"{FORGE_MAVEN_BASE}/{full_version}/forge-{full_version}-installer.jar"

    def download_installer(self, full_version: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(self.installer_url(full_version), timeout=60) as response, destination.open("wb") as fh:
            shutil.copyfileobj(response, fh)
