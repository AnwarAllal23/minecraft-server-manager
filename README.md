# Minecraft Server Manager

A cross-platform desktop application (Python + PySide6) for managing multiple local Minecraft Java servers from a single, responsive UI - Vanilla, Forge, NeoForge, Fabric and Quilt, including CurseForge/Modrinth modpack imports.

Current version: **1.0.1** - see [CHANGELOG.md](CHANGELOG.md) for release history.

## Why this project

Running modded Minecraft servers locally usually means juggling terminal windows, manually editing `server.properties`, hunting down the right Java version, and resolving duplicate-mod crashes by hand. This app wraps all of that in a single native desktop tool:

- No external services or accounts required - everything runs and is stored locally.
- The Java process is fully managed by the app: no separate console window ever opens, all output is streamed into the UI.
- The UI stays responsive even while a heavily modded server (hundreds of mods) is starting up.

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

## Getting Started

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python run.py
```

## Building

```bash
./scripts/build_macos.sh      # macOS, produces dist/Gestion Serveurs Minecraft.app
scripts\build_windows.bat      # Windows, produces dist/Gestion Serveurs Minecraft.exe
```

PyInstaller does not cross-compile, so the Windows build must be run on Windows and the macOS build must be run on macOS.

## Local Data

All application data stays on the local machine:

| Data | Location |
| --- | --- |
| Server profiles | macOS: `~/Library/Application Support/GestionServeursMinecraft/profiles.json`<br>Windows: `%APPDATA%\GestionServeursMinecraft\profiles.json` |
| Managed JDKs | macOS: `~/Library/Application Support/GestionServeursMinecraft/java/`<br>Windows: `%APPDATA%\GestionServeursMinecraft\java\` |
| Server files | The folder chosen by the user when creating/importing a server |

The application does not expose a web interface and does not transmit IP addresses, local paths or RCON credentials to any third party.


## License

This project is licensed under the [MIT License](LICENSE).
