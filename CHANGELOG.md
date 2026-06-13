# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-06-13

### Added
- Server profile management: create, import, duplicate, rename and delete.
- Support for Vanilla, Forge, NeoForge, Fabric and Quilt server types.
- Automatic download of official Vanilla server jars and Forge installers.
- Modpack import (`.zip` server packs and `.mrpack` Modrinth packs), including automatic detection of modloader, Minecraft version and required Java version.
- Support for ServerPackCreator-style packs (`start.sh` / `variables.txt`) with automatic Java/JVM argument configuration.
- Managed Java runtime: automatic detection of installed JDKs and optional download of Eclipse Temurin when a required version is missing.
- Fully in-app process management: the Java/Minecraft server never opens its own console window, with headless JVM mode and managed `PATH`/`JAVA_HOME`.
- Background duplicate-mod detection and automatic resolution (moved to `mods_disabled_duplicates/`), run on import and before every server start.
- Live console with log-level filters, save/copy/clear, command input with autocompletion, and automatic handling of known interactive prompts.
- Player tracking (connected / previously seen / banned) with avatars and moderation actions (`op`, `deop`, `kick`, `ban`, `pardon`, whitelist).
- Desktop notifications for player join/leave events.
- Real-time dashboard: RAM, CPU, player count, folder size and disk usage, with history charts.
- In-app `server.properties` editor with safety warnings for `online-mode`/`white-list`.
- Manual backup creation and restoration.
- LAN/public IP detection and optional UPnP port mapping.
- Light, dark and system-following themes.
- Custom application icon and packaging for macOS (`.app` via PyInstaller) and Windows (`.exe` via PyInstaller).

### Fixed
- Vanilla → Forge server type switch no longer launches the wrong jar.
- UI no longer freezes while a heavily modded server is starting: folder-size scans and duplicate-mod scans run on background threads, oversized log lines are truncated, and console/player-list redraws are batched.
- JVM crash on macOS caused by Forge's `run.sh` resolving an incompatible system Java instead of the app-managed runtime.
