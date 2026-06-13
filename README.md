# Minecraft Server Manager

A cross-platform desktop application (Python + PySide6) for managing multiple local Minecraft Java servers from a single, responsive UI — Vanilla, Forge, NeoForge, Fabric and Quilt, including CurseForge/Modrinth modpack imports.

## Features

- Create, import, duplicate, rename and delete server profiles (Vanilla, Forge, NeoForge, Fabric, Quilt).
- Start, stop, restart and monitor servers without ever opening a separate console window.
- Automatic download of Vanilla/Forge server files, and import of `.zip`/`.mrpack` modpacks with automatic modloader/Java version detection.
- Managed Java runtime: detects installed JDKs and can download the required version automatically.
- Background detection and resolution of duplicate mods.
- Live console with log filters, command input and autocompletion.
- Player tracking (connected, previously seen, banned) with moderation actions and join/leave notifications.
- Real-time dashboard (RAM, CPU, disk usage) with history charts.
- In-app `server.properties` editor, manual backups, and LAN/UPnP networking tools.
- Light, dark and system themes.

## Requirements

- Python 3.9+
- A Java runtime matching your server's Minecraft version (the app can download one automatically if missing).
- An internet connection to download Vanilla/Forge server files and JDKs.

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python run.py
```

## Building a standalone application

```bash
./scripts/build_macos.sh      # macOS, produces dist/Gestion Serveurs Minecraft.app
scripts\build_windows.bat      # Windows, produces dist/Gestion Serveurs Minecraft/Gestion Serveurs Minecraft.exe
```

## License

This project is licensed under the [MIT License](LICENSE).
