# Minecraft Server Manager

A cross-platform desktop application (Python + PySide6) for managing multiple local Minecraft Java servers from a single, responsive UI — Vanilla, Forge, NeoForge, Fabric and Quilt, including CurseForge/Modrinth modpack imports.

Current version: **1.0.0** — see [CHANGELOG.md](CHANGELOG.md) for release history.

## Why this project

Running modded Minecraft servers locally usually means juggling terminal windows, manually editing `server.properties`, hunting down the right Java version, and resolving duplicate-mod crashes by hand. This app wraps all of that in a single native desktop tool:

- No external services or accounts required — everything runs and is stored locally.
- The Java process is fully managed by the app: no separate console window ever opens, all output is streamed into the UI.
- The UI stays responsive even while a heavily modded server (hundreds of mods) is starting up.

## Features

### Server management
- Create, import, duplicate, rename and delete server profiles.
- Multiple server types per profile: Vanilla, Forge, NeoForge, Fabric, Quilt.
- Start, graceful stop (`stop` command), restart and force-kill.
- Live status indicator for running servers in the sidebar.
- Port-conflict detection before launch (both between local profiles and other processes on the machine).

### Server creation & import
- Automatic download of the official Mojang `server.jar` for the selected Vanilla version.
- Automatic download of the official Forge installer via the Forge Maven repository.
- Optional modpack import (`.zip` server pack or `.mrpack` Modrinth pack) during server creation.
- Automatic analysis of imported server packs: detects modloader (Forge/NeoForge/Fabric/Quilt/LegacyFabric), Minecraft version, modloader version and required Java version.
- Support for ServerPackCreator-style packs (`start.sh` + `variables.txt`), with automatic configuration of `JAVA`, `JAVA_ARGS`, `WAIT_FOR_USER_INPUT`, `RESTART`, and Java version correction when a pack declares an invalid value.
- Automatic flattening of archives that wrap the server pack in a single root folder.

### Java runtime management
- Detects installed JDKs and picks the correct major version for the target Minecraft version (Java 17 for 1.18–1.20.4, Java 21 for 1.20.5+).
- Optional automatic download of Eclipse Temurin JDKs into the app's local data directory when the required version is missing.
- The launched Java process never opens its own console/dock icon — `PATH`, `JAVA_HOME` and headless mode are configured per-launch so everything stays inside the app.

### Mod conflict detection
- Background scan for duplicate mod jars (same `modId` declared by multiple files).
- Automatically disables the older duplicate by moving it to `mods_disabled_duplicates/` instead of deleting it.
- Runs both at import time and before every server start, without blocking the UI.

### Console & live monitoring
- Live console with `INFO` / `WARN` / `ERROR` filters, copy, save and clear actions.
- Direct command input with Minecraft command autocompletion.
- Automatic answers to known interactive prompts (e.g. `Yes`/`I agree`) so unattended scripts don't hang.
- Oversized single log lines (some mods dump huge config blobs) are truncated before being rendered, to keep the console responsive.
- Console rendering and player-list refreshes are batched (max one redraw per 150 ms) so a burst of log lines never freezes the UI.

### Players
- Player join/leave detection parsed from server logs.
- Separate tabs for connected players, previously seen players and banned players.
- Player head avatars fetched from Minecraft usernames (configurable, no IP/port data sent).
- Right-click actions: `op`, `deop`, `kick`, `ban`, `pardon`, whitelist management.
- Desktop notifications on player join/leave.

### Dashboard & monitoring
- Real-time RAM and CPU usage, player count, server folder size and free disk space.
- RAM and disk usage history charts.
- Folder size is computed in a background thread (recursive disk scans never block the UI).
- Low-RAM / low-disk warnings, throttled to avoid repeated alerts.
- RAM requirement check against available system memory at import time.

### Configuration
- In-app `server.properties` editor with native-style switches for boolean options.
- Adjustable JVM heap size (`-Xms` / `-Xmx`).
- Warnings when `online-mode=false` or `white-list=false` are set.
- Light / dark / system theme.

### Backups
- Manual backup creation, restoration with confirmation, and quick access to the backups folder.

### Networking
- Local LAN IP and public IP detection.
- Optional UPnP port mapping to expose the server beyond the local network.

## Architecture

```
minecraft_manager/
├── app.py            Application entry point, window icon, global stylesheet
├── ui.py             Main window, dialogs, background workers (QThread)
├── models.py         ServerProfile data model, app data directory resolution
├── profiles.py       Profile persistence (JSON store)
├── setup.py          Server creation/import logic, modloader detection
├── modpacks.py       Modpack/server-pack archive extraction
├── mods.py           Duplicate mod detection and resolution
├── server_process.py QProcess wrapper that launches and supervises the server
├── java_runtime.py   JDK discovery and managed Temurin downloads
├── downloader.py     Vanilla/Forge artifact downloaders
├── monitoring.py     RAM/CPU/disk metrics
├── players.py        Player join/leave log parsing
├── networking.py     LAN/public IP, UPnP port mapping
├── backups.py        Backup creation/restoration
├── properties.py     server.properties read/write helpers
├── charts.py         Lightweight RAM/disk usage chart widget
├── settings.py       Application settings persistence
└── style.py          Light/dark/system Qt stylesheets
```

The UI thread is kept free of blocking I/O: folder-size scans, duplicate-mod scans, modpack imports, Java downloads and avatar downloads all run on dedicated `QThread` workers and report back to the main window via Qt signals.

## Requirements

- Python 3.9+
- A Java runtime matching your server's Minecraft version (the app can download one automatically if missing):
  - Java 17 for Minecraft 1.18 – 1.20.4
  - Java 21 for Minecraft 1.20.5+
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

### macOS (.app)

```bash
./scripts/build_macos.sh
```

Produces `dist/Gestion Serveurs Minecraft.app`, ad-hoc code-signed so it can be opened directly from Finder.

### Windows (.exe)

PyInstaller does not cross-compile, so the Windows build must be run **on Windows**:

```bat
scripts\build_windows.bat
```

Produces `dist/Gestion Serveurs Minecraft/Gestion Serveurs Minecraft.exe`.

### App icon

The app icon (`assets/AppIcon.icns`, `assets/AppIcon.ico`, `assets/app_icon.png`) is generated procedurally from `scripts/generate_icon.py`:

```bash
python3 scripts/generate_icon.py
```

## Local data

All application data stays on the local machine:

| Data | Location |
| --- | --- |
| Server profiles | `~/Library/Application Support/GestionServeursMinecraft/profiles.json` |
| Managed JDKs | `~/Library/Application Support/GestionServeursMinecraft/java/` |
| Server files | The folder chosen by the user when creating/importing a server |

The application does not expose a web interface and does not transmit IP addresses, local paths or RCON credentials to any third party.

## Versioning

This project follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`). The current application version is exposed as `minecraft_manager.__version__` and shown in the window title. All notable changes are tracked in [CHANGELOG.md](CHANGELOG.md).

## License

This project is licensed under the [MIT License](LICENSE).
