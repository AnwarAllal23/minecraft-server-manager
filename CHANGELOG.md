# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-07-01

### Added
- Multi-language interface: English, French and Spanish, selectable from Settings → Language. English is now the default language for new installs. Applying a new language requires restarting the app.

### Fixed
- A corrupted or truncated `profiles.json` no longer prevents the app from starting; the bad file is quarantined instead of being silently overwritten. Profile saving is now atomic (write to a temp file, then replace) so a crash mid-save can't corrupt it in the first place.
- Loading a `profiles.json` with a field unknown to this version of the app (e.g. from a newer release) no longer crashes.
- Server names with characters invalid in file names (`: / * ? " < > |`) no longer fail to create a backup.
- A `server.properties` value containing a newline is no longer written as a raw line break that corrupts the file; property keys/values with stray surrounding whitespace are now parsed correctly instead of creating silent duplicate keys.
- Importing an existing server folder whose `server.properties` has an invalid `server-port` no longer crashes; it falls back to 25565.
- Typing a non-numeric value into `server-port`, `max-players`, `view-distance` or `simulation-distance` in the properties editor is now rejected with a warning instead of corrupting the profile or crashing the dashboard on every refresh.
- Restoring a backup or changing the Minecraft version while the server is still running is now blocked with a warning, matching the existing protection on server deletion; a failed restore (e.g. a locked file) now shows an error instead of crashing.
- Closing the app while a server is still running now offers to stop it cleanly (or cancel) instead of terminating the Java process uncontrolled.
- A server name of `.` or `..` no longer resolves to the current/parent directory when picking its folder.
- Windows: Java version-detection calls and the Forge/NeoForge installer no longer briefly flash a console window.
- Windows: server console output (player names, MOTD, log lines) is no longer at risk of encoding corruption on non-English locales with Java versions older than 18; the JVM is now forced to UTF-8 I/O.

## [1.0.3] - 2026-06-13

### Added
- New "Ports ouverts" tab listing all UPnP port mappings on the router, with a button to delete a single port and a button to delete all open ports at once.

### Fixed
- The "Ports ouverts" tab now also checks each server profile's port individually, since some routers (e.g. Freebox) report an empty list via the generic UPnP enumeration even when port mappings exist.

## [1.0.2] - 2026-06-13

### Fixed
- New Vanilla server profiles now use the Java version required by the selected Minecraft version (e.g. Java 21 for 1.20.5+) instead of always defaulting to Java 17, which caused an `UnsupportedClassVersionError` on startup.
- Vanilla and Forge downloads now send a `User-Agent` header, fixing `HTTP Error 403: Forbidden` responses from Mojang/Forge CDNs during server creation.

## [1.0.1] - 2026-06-13

### Added
- Windows-aware managed Java discovery via `JAVA_HOME`, version-specific `JAVA_HOME_*`, common Eclipse Adoptium/Java install folders, and `java.exe` on `PATH`.
- Windows server-pack script support for `.bat`, `.cmd`, and `.ps1` start scripts.
- Platform-specific application data folders: `%APPDATA%\GestionServeursMinecraft` on Windows, `~/Library/Application Support/GestionServeursMinecraft` on macOS, and XDG data folders on Linux.

### Changed
- Temurin downloads now select the correct operating system and archive type automatically (`.zip` on Windows, `.tar.gz` on macOS/Linux).
- Server launch environments now use the platform-specific `PATH` separator and set `JAVA_HOME` consistently for the resolved runtime.
- Imported server-pack detection now recognizes Windows start scripts as valid server-pack markers.
- UI labels and warnings now refer to the current machine (`ce PC`, `ce Mac`, or `cette machine`) instead of always saying Mac.
- Backup-folder opening now uses the native platform command (`os.startfile` on Windows, `open` on macOS, `xdg-open` elsewhere).
- README data-location documentation now lists both macOS and Windows storage paths.

### Fixed
- Windows builds no longer try to download the macOS Temurin package when Java is missing.
- Windows server launches no longer prepend Java to `PATH` using the macOS/Linux `:` separator.
- Windows packs with `.bat`, `.cmd`, or `.ps1` launch scripts are no longer missed in favor of Unix-only script handling.

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
