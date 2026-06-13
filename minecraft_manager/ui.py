from __future__ import annotations

import re
import shutil
import subprocess
import time
import urllib.request
import json
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from PySide6.QtCore import QRectF, QSize, QThread, QTimer, Signal, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QIcon, QPainter, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .backups import backup_files, backups_dir, create_backup, restore_backup
from .charts import MetricChart
from .downloader import VanillaDownloader
from .java_runtime import JavaNotFoundError, download_java, find_java, managed_java_root
from .models import DEFAULT_PROPERTIES, ServerProfile, app_data_dir
from . import __version__
from .monitoring import ProcessMonitor, folder_size, available_memory_gb
from .mods import disable_duplicate_mods, find_duplicate_mods, format_duplicate_mods
from .networking import PortMappingResult, local_lan_ip, open_minecraft_port
from .players import PlayerTracker
from .profiles import ProfileStore
from .properties import read_properties, write_properties
from .server_process import ServerRunner, port_is_free
from .settings import SettingsStore
from .style import style_for_mode
from .setup import (
    analyze_server_folder,
    configure_imported_server,
    configure_start_script_server,
    create_forge_server,
    create_server,
    existing_modloader_install,
    find_modloader_installer,
    find_start_script,
    full_version_from_installer,
    is_modded_type,
    looks_like_modded_server,
    minecraft_version_from_forge_full_version,
    modloader_from_installer,
    modloader_version_from_installer,
    normalize_java_version,
    read_serverpack_variables,
    required_java_for_minecraft,
    canonical_modloader,
)


# Some mods print single log lines that are hundreds of KB long (e.g. huge
# config dumps). Lines longer than this are truncated before being stored
# and rendered, to avoid freezing the console widget.
MAX_LOG_LINE_LENGTH = 4000

COMMON_VERSIONS = ["1.21.6", "1.21.5", "1.21.4", "1.21.1", "1.21", "1.20.6", "1.20.4", "1.20.1"]

COMMAND_SUGGESTIONS = [
    "/help",
    "/list",
    "/stop",
    "/save-all",
    "/save-on",
    "/save-off",
    "/say ",
    "/msg ",
    "/tell ",
    "/op ",
    "/deop ",
    "/kick ",
    "/ban ",
    "/ban-ip ",
    "/pardon ",
    "/pardon-ip ",
    "/whitelist on",
    "/whitelist off",
    "/whitelist list",
    "/whitelist add ",
    "/whitelist remove ",
    "/gamemode survival ",
    "/gamemode creative ",
    "/gamemode adventure ",
    "/gamemode spectator ",
    "/difficulty peaceful",
    "/difficulty easy",
    "/difficulty normal",
    "/difficulty hard",
    "/time set day",
    "/time set night",
    "/weather clear",
    "/weather rain",
    "/weather thunder",
    "/tp ",
    "/give ",
    "/effect give ",
    "/xp add ",
    "/seed",
    "/reload",
    "/datapack list",
    "/gamerule ",
]

BOOL_PROPERTY_LABELS = {
    "online-mode": "Mode en ligne",
    "white-list": "Whitelist",
    "pvp": "PvP",
    "enable-command-block": "Blocs de commande",
    "allow-flight": "Vol autorisé",
    "hardcore": "Hardcore",
    "enable-rcon": "RCON",
    "enforce-secure-profile": "Profils sécurisés",
    "prevent-proxy-connections": "Anti-proxy",
}

ADVANCED_PROPERTY_KEYS = [key for key in DEFAULT_PROPERTIES if key not in BOOL_PROPERTY_LABELS]


def machine_label() -> str:
    if sys.platform == "darwin":
        return "ce Mac"
    if os.name == "nt":
        return "ce PC"
    return "cette machine"


def open_folder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


class ToggleSwitch(QCheckBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setText("")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        checked = self.isChecked()
        track = QRectF(1, 1, 44, 24)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#34c759" if checked else "#c7c7cc"))
        painter.drawRoundedRect(track, 12, 12)
        knob_x = 22 if checked else 3
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(knob_x, 3, 20, 20))
        painter.end()


class ServerCreateWorker(QThread):
    finished_ok = Signal(ServerProfile, str)
    failed = Signal(str)

    def __init__(self, profile: ServerProfile) -> None:
        super().__init__()
        self.profile = profile

    def run(self) -> None:
        try:
            notes = create_server(self.profile, download=True)
            self.finished_ok.emit(self.profile, "\n".join(notes))
        except Exception as exc:
            self.failed.emit(str(exc))


class ServerImportWorker(QThread):
    finished_ok = Signal(ServerProfile, str)
    failed = Signal(str)

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self.folder = folder

    def run(self) -> None:
        try:
            profile, notes = configure_imported_server(self.folder)
            self.finished_ok.emit(profile, "\n".join(notes))
        except Exception as exc:
            self.failed.emit(str(exc))


class JavaDownloadWorker(QThread):
    finished_ok = Signal(str, str)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, version: str) -> None:
        super().__init__()
        self.version = version

    def run(self) -> None:
        try:
            path = download_java(self.version, lambda done, total: self.progress.emit(done, total))
            self.finished_ok.emit(self.version, path)
        except Exception as exc:
            self.failed.emit(str(exc))


class ServerPrepareWorker(QThread):
    finished_ok = Signal(ServerProfile, str)
    failed = Signal(str)

    def __init__(self, profile: ServerProfile) -> None:
        super().__init__()
        self.profile = profile

    def run(self) -> None:
        try:
            notes = create_forge_server(self.profile, download=False)
            self.finished_ok.emit(self.profile, "\n".join(notes))
        except Exception as exc:
            self.failed.emit(str(exc))


class PortMappingWorker(QThread):
    finished_ok = Signal(str, object)

    def __init__(self, profile: ServerProfile) -> None:
        super().__init__()
        self.profile_id = profile.id
        self.port = profile.port
        self.description = f"Minecraft - {profile.name}"

    def run(self) -> None:
        try:
            result = open_minecraft_port(self.port, self.description)
        except Exception as exc:
            result = PortMappingResult(
                ok=False,
                message=f"Verification reseau impossible: {exc}",
                local_ip="",
                connect_address="",
            )
        self.finished_ok.emit(self.profile_id, result)


class VersionWorker(QThread):
    finished_versions = Signal(list)

    def run(self) -> None:
        try:
            self.finished_versions.emit(VanillaDownloader().versions()[:40])
        except Exception:
            self.finished_versions.emit(COMMON_VERSIONS)


class FolderSizeWorker(QThread):
    """Walks a server folder off the UI thread to measure its size.

    Servers with many mods, libraries and world saves can contain tens of
    thousands of files: computing the total size with os.walk synchronously
    on every dashboard tick would freeze the whole app, especially right
    after launch when the OS is busy extracting/writing those same files.
    """

    finished_size = Signal(str, float)

    def __init__(self, profile_id: str, folder: Path) -> None:
        super().__init__()
        self.profile_id = profile_id
        self.folder = folder

    def run(self) -> None:
        try:
            size_mb = folder_size(self.folder) / (1024**2)
        except OSError:
            size_mb = 0.0
        self.finished_size.emit(self.profile_id, size_mb)


class DuplicateModsWorker(QThread):
    """Scans the mods folder for duplicate modIds off the UI thread.

    Opening every mod jar to read its metadata can take several seconds for
    a modpack with hundreds of mods, which would otherwise freeze the app
    right when the user clicks "Démarrer".
    """

    finished_ok = Signal(str, list)
    duplicates_remaining = Signal(str, str)
    failed = Signal(str, str)

    def __init__(self, profile_id: str, folder: Path) -> None:
        super().__init__()
        self.profile_id = profile_id
        self.folder = folder

    def run(self) -> None:
        duplicates = find_duplicate_mods(self.folder)
        if not duplicates:
            self.finished_ok.emit(self.profile_id, [])
            return
        try:
            moved = disable_duplicate_mods(self.folder)
        except Exception as exc:
            self.failed.emit(self.profile_id, str(exc))
            return
        remaining = find_duplicate_mods(self.folder)
        if remaining:
            self.duplicates_remaining.emit(self.profile_id, format_duplicate_mods(remaining))
            return
        self.finished_ok.emit(self.profile_id, [path.name for path in moved])


class AvatarWorker(QThread):
    loaded = Signal(str, str)
    failed = Signal(str)

    def __init__(self, pseudo: str, cache_dir: Path) -> None:
        super().__init__()
        self.pseudo = pseudo
        self.cache_dir = cache_dir

    def run(self) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            target = self.cache_dir / f"{self.pseudo.lower()}.png"
            if not target.exists():
                url = f"https://mc-heads.net/avatar/{self.pseudo}/64.png"
                with urllib.request.urlopen(url, timeout=12) as response:
                    data = response.read()
                if not data:
                    raise RuntimeError("avatar empty")
                target.write_bytes(data)
            self.loaded.emit(self.pseudo, str(target))
        except Exception:
            self.failed.emit(self.pseudo)


def slugify_server_name(name: str) -> str:
    """Turn a server name into a filesystem-friendly folder name.

    Strips characters that are invalid in common desktop paths (``/``, ``:``...) and
    collapses repeated whitespace, while keeping the result readable.
    """
    cleaned = re.sub(r'[\\/:*?"<>|]+', "", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Serveur Minecraft"


def unique_server_folder(base_dir: Path, name: str, taken: set) -> Path:
    """Pick a free folder under ``base_dir`` for a server named ``name``.

    Every server profile must live in its own folder: two profiles sharing
    a folder would mix their jars/libraries/mods together and confuse the
    modloader auto-detection in setup.py (a Vanilla server could end up
    looking like a leftover Forge install, for example). If the natural
    folder name is already used by another profile or already exists on
    disk, a numeric suffix " (2)", " (3)"... is appended until free.
    """
    slug = slugify_server_name(name)
    candidate = base_dir / slug
    counter = 2
    while candidate in taken or candidate.exists():
        candidate = base_dir / f"{slug} ({counter})"
        counter += 1
    return candidate


class NewServerDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, existing_profiles: Optional[List[ServerProfile]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nouveau serveur")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)

        # Folders already used by other profiles, so the auto-generated
        # folder for this new server never collides with an existing one.
        self._taken_folders = {Path(p.folder).expanduser() for p in (existing_profiles or [])}
        self._folder_is_auto = True

        form = QFormLayout()
        self.name = QLineEdit("Serveur Minecraft")
        self.folder = QLineEdit()
        browse = QPushButton("Choisir")
        browse.clicked.connect(self.choose_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder)
        folder_row.addWidget(browse)

        self.server_type = QComboBox()
        self.server_type.addItems(["Vanilla", "Paper", "Fabric", "Forge", "Custom"])
        self.server_type.currentTextChanged.connect(self._type_changed)
        self.version = QComboBox()
        self.version.setEditable(True)
        self.version.addItems(COMMON_VERSIONS)
        self.forge_version = QLineEdit("recommended")
        self.forge_version.setPlaceholderText("recommended, latest ou ex: 47.4.20")
        self.modpack = QLineEdit()
        self.modpack.setPlaceholderText("Optionnel: pack serveur .zip ou .mrpack")
        modpack_browse = QPushButton("Importer")
        modpack_browse.clicked.connect(self.choose_modpack)
        self.modpack_row = QHBoxLayout()
        self.modpack_row.addWidget(self.modpack)
        self.modpack_row.addWidget(modpack_browse)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(25565)
        self.ram_min = QSpinBox()
        self.ram_min.setRange(1, 128)
        self.ram_min.setValue(2)
        self.ram_max = QSpinBox()
        self.ram_max.setRange(1, 128)
        self.ram_max.setValue(4)
        self.info = QLabel(f"RAM disponible sur {machine_label()}: {available_memory_gb():.1f} Go")

        form.addRow("Nom", self.name)
        form.addRow("Dossier", folder_row)
        form.addRow("Type", self.server_type)
        form.addRow("Version Minecraft", self.version)
        self.forge_label = QLabel("Version Forge")
        form.addRow(self.forge_label, self.forge_version)
        self.modpack_label = QLabel("Modpack")
        form.addRow(self.modpack_label, self.modpack_row)
        form.addRow("Port", self.port)
        form.addRow("RAM minimale (Go)", self.ram_min)
        form.addRow("RAM maximale (Go)", self.ram_max)
        layout.addLayout(form)
        layout.addWidget(self.info)

        buttons = QHBoxLayout()
        cancel = QPushButton("Annuler")
        create = QPushButton("Créer")
        cancel.clicked.connect(self.reject)
        create.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(create)
        layout.addLayout(buttons)

        self._type_changed(self.server_type.currentText())

        # Auto-fill the folder from the server name as long as the user
        # hasn't picked/edited it manually (each server gets its own folder).
        self.name.textChanged.connect(self._sync_folder_with_name)
        self.folder.textEdited.connect(self._mark_folder_manual)
        self._sync_folder_with_name(self.name.text())

    def _mark_folder_manual(self, _text: str) -> None:
        self._folder_is_auto = False

    def _sync_folder_with_name(self, name: str) -> None:
        if not self._folder_is_auto:
            return
        base_dir = Path.home() / "MinecraftServers"
        folder = unique_server_folder(base_dir, name, self._taken_folders)
        self.folder.blockSignals(True)
        self.folder.setText(str(folder))
        self.folder.blockSignals(False)

    def _set_versions(self, versions: List[str]) -> None:
        current = self.version.currentText()
        self.version.clear()
        self.version.addItems(versions or COMMON_VERSIONS)
        if current:
            self.version.setCurrentText(current)

    def _type_changed(self, value: str) -> None:
        is_forge = value == "Forge"
        self.forge_label.setVisible(is_forge)
        self.forge_version.setVisible(is_forge)
        self.modpack_label.setVisible(is_forge)
        self.modpack.setVisible(is_forge)
        for index in range(self.modpack_row.count()):
            widget = self.modpack_row.itemAt(index).widget()
            if widget:
                widget.setVisible(is_forge)
        if value not in {"Vanilla", "Forge"}:
            QMessageBox.information(self, "Type pas encore disponible", "Cette version crée des serveurs Vanilla et Forge. Paper/Fabric/Custom arrivent ensuite.")
            self.server_type.setCurrentText("Vanilla")

    def choose_modpack(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importer un modpack",
            str(Path.home()),
            "Modpacks (*.zip *.mrpack);;Archives (*.zip);;Tous les fichiers (*)",
        )
        if path:
            self.modpack.setText(path)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choisir le dossier du serveur", str(Path.home()))
        if folder:
            self._folder_is_auto = False
            self.folder.setText(folder)

    def accept(self) -> None:
        if self.ram_min.value() > self.ram_max.value():
            QMessageBox.warning(self, "RAM invalide", "La RAM minimale ne peut pas être supérieure à la RAM maximale.")
            return
        if not self.name.text().strip():
            QMessageBox.warning(self, "Nom manquant", "Choisis un nom pour le serveur.")
            return
        folder = Path(self.folder.text().strip()).expanduser()
        if folder in self._taken_folders:
            QMessageBox.warning(
                self,
                "Dossier déjà utilisé",
                "Un autre serveur de la liste utilise déjà ce dossier.\n\n"
                "Chaque serveur doit avoir son propre dossier, sinon leurs fichiers "
                "(jar, mods, librairies) se mélangent et le type du serveur peut être "
                "mal détecté au prochain démarrage.",
            )
            return
        super().accept()

    def profile(self) -> ServerProfile:
        props = dict(DEFAULT_PROPERTIES)
        props["server-port"] = str(self.port.value())
        version = self.version.currentText().strip()
        return ServerProfile(
            name=self.name.text().strip(),
            folder=self.folder.text().strip(),
            version=version,
            port=self.port.value(),
            ram_min_gb=self.ram_min.value(),
            ram_max_gb=self.ram_max.value(),
            server_type=self.server_type.currentText(),
            forge_version=self.forge_version.text().strip() if self.server_type.currentText() == "Forge" else "",
            modpack_path=self.modpack.text().strip() if self.server_type.currentText() == "Forge" else "",
            properties=props,
            java_version=required_java_for_minecraft(version),
        )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Gestion Serveurs Minecraft v{__version__}")
        self.store = ProfileStore()
        self.settings = SettingsStore()
        self.runners: Dict[str, ServerRunner] = {}
        self.trackers: Dict[str, PlayerTracker] = {}
        self.logs: Dict[str, List[str]] = {}
        self.avatar_cache: Dict[str, QIcon] = {}
        self.avatar_workers: Dict[str, AvatarWorker] = {}
        self.avatar_cache_dir = app_data_dir() / "avatar_cache"
        self.monitor = ProcessMonitor()
        self.current_profile: Optional[ServerProfile] = None
        self.worker: Optional[ServerCreateWorker] = None
        self.import_worker: Optional[ServerImportWorker] = None
        self.java_worker: Optional[JavaDownloadWorker] = None
        self.pending_import_folder: Optional[Path] = None
        # Callback run once a JavaDownloadWorker finishes successfully. Lets a
        # single download flow serve different callers (import a server pack,
        # retry starting a server that was missing its Java runtime, ...).
        self.pending_java_action: Optional[Callable[[], None]] = None
        self.prepare_worker: Optional[ServerPrepareWorker] = None
        self.port_workers: Dict[str, PortMappingWorker] = {}
        self.network_results: Dict[str, PortMappingResult] = {}
        # Tracks which profiles already triggered a "RAM presque pleine" /
        # "disque presque plein" notification, so we warn once per episode
        # instead of on every dashboard refresh (every 1.5s).
        self._ram_warned: set[str] = set()
        self._disk_warned: set[str] = set()
        # Folder size (mods, world, libraries...) is measured in a background
        # thread because os.walk over a big modded server can take seconds.
        # We cache the last known value per profile and refresh it
        # periodically instead of on every 1.5s dashboard tick.
        self._folder_size_cache: Dict[str, float] = {}
        self._folder_size_workers: Dict[str, FolderSizeWorker] = {}
        self._folder_size_last_started: Dict[str, float] = {}
        self.duplicate_mods_workers: Dict[str, DuplicateModsWorker] = {}
        self._pending_import_messages: Dict[str, str] = {}
        # Modded servers can spam hundreds of log lines per second while
        # loading. Re-rendering the console/players tables on every single
        # line would freeze the UI, so refreshes are coalesced into one
        # repaint every 150ms via this timer.
        self._log_render_timer = QTimer(self)
        self._log_render_timer.setSingleShot(True)
        self._log_render_timer.timeout.connect(self._flush_log_render)

        self._build_ui()
        self._build_menu()
        self._build_tray_icon()
        self.refresh_server_list()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_dashboard)
        self.timer.start(1500)

    def _build_menu(self) -> None:
        action = QAction("Quitter", self)
        action.triggered.connect(QApplication.quit)
        self.menuBar().addMenu("Application").addAction(action)

    def _build_tray_icon(self) -> None:
        """Create the desktop notification icon used by notify().

        Reuses a standard Qt icon so the app doesn't need to ship/bundle a
        dedicated asset just for notifications.
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return
        self.tray_icon = QSystemTrayIcon(self.style().standardIcon(QStyle.SP_ComputerIcon), self)
        self.tray_icon.setToolTip("Gestion Serveurs Minecraft")
        self.tray_icon.show()

    def notify(self, title: str, message: str, icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.Information) -> None:
        """Show a desktop notification, unless the user disabled them.

        Falls back to the status bar if the system tray isn't available.
        Used for player join/leave, low RAM/disk warnings and server start
        errors (e.g. missing Java).
        """
        if not self.settings.get_bool("notifications_enabled"):
            return
        if self.tray_icon is not None:
            self.tray_icon.showMessage(title, message, icon, 6000)
        else:
            self.statusBar().showMessage(f"{title} - {message}", 6000)

    def _build_ui(self) -> None:
        root = QSplitter()
        self.setCentralWidget(root)

        left = QWidget()
        left.setObjectName("Sidebar")
        left_layout = QVBoxLayout(left)
        title = QLabel("Mes serveurs")
        title.setObjectName("SidebarTitle")
        left_layout.addWidget(title)
        self.server_list = QListWidget()
        self.server_list.currentItemChanged.connect(self._selected_server_changed)
        left_layout.addWidget(self.server_list)

        new_btn = QPushButton("+ Nouveau serveur")
        new_btn.setObjectName("PrimaryButton")
        import_btn = QPushButton("Importer")
        duplicate_btn = QPushButton("Dupliquer")
        rename_btn = QPushButton("Renommer")
        delete_btn = QPushButton("Supprimer")
        new_btn.clicked.connect(self.new_server)
        import_btn.clicked.connect(self.import_server)
        duplicate_btn.clicked.connect(self.duplicate_server)
        rename_btn.clicked.connect(self.rename_server)
        delete_btn.clicked.connect(self.delete_server)
        left_layout.addWidget(new_btn)
        for button in [import_btn, duplicate_btn, rename_btn, delete_btn]:
            button.setObjectName("SidebarButton")
            left_layout.addWidget(button)
        root.addWidget(left)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._dashboard_tab(), "Dashboard")
        self.tabs.addTab(self._console_tab(), "Console")
        self.tabs.addTab(self._players_tab(), "Joueurs")
        self.tabs.addTab(self._properties_tab(), "Paramètres serveur")
        self.tabs.addTab(self._versions_tab(), "Versions Minecraft")
        self.tabs.addTab(self._backups_tab(), "Backups")
        self.tabs.addTab(self._storage_tab(), "Stockage")
        self.tabs.addTab(self._app_settings_tab(), "Paramètres application")
        root.addWidget(self.tabs)
        root.setSizes([280, 980])

    def _dashboard_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        self.server_title = QLabel("Aucun serveur sélectionné")
        self.server_title.setObjectName("PageTitle")
        self.status_label = QLabel("Statut: arrete")
        layout.addWidget(self.server_title)

        actions = QHBoxLayout()
        self.start_btn = QPushButton("Démarrer")
        self.start_btn.setObjectName("PrimaryButton")
        self.stop_btn = QPushButton("Arrêter proprement")
        self.restart_btn = QPushButton("Redémarrer")
        self.kill_btn = QPushButton("Forcer l’arrêt")
        self.kill_btn.setObjectName("DangerButton")
        self.start_btn.clicked.connect(self.toggle_server)
        self.stop_btn.clicked.connect(self.stop_server)
        self.restart_btn.clicked.connect(self.restart_server)
        self.kill_btn.clicked.connect(self.kill_server)
        actions.addWidget(self.status_label)
        actions.addStretch()
        for button in [self.start_btn, self.stop_btn, self.restart_btn, self.kill_btn]:
            actions.addWidget(button)
        layout.addLayout(actions)

        metrics = QFrame()
        metrics.setObjectName("Surface")
        grid = QGridLayout(metrics)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        self.ram_bar = QProgressBar()
        self.cpu_bar = QProgressBar()
        self.players_bar = QProgressBar()
        self.folder_label = QLabel("Taille dossier: -")
        self.disk_label = QLabel("Disque libre: -")
        self.ram_alloc_label = QLabel("Allocation RAM: -")
        grid.addWidget(QLabel("RAM utilisée"), 0, 0)
        grid.addWidget(self.ram_bar, 0, 1)
        grid.addWidget(QLabel("CPU utilisé"), 1, 0)
        grid.addWidget(self.cpu_bar, 1, 1)
        grid.addWidget(QLabel("Joueurs connectés"), 2, 0)
        grid.addWidget(self.players_bar, 2, 1)
        grid.addWidget(self.ram_alloc_label, 0, 2)
        grid.addWidget(self.folder_label, 1, 2)
        grid.addWidget(self.disk_label, 2, 2)
        layout.addWidget(metrics)

        network = QFrame()
        network.setObjectName("Surface")
        network_layout = QGridLayout(network)
        network_layout.setContentsMargins(16, 14, 16, 14)
        network_layout.setHorizontalSpacing(14)
        network_layout.setVerticalSpacing(8)
        self.connect_address_label = QLabel("Adresse joueurs: -")
        self.local_address_label = QLabel("Adresse locale: -")
        self.port_status_label = QLabel("Port routeur: non vérifié")
        self.copy_address_btn = QPushButton("Copier l'adresse")
        self.refresh_network_btn = QPushButton("Ouvrir/vérifier le port")
        self.copy_address_btn.clicked.connect(self.copy_connect_address)
        self.refresh_network_btn.clicked.connect(self.ensure_selected_port_mapping)
        network_layout.addWidget(self.connect_address_label, 0, 0)
        network_layout.addWidget(self.local_address_label, 1, 0)
        network_layout.addWidget(self.port_status_label, 2, 0)
        network_layout.addWidget(self.copy_address_btn, 0, 1)
        network_layout.addWidget(self.refresh_network_btn, 1, 1)
        layout.addWidget(network)

        charts = QSplitter(Qt.Horizontal)
        self.ram_chart = MetricChart("Graphique RAM serveur", "#0a84ff", " Mo")
        self.cpu_chart = MetricChart("Graphique CPU serveur", "#ff9f0a", "%")
        self.disk_chart = MetricChart("Graphique disque serveur", "#30d158", " Mo")
        charts.addWidget(self.ram_chart)
        charts.addWidget(self.cpu_chart)
        charts.addWidget(self.disk_chart)
        charts.setSizes([1, 1, 1])
        layout.addWidget(charts)

        console_panel = self._console_panel("dashboard")
        layout.addWidget(console_panel, 1)
        return page

    def _console_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(self._console_panel("main"))
        return page

    def _console_panel(self, name: str) -> QWidget:
        page = QFrame()
        page.setObjectName("Surface")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        header = QHBoxLayout()
        console_title = QLabel("Console serveur")
        console_title.setObjectName("PanelTitle")
        header.addWidget(console_title)
        header.addStretch()
        layout.addLayout(header)
        tools = QHBoxLayout()
        log_filter = QComboBox()
        log_filter.addItems(["TOUT", "INFO", "WARN", "ERROR"])
        log_filter.currentTextChanged.connect(self.render_logs)
        copy_btn = QPushButton("Copier les logs")
        save_btn = QPushButton("Sauvegarder les logs")
        clear_btn = QPushButton("Vider l’affichage")
        copy_btn.clicked.connect(self.copy_logs)
        save_btn.clicked.connect(self.save_logs)
        clear_btn.clicked.connect(self.clear_logs)
        tools.addWidget(QLabel("Filtre"))
        tools.addWidget(log_filter)
        tools.addStretch()
        for button in [copy_btn, save_btn, clear_btn]:
            tools.addWidget(button)
        layout.addLayout(tools)
        console = QTextEdit()
        console.setReadOnly(True)
        layout.addWidget(console)
        command_row = QHBoxLayout()
        command_input = QLineEdit()
        command_input.setPlaceholderText("Commande serveur, ex: /list")
        command_input.setCompleter(self._command_completer())
        command_input.returnPressed.connect(lambda inp=command_input: self.send_command_from(inp))
        send = QPushButton("Envoyer")
        send.setObjectName("PrimaryButton")
        send.clicked.connect(lambda _=False, inp=command_input: self.send_command_from(inp))
        command_row.addWidget(command_input)
        command_row.addWidget(send)
        layout.addLayout(command_row)
        if name == "dashboard":
            self.dashboard_log_filter = log_filter
            self.dashboard_console = console
            self.dashboard_command_input = command_input
        else:
            self.log_filter = log_filter
            self.console = console
            self.command_input = command_input
        return page

    def _command_completer(self) -> QCompleter:
        completer = QCompleter(COMMAND_SUGGESTIONS, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchStartsWith)
        return completer

    def _players_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        self.players_tabs = QTabWidget()
        self.connected_players_table = self._player_table(["Tête", "Pseudo", "IP", "Port distant", "Connexion", "Statut"])
        self.seen_players_table = self._player_table(["Tête", "Pseudo", "IP", "Port distant", "Première connexion", "Dernière sortie", "Statut"])
        self.banned_players_table = self._player_table(["Pseudo", "UUID", "Date", "Source", "Expire", "Raison"], avatars=False)
        self.players_tabs.addTab(self.connected_players_table, "Connectés")
        self.players_tabs.addTab(self.seen_players_table, "Déjà connectés")
        self.players_tabs.addTab(self.banned_players_table, "Bannis")
        layout.addWidget(self.players_tabs)
        return page

    def _player_table(self, labels: List[str], avatars: bool = True) -> QTableWidget:
        table = QTableWidget(0, len(labels))
        table.setHorizontalHeaderLabels(labels)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if avatars:
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
            table.setColumnWidth(0, 54)
            table.setIconSize(QSize(34, 34))
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos, current=table: self.player_context_menu(current, pos))
        return table

    def _properties_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        ram_box = QFrame()
        ram_box.setObjectName("Surface")
        ram_layout = QFormLayout(ram_box)
        self.ram_min_setting = QSpinBox()
        self.ram_min_setting.setRange(1, 128)
        self.ram_max_setting = QSpinBox()
        self.ram_max_setting.setRange(1, 128)
        self.ram_available_label = QLabel(f"RAM disponible sur {machine_label()}: {available_memory_gb():.1f} Go")
        save_ram = QPushButton("Enregistrer la RAM")
        save_ram.clicked.connect(self.save_ram_settings)
        ram_layout.addRow("RAM minimale (-Xms)", self.ram_min_setting)
        ram_layout.addRow("RAM maximale (-Xmx)", self.ram_max_setting)
        ram_layout.addRow("", self.ram_available_label)
        ram_layout.addRow("", save_ram)
        layout.addWidget(ram_box)

        switches_box = QFrame()
        switches_box.setObjectName("Surface")
        switches_layout = QGridLayout(switches_box)
        switches_layout.setContentsMargins(16, 14, 16, 14)
        switches_layout.setHorizontalSpacing(24)
        switches_layout.setVerticalSpacing(12)
        self.property_switches: Dict[str, ToggleSwitch] = {}
        for index, (key, label) in enumerate(BOOL_PROPERTY_LABELS.items()):
            row = index // 3
            column = (index % 3) * 2
            name = QLabel(label)
            name.setObjectName("PanelTitle")
            toggle = ToggleSwitch()
            self.property_switches[key] = toggle
            switches_layout.addWidget(name, row, column)
            switches_layout.addWidget(toggle, row, column + 1, Qt.AlignRight)
        layout.addWidget(switches_box)

        self.security_warning = QLabel("")
        self.security_warning.setObjectName("WarningLabel")
        layout.addWidget(self.security_warning)
        self.properties_table = QTableWidget(0, 2)
        self.properties_table.setHorizontalHeaderLabels(["Paramètre avancé", "Valeur"])
        self.properties_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.properties_table)
        save = QPushButton("Enregistrer server.properties")
        save.clicked.connect(self.save_properties)
        layout.addWidget(save)
        return page

    def _versions_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.current_version_label = QLabel("-")
        self.new_version = QComboBox()
        self.new_version.setEditable(True)
        self.new_version.addItems(COMMON_VERSIONS)
        change = QPushButton("Changer de version avec backup")
        change.clicked.connect(self.change_version)
        layout.addRow("Version actuelle", self.current_version_label)
        layout.addRow("Nouvelle version", self.new_version)
        layout.addRow("", change)
        return page

    def _backups_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        manual = QPushButton("Créer un backup manuel")
        restore = QPushButton("Restaurer le backup sélectionné")
        open_dir = QPushButton("Ouvrir le dossier backups")
        manual.clicked.connect(self.create_manual_backup)
        restore.clicked.connect(self.restore_selected_backup)
        open_dir.clicked.connect(self.open_backups_folder)
        for button in [manual, restore, open_dir]:
            row.addWidget(button)
        layout.addLayout(row)
        self.backups_list = QListWidget()
        layout.addWidget(self.backups_list)
        return page

    def _storage_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.storage_label = QLabel("Sélectionne un serveur pour voir le stockage.")
        layout.addWidget(self.storage_label)
        layout.addStretch()
        return page

    def _app_settings_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        self.data_dir_label = QLabel(str(app_data_dir()))
        local = QCheckBox("Interface locale uniquement")
        local.setChecked(True)
        local.setEnabled(False)
        self.theme_mode = QComboBox()
        self.theme_mode.addItem("Automatique système", "auto")
        self.theme_mode.addItem("Clair", "light")
        self.theme_mode.addItem("Sombre", "dark")
        current_theme = self.settings.get_str("theme_mode")
        index = self.theme_mode.findData(current_theme)
        self.theme_mode.setCurrentIndex(index if index >= 0 else 0)
        self.theme_mode.currentIndexChanged.connect(self.save_app_settings)
        self.download_heads_checkbox = QCheckBox("Télécharger les têtes Minecraft depuis les pseudos")
        self.download_heads_checkbox.setChecked(self.settings.get_bool("download_player_heads"))
        self.download_heads_checkbox.setToolTip("Envoie uniquement le pseudo au service d’avatar public, jamais l’IP ni le port du joueur.")
        self.download_heads_checkbox.stateChanged.connect(self.save_app_settings)
        self.notifications_checkbox = QCheckBox("Notifications (connexions/déconnexions, RAM, disque, erreurs)")
        self.notifications_checkbox.setChecked(self.settings.get_bool("notifications_enabled"))
        self.notifications_checkbox.setToolTip("Affiche une notification système quand un joueur rejoint/quitte ou en cas de problème (RAM, disque, démarrage).")
        self.notifications_checkbox.stateChanged.connect(self.save_app_settings)
        layout.addRow("Données application", self.data_dir_label)
        layout.addRow("Thème", self.theme_mode)
        layout.addRow("Confidentialité", local)
        layout.addRow("Joueurs", self.download_heads_checkbox)
        layout.addRow("Notifications", self.notifications_checkbox)
        return page

    def refresh_server_list(self) -> None:
        current_id = self.current_profile.id if self.current_profile else ""
        self.server_list.clear()
        for profile in self.store.profiles:
            running = self._profile_is_running(profile.id)
            status = "en route" if running else "arrêté"
            item = QListWidgetItem(f"{profile.name}  ·  {profile.port}  ·  {status}")
            item.setData(Qt.UserRole, profile.id)
            item.setForeground(QBrush(QColor("#30d158" if running else "#8e8e93")))
            item.setToolTip(f"{profile.name} est {status}.")
            self.server_list.addItem(item)
            if profile.id == current_id:
                self.server_list.setCurrentItem(item)
        if self.server_list.count() and not self.server_list.currentItem():
            self.server_list.setCurrentRow(0)

    def _profile_is_running(self, profile_id: str) -> bool:
        runner = self.runners.get(profile_id)
        return bool(runner and runner.running)

    def save_app_settings(self, *_args) -> None:
        self.settings.set_bool("download_player_heads", self.download_heads_checkbox.isChecked())
        self.settings.set_bool("notifications_enabled", self.notifications_checkbox.isChecked())
        self.settings.set_str("theme_mode", self.theme_mode.currentData() or "auto")
        app = QApplication.instance()
        if app:
            app.setStyleSheet(style_for_mode(self.settings.get_str("theme_mode")))
        self.refresh_players()

    def _selected_server_changed(self, item: Optional[QListWidgetItem]) -> None:
        self.current_profile = self.store.get(item.data(Qt.UserRole)) if item else None
        self.refresh_current_profile()

    def refresh_current_profile(self) -> None:
        profile = self.current_profile
        if not profile:
            self.server_title.setText("Aucun serveur sélectionné")
            self.connect_address_label.setText("Adresse joueurs: -")
            self.local_address_label.setText("Adresse locale: -")
            self.port_status_label.setText("Port routeur: non vérifié")
            for console_name in ("console", "dashboard_console"):
                console = getattr(self, console_name, None)
                if console:
                    console.clear()
            return
        self.server_title.setText(f"{profile.name} - {profile.server_type} {profile.version}")
        self.current_version_label.setText(profile.version)
        self.ram_min_setting.setValue(profile.ram_min_gb)
        self.ram_max_setting.setValue(profile.ram_max_gb)
        self.ram_available_label.setText(f"RAM disponible sur {machine_label()}: {available_memory_gb():.1f} Go")
        if (profile.folder_path / "server.properties").exists():
            profile.properties = read_properties(profile.folder_path / "server.properties")
        if profile.id not in self.trackers:
            self.trackers[profile.id] = PlayerTracker(profile.players)
        self.render_properties()
        self.render_logs()
        self.refresh_players()
        self.refresh_backups()
        self.refresh_network_labels()
        self.refresh_dashboard()

    def new_server(self) -> None:
        dialog = NewServerDialog(self, self.store.profiles)
        if dialog.exec() != QDialog.Accepted:
            return
        profile = dialog.profile()
        if any(p.port == profile.port for p in self.store.profiles):
            QMessageBox.warning(self, "Port déjà utilisé", "Un profil utilise déjà ce port.")
            return
        self.statusBar().showMessage("Création et téléchargement du server.jar...")
        self.worker = ServerCreateWorker(profile)
        self.worker.finished_ok.connect(self._server_created)
        self.worker.failed.connect(self._server_create_failed)
        self.worker.start()

    def _server_created(self, profile: ServerProfile, notes: str = "") -> None:
        self.store.add(profile)
        self.trackers[profile.id] = PlayerTracker()
        self.logs[profile.id] = []
        self.refresh_server_list()
        self.statusBar().showMessage("Serveur créé. Ouverture du port routeur...")
        self.ensure_port_mapping(profile)
        details = (
            f"Le serveur {profile.server_type} est prêt. L’application tente maintenant d’ouvrir "
            f"le port TCP {profile.port} automatiquement via UPnP."
            "\n\nLe EULA sera demandé explicitement au premier démarrage."
        )
        if notes:
            details += f"\n\n{notes}"
        QMessageBox.information(self, "Serveur créé", details)

    def _server_create_failed(self, message: str) -> None:
        self.statusBar().showMessage("Création échouée.", 5000)
        QMessageBox.critical(self, "Erreur de création", message)

    def import_server(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Importer un serveur existant", str(Path.home()))
        if not folder:
            return
        folder_path = Path(folder)
        if any(Path(p.folder) == folder_path for p in self.store.profiles):
            QMessageBox.warning(self, "Déjà importé", "Ce dossier serveur est déjà dans la liste.")
            return
        try:
            analysis = analyze_server_folder(folder_path)
        except Exception as exc:
            QMessageBox.warning(self, "Analyse du modpack", f"Analyse automatique impossible.\n\n{exc}")
            analysis = None
        if analysis and analysis.is_modded:
            analysis.java_version = normalize_java_version(analysis.java_version, analysis.minecraft_version)
            try:
                find_java(analysis.java_version)
            except JavaNotFoundError:
                if not self._ask_java_download(analysis.summary(), analysis.java_version):
                    self.statusBar().showMessage("Import annulé: Java compatible manquant.", 5000)
                    return
                self.pending_import_folder = folder_path
                self._download_java_then_import(analysis.java_version)
                return
        self._start_import_worker(folder_path)

    def _ask_java_download(self, summary: str, java_version: str) -> bool:
        answer = QMessageBox.question(
            self,
            f"Java {java_version} requis",
            "Analyse du modpack:\n"
            f"{summary}\n\n"
            f"Java {java_version} est introuvable sur {machine_label()}.\n\n"
            "Autorises-tu l’application à télécharger Temurin Java "
            f"{java_version} et à l’installer dans son dossier local ?\n\n"
            f"{managed_java_root()}",
        )
        return answer == QMessageBox.Yes

    def _download_java_then_import(self, java_version: str) -> None:
        folder = self.pending_import_folder
        self._download_java_then(java_version, lambda: self._start_import_worker(folder) if folder else None)

    def _download_java_then(self, java_version: str, on_success: Callable[[], None]) -> None:
        """Start a Temurin download for ``java_version`` and run ``on_success`` once installed.

        The downloaded JDK is stored under managed_java_root() (inside the
        app's own data folder), where find_java() looks first - so the
        caller can simply retry whatever it was doing (import, server
        start...) without needing to know the install path.
        """
        if self.java_worker and self.java_worker.isRunning():
            QMessageBox.information(self, "Téléchargement en cours", "Un téléchargement Java est déjà en cours.")
            return
        self.pending_java_action = on_success
        self.statusBar().showMessage(f"Téléchargement de Java {java_version}...")
        self.java_worker = JavaDownloadWorker(java_version)
        self.java_worker.progress.connect(self._java_download_progress)
        self.java_worker.finished_ok.connect(self._java_downloaded)
        self.java_worker.failed.connect(self._java_download_failed)
        self.java_worker.start()

    def _java_download_progress(self, done: int, total: int) -> None:
        if total:
            percent = int(done * 100 / total)
            self.statusBar().showMessage(f"Téléchargement Java... {percent}%")
        else:
            self.statusBar().showMessage(f"Téléchargement Java... {done // (1024 * 1024)} Mo")

    def _java_downloaded(self, version: str, java_path: str) -> None:
        self.statusBar().showMessage(f"Java {version} installé dans l’application.", 5000)
        self.pending_import_folder = None
        action = self.pending_java_action
        self.pending_java_action = None
        if action:
            action()

    def _java_download_failed(self, message: str) -> None:
        self.pending_import_folder = None
        self.pending_java_action = None
        self.statusBar().showMessage("Téléchargement Java échoué.", 5000)
        QMessageBox.critical(self, "Téléchargement Java impossible", message)

    def _start_import_worker(self, folder: Path) -> None:
        self.statusBar().showMessage("Import du serveur...")
        self.import_worker = ServerImportWorker(folder)
        self.import_worker.finished_ok.connect(self._server_imported)
        self.import_worker.failed.connect(self._server_import_failed)
        self.import_worker.start()

    def _server_imported(self, profile: ServerProfile, notes: str = "") -> None:
        if any(p.folder == profile.folder for p in self.store.profiles):
            QMessageBox.warning(self, "Déjà importé", "Ce dossier serveur est déjà dans la liste.")
            self.statusBar().clearMessage()
            return
        self.store.add(profile)
        self.refresh_server_list()
        self.statusBar().showMessage("Serveur importé. Ouverture du port routeur...")
        self.ensure_port_mapping(profile)
        message = f"{profile.name} a été importé comme serveur {profile.server_type}."
        if notes:
            message += f"\n\n{notes}"
        # Another frequent CurseForge-import crash: the modpack's
        # user_jvm_args.txt asks for more RAM (-Xmx) than this machine actually
        # has available, so the JVM fails to allocate its heap at startup.
        available_gb = available_memory_gb()
        if available_gb and profile.ram_max_gb > available_gb * 0.9:
            message += (
                f"\n\nATTENTION: ce modpack demande {profile.ram_max_gb} Go de RAM, "
                f"mais {machine_label()} n'a que {available_gb:.1f} Go disponibles. "
                "Réduis l'allocation RAM dans « Paramètres serveur » avant de démarrer, "
                "sinon le serveur risque de crasher immédiatement."
            )
        # On a juste vu un crash causé par des mods dupliqués / un Java
        # incompatible détecté seulement au premier démarrage. Pour éviter ce
        # type de mauvaise surprise, on analyse le dossier de mods tout de
        # suite après l'import (en arrière-plan) et on complète le résumé
        # avant de l'afficher.
        if is_modded_type(profile.server_type) or (profile.folder_path / "mods").exists():
            self.statusBar().showMessage("Analyse des mods importés...")
            self._pending_import_messages[profile.id] = message
            worker = DuplicateModsWorker(profile.id, profile.folder_path)
            self.duplicate_mods_workers[profile.id] = worker
            worker.finished_ok.connect(self._import_duplicate_mods_checked)
            worker.duplicates_remaining.connect(self._import_duplicate_mods_conflict)
            worker.failed.connect(self._import_duplicate_mods_failed)
            worker.start()
            return
        QMessageBox.information(self, "Serveur importé", message)

    def _import_duplicate_mods_checked(self, profile_id: str, moved_names: List[str]) -> None:
        self.duplicate_mods_workers.pop(profile_id, None)
        message = self._pending_import_messages.pop(profile_id, "")
        if moved_names:
            message += (
                "\n\nMods dupliqués désactivés automatiquement (déplacés dans "
                "mods_disabled_duplicates):\n" + "\n".join(f"- {name}" for name in moved_names)
            )
        else:
            message += "\n\nAucun mod dupliqué détecté."
        self.statusBar().clearMessage()
        QMessageBox.information(self, "Serveur importé", message)

    def _import_duplicate_mods_conflict(self, profile_id: str, conflict_message: str) -> None:
        self.duplicate_mods_workers.pop(profile_id, None)
        message = self._pending_import_messages.pop(profile_id, "")
        message += (
            "\n\nATTENTION: des mods dupliqués déclarent encore le même modId et "
            "peuvent faire crasher le serveur au démarrage.\n\n" + conflict_message
        )
        self.statusBar().clearMessage()
        QMessageBox.warning(self, "Serveur importé", message)

    def _import_duplicate_mods_failed(self, profile_id: str, error_message: str) -> None:
        self.duplicate_mods_workers.pop(profile_id, None)
        message = self._pending_import_messages.pop(profile_id, "")
        message += f"\n\nAnalyse des mods dupliqués impossible: {error_message}"
        self.statusBar().clearMessage()
        QMessageBox.information(self, "Serveur importé", message)

    def _server_import_failed(self, message: str) -> None:
        self.statusBar().showMessage("Import échoué.", 5000)
        QMessageBox.critical(self, "Import impossible", message)

    def duplicate_server(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        duplicate = ServerProfile.from_dict(profile.to_dict())
        duplicate.id = uuid4().hex
        duplicate.name = f"{profile.name} copie"
        duplicate.folder = str(profile.folder_path.parent / duplicate.name)
        duplicate.port = self._next_free_profile_port(profile.port + 1)
        duplicate.properties["server-port"] = str(duplicate.port)
        shutil.copytree(profile.folder_path, duplicate.folder_path, dirs_exist_ok=True)
        write_properties(duplicate.folder_path / "server.properties", duplicate.properties)
        self.store.add(duplicate)
        self.refresh_server_list()

    def _next_free_profile_port(self, start: int) -> int:
        used = {p.port for p in self.store.profiles}
        port = start
        while port in used and port < 65535:
            port += 1
        return port

    def rename_server(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        text, ok = QInputDialog.getText(self, "Renommer", "Nouveau nom", text=profile.name)
        if ok and text:
            profile.name = text.strip()
            self.store.update(profile)
            self.refresh_server_list()

    def delete_server(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        if self.runner(profile).running:
            QMessageBox.warning(self, "Serveur actif", "Arrête le serveur avant de supprimer son profil.")
            return
        if QMessageBox.question(self, "Supprimer", f"Supprimer ce profil ? Le dossier serveur reste sur {machine_label()}.") == QMessageBox.Yes:
            self.store.remove(profile.id)
            self.current_profile = None
            self.refresh_server_list()

    def runner(self, profile: ServerProfile) -> ServerRunner:
        if profile.id not in self.runners:
            runner = ServerRunner(profile)
            runner.log_line.connect(lambda line, pid=profile.id: self._append_log(pid, line))
            runner.state_changed.connect(lambda state, pid=profile.id: self._state_changed(pid, state))
            runner.java_missing.connect(lambda version, pid=profile.id: self._handle_java_missing(pid, version))
            self.runners[profile.id] = runner
        elif not self.runners[profile.id].running:
            self.runners[profile.id].profile = profile
        return self.runners[profile.id]

    def refresh_network_labels(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        result = self.network_results.get(profile.id)
        if result and result.connect_address:
            self.connect_address_label.setText(f"Adresse joueurs: {result.connect_address}")
        else:
            self.connect_address_label.setText(f"Adresse joueurs: recherche IP publique... port {profile.port}")
        try:
            lan_ip = result.local_ip if result else local_lan_ip()
        except OSError:
            lan_ip = ""
        self.local_address_label.setText(f"Adresse locale: {lan_ip}:{profile.port}" if lan_ip else "Adresse locale: -")
        if result:
            prefix = "ouvert" if result.ok else "à vérifier"
            self.port_status_label.setText(f"Port routeur: {prefix} - {result.message}")
        elif profile.id in self.port_workers:
            self.port_status_label.setText("Port routeur: ouverture automatique en cours...")
        else:
            self.port_status_label.setText("Port routeur: non vérifié")

    def ensure_selected_port_mapping(self) -> None:
        if self.current_profile:
            self.ensure_port_mapping(self.current_profile)

    def ensure_port_mapping(self, profile: ServerProfile) -> None:
        if profile.id in self.port_workers:
            return
        worker = PortMappingWorker(profile)
        worker.finished_ok.connect(self._port_mapping_finished)
        self.port_workers[profile.id] = worker
        if self.current_profile and self.current_profile.id == profile.id:
            self.refresh_network_labels()
        worker.start()

    def _port_mapping_finished(self, profile_id: str, result: PortMappingResult) -> None:
        self.port_workers.pop(profile_id, None)
        self.network_results[profile_id] = result
        profile = self.store.get(profile_id)
        if profile:
            self._append_log(profile_id, f"Réseau: {result.message}")
            if result.connect_address:
                self._append_log(profile_id, f"Adresse à partager: {result.connect_address}")
        if self.current_profile and self.current_profile.id == profile_id:
            self.refresh_network_labels()
            if result.ok:
                self.statusBar().showMessage(f"Port ouvert. Adresse joueurs: {result.connect_address or 'IP publique indisponible'}", 8000)
            else:
                self.statusBar().showMessage("Ouverture automatique du port impossible. Voir Dashboard.", 8000)

    def copy_connect_address(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        result = self.network_results.get(profile.id)
        address = result.connect_address if result else ""
        if not address:
            self.ensure_port_mapping(profile)
            QMessageBox.information(
                self,
                "Adresse indisponible",
                "L’adresse publique n’est pas encore prête. L’application lance la vérification réseau; réessaie dans quelques secondes.",
            )
            return
        QApplication.clipboard().setText(address)
        self.statusBar().showMessage(f"Adresse copiée: {address}", 5000)

    def start_server(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        if self._repair_imported_modded_profile(profile):
            self.store.update(profile)
            self.refresh_current_profile()
        if find_start_script(profile.folder_path):
            try:
                configure_start_script_server(profile)
                self.store.update(profile)
            except Exception as exc:
                QMessageBox.warning(self, "Configuration du script serveur", str(exc))
                return
        if profile.ram_min_gb > profile.ram_max_gb:
            QMessageBox.warning(self, "RAM invalide", "La RAM minimale ne peut pas être supérieure à la RAM maximale.")
            return
        if is_modded_type(profile.server_type) and not self.runner(profile).can_launch() and find_modloader_installer(profile.folder_path, profile.server_type):
            self.statusBar().showMessage(f"Préparation {profile.server_type} du serveur importé...")
            self.prepare_worker = ServerPrepareWorker(profile)
            self.prepare_worker.finished_ok.connect(self._server_prepared_then_start)
            self.prepare_worker.failed.connect(self._server_prepare_failed)
            self.prepare_worker.start()
            return
        if is_modded_type(profile.server_type) or (profile.folder_path / "mods").exists():
            # Scanning every mod jar for duplicate modIds can take seconds
            # with a large modpack, so it runs in a background thread to
            # keep the UI responsive. _continue_start_server resumes once
            # it reports back.
            self.statusBar().showMessage("Vérification des mods...")
            worker = DuplicateModsWorker(profile.id, profile.folder_path)
            self.duplicate_mods_workers[profile.id] = worker
            worker.finished_ok.connect(self._duplicate_mods_checked)
            worker.duplicates_remaining.connect(self._duplicate_mods_conflict)
            worker.failed.connect(self._duplicate_mods_failed)
            worker.start()
            return
        self._continue_start_server(profile)

    def _duplicate_mods_checked(self, profile_id: str, moved_names: List[str]) -> None:
        self.duplicate_mods_workers.pop(profile_id, None)
        if moved_names:
            self._append_log(
                profile_id,
                "Mods dupliqués désactivés automatiquement:\n" + "\n".join(f"- {name}" for name in moved_names),
            )
            self.statusBar().showMessage("Doublons de mods désactivés automatiquement.", 5000)
        profile = self.store.get(profile_id)
        if profile and self.current_profile and self.current_profile.id == profile_id:
            self._continue_start_server(profile)

    def _duplicate_mods_conflict(self, profile_id: str, message: str) -> None:
        self.duplicate_mods_workers.pop(profile_id, None)
        QMessageBox.warning(
            self,
            "Mods dupliqués",
            "Le serveur moddé peut crasher parce que plusieurs fichiers déclarent encore le même modId.\n\n"
            + message
            + "\n\nL’application a essayé de mettre les doublons de côté, mais il reste un conflit à corriger.",
        )

    def _duplicate_mods_failed(self, profile_id: str, message: str) -> None:
        self.duplicate_mods_workers.pop(profile_id, None)
        QMessageBox.warning(self, "Mods dupliqués", f"Impossible de désactiver les doublons automatiquement.\n\n{message}")

    def _continue_start_server(self, profile: ServerProfile) -> None:
        if not self.runner(profile).can_launch():
            QMessageBox.warning(self, "Lancement impossible", "Le fichier de lancement du serveur est introuvable.")
            return
        for other_id, runner in self.runners.items():
            other = self.store.get(other_id)
            if other and other.id != profile.id and other.port == profile.port and runner.running:
                QMessageBox.warning(self, "Port occupé", "Un autre serveur lancé utilise déjà ce port.")
                return
        if not port_is_free(profile.port) and not self.runner(profile).running:
            QMessageBox.warning(self, "Port occupé", f"Le port {profile.port} est déjà utilisé sur {machine_label()}.")
            return
        if not self._ensure_eula(profile):
            return
        write_properties(profile.folder_path / "server.properties", profile.properties)
        self.ensure_port_mapping(profile)
        self.runner(profile).start()

    def _repair_imported_modded_profile(self, profile: ServerProfile) -> bool:
        # This repair pass only makes sense for profiles that are already a
        # modloader (Forge/NeoForge/...) or whose type is unknown ("Custom"),
        # because it re-detects the modloader from files on disk and may
        # rewrite `profile.server_type`. A profile explicitly created as
        # "Vanilla" must never be reclassified, even if its folder happens to
        # contain leftover modloader files (e.g. it was reused from another
        # server folder) - otherwise a Vanilla server could silently turn
        # into a Forge server on the next launch.
        if profile.server_type == "Vanilla":
            return False
        if not looks_like_modded_server(profile.folder_path):
            return False
        variables = read_serverpack_variables(profile.folder_path)
        install = existing_modloader_install(profile.folder_path, variables.get("MODLOADER", profile.server_type))
        installer = find_modloader_installer(profile.folder_path, variables.get("MODLOADER", profile.server_type))
        modloader = canonical_modloader(variables.get("MODLOADER", "")) or (install[0] if install else "")
        if not modloader and installer:
            modloader = modloader_from_installer(installer)
        modloader = modloader or (canonical_modloader(profile.server_type) if is_modded_type(profile.server_type) else "Forge")
        forge_full = install[1] if install else ""
        modloader_version = variables.get("MODLOADER_VERSION", "")
        if not modloader_version and install:
            modloader_version = install[2]
        if not modloader_version and installer:
            modloader_version = modloader_version_from_installer(installer)
        if not forge_full and installer and modloader == "Forge":
            forge_full = full_version_from_installer(installer) or ""
        profile.server_type = modloader
        profile.jar_file = "start-script" if find_start_script(profile.folder_path) else "forge-run"
        if variables.get("MINECRAFT_VERSION"):
            profile.version = variables["MINECRAFT_VERSION"]
        if forge_full:
            profile.forge_full_version = forge_full
            profile.forge_version = forge_full.split("-", 1)[1] if "-" in forge_full else ""
            if "-" in forge_full:
                profile.version = minecraft_version_from_forge_full_version(forge_full)
        if modloader_version:
            profile.forge_version = modloader_version
            if profile.version and profile.version != "custom":
                profile.forge_full_version = f"{profile.version}-{modloader_version}"
        profile.java_version = normalize_java_version(variables.get("RECOMMENDED_JAVA_VERSION", ""), profile.version)
        return True

    def _server_prepared_then_start(self, profile: ServerProfile, notes: str = "") -> None:
        self.store.update(profile)
        self.refresh_current_profile()
        self.statusBar().showMessage(f"Serveur {profile.server_type} préparé.", 5000)
        if notes:
            self._append_log(profile.id, notes)
        if not self.runner(profile).can_launch():
            QMessageBox.warning(self, "Lancement impossible", "Le modloader a été préparé, mais aucun fichier de lancement serveur n’a été trouvé.")
            return
        self.start_server()

    def _server_prepare_failed(self, message: str) -> None:
        self.statusBar().showMessage("Préparation du modloader échouée.", 5000)
        QMessageBox.critical(self, "Préparation du modloader impossible", message)

    def _handle_java_missing(self, profile_id: str, java_version: str) -> None:
        """Offer to download the missing Java runtime when a server fails to start.

        Triggered by ServerRunner.java_missing. Downloads go to
        managed_java_root() (inside the app's own data folder), so they
        don't require admin rights or touch the system Java install. Once
        the download succeeds, the server start is retried automatically.
        """
        profile = self.store.get(profile_id)
        if not profile:
            return
        if self.java_worker and self.java_worker.isRunning():
            # A Java download is already running (e.g. the user clicked
            # "Démarrer" again); avoid stacking duplicate prompts.
            return
        answer = QMessageBox.question(
            self,
            f"Java {java_version} requis",
            f"Le serveur « {profile.name} » a besoin de Java {java_version}, introuvable sur {machine_label()}.\n\n"
            f"Veux-tu que l’application télécharge Temurin Java {java_version} et l’installe "
            "automatiquement dans son propre dossier ? Le serveur démarrera ensuite "
            "automatiquement avec ce Java.\n\n"
            f"Dossier d’installation: {managed_java_root()}",
        )
        if answer != QMessageBox.Yes:
            self._append_log(profile_id, f"Java {java_version} non installé: démarrage annulé.")
            return
        self._download_java_then(java_version, lambda: self._retry_start_server(profile_id, java_version))

    def _retry_start_server(self, profile_id: str, java_version: str) -> None:
        profile = self.store.get(profile_id)
        if not profile:
            return
        self._append_log(profile_id, f"Java {java_version} installé. Nouvelle tentative de démarrage du serveur...")
        if self.current_profile and self.current_profile.id == profile_id:
            self.start_server()
        else:
            self.statusBar().showMessage(
                f"Java {java_version} installé. Sélectionne « {profile.name} » pour le démarrer.", 8000
            )

    def _ensure_eula(self, profile: ServerProfile) -> bool:
        if profile.eula_path.exists() and "eula=true" in profile.eula_path.read_text(encoding="utf-8", errors="replace").lower():
            return True
        answer = QMessageBox.question(
            self,
            "EULA Minecraft",
            "Minecraft demande d’accepter son EULA avant de démarrer le serveur. Acceptes-tu explicitement le EULA Minecraft ?",
        )
        if answer == QMessageBox.Yes:
            profile.eula_path.write_text("eula=true\n", encoding="utf-8")
            return True
        QMessageBox.information(self, "EULA refusé", "Le serveur ne sera pas démarré.")
        return False

    def stop_server(self) -> None:
        if self.current_profile:
            self.runner(self.current_profile).stop()

    def toggle_server(self) -> None:
        if not self.current_profile:
            return
        runner = self.runner(self.current_profile)
        if runner.running:
            runner.stop()
        else:
            self.start_server()

    def _refresh_start_button(self) -> None:
        if not hasattr(self, "start_btn"):
            return
        running = bool(self.current_profile and self.runner(self.current_profile).running)
        self.start_btn.setText("Arrêter" if running else "Démarrer")
        self.start_btn.setObjectName("StopButton" if running else "PrimaryButton")
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

    def restart_server(self) -> None:
        if not self.current_profile:
            return
        runner = self.runner(self.current_profile)
        if runner.running:
            runner.stop()
            QTimer.singleShot(4000, self.start_server)
        else:
            self.start_server()

    def kill_server(self) -> None:
        if self.current_profile and QMessageBox.question(self, "Forcer l’arrêt", "Forcer l’arrêt seulement si le serveur bloque. Continuer ?") == QMessageBox.Yes:
            self.runner(self.current_profile).kill()

    def send_command(self) -> None:
        if hasattr(self, "command_input"):
            self.send_command_from(self.command_input)

    def send_command_from(self, input_widget: QLineEdit) -> None:
        if not self.current_profile:
            return
        command = input_widget.text().strip()
        if not command:
            return
        display_command = command
        command = command[1:].strip() if command.startswith("/") else command
        runner = self.runner(self.current_profile)
        if not runner.running:
            QMessageBox.warning(self, "Serveur arrêté", "Démarre le serveur avant d’envoyer une commande.")
            return
        runner.send_command(command)
        self._append_log(self.current_profile.id, f"> {display_command}")
        input_widget.clear()

    def _append_log(self, profile_id: str, line: str) -> None:
        # Some mods (e.g. ShotsFired's TACZ drop-table dump) print a single
        # log line that is hundreds of KB long. Rendering that in the
        # console widget can freeze the UI for a long time, so truncate it.
        if len(line) > MAX_LOG_LINE_LENGTH:
            line = line[:MAX_LOG_LINE_LENGTH] + f"… (ligne tronquée, {len(line)} caractères)"
        self.logs.setdefault(profile_id, []).append(line)
        tracker = self.trackers.get(profile_id)
        if not tracker:
            profile = self.store.get(profile_id)
            tracker = PlayerTracker(profile.players if profile else [])
            self.trackers[profile_id] = tracker
        event = tracker.ingest(line)
        if event:
            profile = self.store.get(profile_id)
            if profile:
                profile.players = tracker.rows()
                self.store.update(profile)
                self._notify_player_event(profile, event)
        if self.current_profile and self.current_profile.id == profile_id:
            if not self._log_render_timer.isActive():
                self._log_render_timer.start(150)

    def _flush_log_render(self) -> None:
        self.render_logs()
        self.refresh_players()

    def _notify_player_event(self, profile: ServerProfile, event: Tuple[str, str]) -> None:
        kind, pseudo = event
        if kind == "join":
            self.notify(profile.name, f"{pseudo} a rejoint le serveur.")
        else:
            self.notify(profile.name, f"{pseudo} a quitté le serveur.")

    def _state_changed(self, profile_id: str, state: str) -> None:
        if self.current_profile and self.current_profile.id == profile_id:
            self.status_label.setText(f"Statut: {state}")
            self._refresh_start_button()
        if state == "erreur":
            profile = self.store.get(profile_id)
            if profile:
                self.notify(profile.name, "Le serveur n’a pas pu démarrer. Voir la console pour le détail.", QSystemTrayIcon.Critical)
        if state in {"arrete", "erreur"}:
            self._ram_warned.discard(profile_id)
            self._disk_warned.discard(profile_id)
        self.refresh_server_list()

    def render_logs(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        lines = self.logs.get(profile.id, [])
        for console_name, filter_name in (("console", "log_filter"), ("dashboard_console", "dashboard_log_filter")):
            console = getattr(self, console_name, None)
            log_filter = getattr(self, filter_name, None)
            if not console or not log_filter:
                continue
            selected = log_filter.currentText()
            filtered = lines if selected == "TOUT" else [line for line in lines if selected in line]
            console.setPlainText("\n".join(filtered[-1000:]))
            console.moveCursor(QTextCursor.End)

    def copy_logs(self) -> None:
        QApplication.clipboard().setText(self.console.toPlainText())

    def save_logs(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Sauvegarder les logs", str(profile.folder_path / "logs-export.txt"))
        if path:
            Path(path).write_text(self.console.toPlainText(), encoding="utf-8")

    def clear_logs(self) -> None:
        if self.current_profile:
            self.logs[self.current_profile.id] = []
            self.render_logs()

    def refresh_players(self) -> None:
        profile = self.current_profile
        rows = []
        if profile:
            rows = self.trackers.get(profile.id, PlayerTracker()).rows() or profile.players
        connected = [row for row in rows if row.get("status") == "connecte"]
        self._fill_player_table(self.connected_players_table, connected, connected_only=True)
        self._fill_player_table(self.seen_players_table, rows, connected_only=False)
        self._fill_banned_table(self.banned_players_table, self._banned_players(profile))

    def _fill_player_table(self, table: QTableWidget, rows: List[Dict[str, str]], connected_only: bool) -> None:
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            table.setRowHeight(row_index, 44)
            pseudo = row.get("pseudo", "")
            avatar_item = QTableWidgetItem()
            avatar_item.setIcon(self.avatar_icon(pseudo))
            table.setItem(row_index, 0, avatar_item)
            if connected_only:
                values = [pseudo, row.get("ip", ""), row.get("remote_port", ""), row.get("connected_at", ""), row.get("status", "")]
            else:
                values = [
                    pseudo,
                    row.get("ip", ""),
                    row.get("remote_port", ""),
                    row.get("connected_at", ""),
                    row.get("disconnected_at", ""),
                    row.get("status", ""),
                ]
            for column, value in enumerate(values):
                table.setItem(row_index, column + 1, QTableWidgetItem(value))

    def _fill_banned_table(self, table: QTableWidget, rows: List[Dict[str, str]]) -> None:
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            table.setRowHeight(row_index, 36)
            values = [
                row.get("name", ""),
                row.get("uuid", ""),
                row.get("created", ""),
                row.get("source", ""),
                row.get("expires", ""),
                row.get("reason", ""),
            ]
            for column, value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(value))

    def _banned_players(self, profile: Optional[ServerProfile]) -> List[Dict[str, str]]:
        if not profile:
            return []
        path = profile.folder_path / "banned-players.json"
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, list):
            return []
        return [row for row in raw if isinstance(row, dict)]

    def avatar_icon(self, pseudo: str) -> QIcon:
        key = pseudo.lower()
        if not pseudo:
            return self.placeholder_avatar("?")
        if key in self.avatar_cache:
            return self.avatar_cache[key]
        cached = self.avatar_cache_dir / f"{key}.png"
        if cached.exists():
            self.avatar_cache[key] = QIcon(str(cached))
            return self.avatar_cache[key]
        if self.settings.get_bool("download_player_heads") and key not in self.avatar_workers:
            worker = AvatarWorker(pseudo, self.avatar_cache_dir)
            worker.loaded.connect(self._avatar_loaded)
            worker.failed.connect(self._avatar_failed)
            self.avatar_workers[key] = worker
            worker.start()
        return self.placeholder_avatar(pseudo[:1].upper())

    def placeholder_avatar(self, letter: str) -> QIcon:
        pixmap = QPixmap(36, 36)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#d8dee9"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, 36, 36, 8, 8)
        painter.setPen(QColor("#2f343d"))
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, letter or "?")
        painter.end()
        return QIcon(pixmap)

    def _avatar_loaded(self, pseudo: str, path: str) -> None:
        key = pseudo.lower()
        self.avatar_cache[key] = QIcon(path)
        self.avatar_workers.pop(key, None)
        self.refresh_players()

    def _avatar_failed(self, pseudo: str) -> None:
        self.avatar_workers.pop(pseudo.lower(), None)

    def player_context_menu(self, table: QTableWidget, pos) -> None:
        row = table.rowAt(pos.y())
        if row < 0:
            return
        pseudo_column = 0 if table is self.banned_players_table else 1
        table.setCurrentCell(row, pseudo_column)
        pseudo_item = table.item(row, pseudo_column)
        if not pseudo_item or not pseudo_item.text().strip():
            return
        pseudo = pseudo_item.text().strip()
        menu = QMenu(self)
        actions = {}
        if table is self.banned_players_table:
            actions[menu.addAction("Débannir")] = f"pardon {pseudo}"
            actions[menu.addAction("Ajouter à la whitelist")] = f"whitelist add {pseudo}"
        else:
            actions = {
                menu.addAction("Mettre opérateur"): f"op {pseudo}",
                menu.addAction("Retirer opérateur"): f"deop {pseudo}",
                menu.addSeparator(): "",
                menu.addAction("Expulser"): f"kick {pseudo}",
                menu.addAction("Bannir"): f"ban {pseudo}",
                menu.addAction("Débannir"): f"pardon {pseudo}",
                menu.addSeparator(): "",
                menu.addAction("Ajouter à la whitelist"): f"whitelist add {pseudo}",
                menu.addAction("Retirer de la whitelist"): f"whitelist remove {pseudo}",
            }
        selected = menu.exec(table.viewport().mapToGlobal(pos))
        command = actions.get(selected, "")
        if command:
            self.send_player_command(command)

    def send_player_command(self, command: str) -> None:
        profile = self.current_profile
        if not profile:
            return
        runner = self.runner(profile)
        if not runner.running:
            QMessageBox.warning(self, "Serveur arrêté", "Démarre le serveur avant d’envoyer une commande joueur.")
            return
        runner.send_command(command)
        self._append_log(profile.id, f"> {command}")
        self.statusBar().showMessage(f"Commande envoyée: {command}", 4000)
        self.refresh_players()

    def render_properties(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        for key, toggle in self.property_switches.items():
            toggle.blockSignals(True)
            toggle.setChecked(profile.properties.get(key, DEFAULT_PROPERTIES.get(key, "false")).lower() == "true")
            toggle.blockSignals(False)
        keys = ADVANCED_PROPERTY_KEYS
        self.properties_table.setRowCount(len(keys))
        for row, key in enumerate(keys):
            key_item = QTableWidgetItem(key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
            self.properties_table.setItem(row, 0, key_item)
            self.properties_table.setItem(row, 1, QTableWidgetItem(profile.properties.get(key, "")))
        self._update_security_warning()

    def save_properties(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        values = dict(profile.properties)
        for key, toggle in self.property_switches.items():
            values[key] = "true" if toggle.isChecked() else "false"
        for row in range(self.properties_table.rowCount()):
            key = self.properties_table.item(row, 0).text()
            value_item = self.properties_table.item(row, 1)
            values[key] = value_item.text() if value_item else ""
        values["server-ip"] = ""
        profile.properties = values
        profile.port = int(values.get("server-port", profile.port))
        write_properties(profile.folder_path / "server.properties", values)
        self.store.update(profile)
        self._update_security_warning()
        self.refresh_server_list()

    def save_ram_settings(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        ram_min = self.ram_min_setting.value()
        ram_max = self.ram_max_setting.value()
        if ram_min > ram_max:
            QMessageBox.warning(self, "RAM invalide", "La RAM minimale ne peut pas être supérieure à la RAM maximale.")
            return
        profile.ram_min_gb = ram_min
        profile.ram_max_gb = ram_max
        if find_start_script(profile.folder_path):
            try:
                configure_start_script_server(profile)
            except Exception as exc:
                QMessageBox.warning(self, "RAM enregistrée, script non mis à jour", str(exc))
        self.store.update(profile)
        self.refresh_dashboard()
        if self.runner(profile).running:
            QMessageBox.information(self, "RAM enregistrée", "La nouvelle RAM sera utilisée au prochain redémarrage du serveur.")
        else:
            self.statusBar().showMessage("RAM du serveur enregistrée.", 5000)

    def _update_security_warning(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        warnings = []
        if profile.properties.get("online-mode", "true").lower() == "false":
            warnings.append("online-mode=false désactive la vérification Mojang.")
        if profile.properties.get("white-list", "false").lower() == "false":
            warnings.append("white-list=false autorise les connexions non listées.")
        self.security_warning.setText("Avertissement sécurité: " + " ".join(warnings) if warnings else "")

    def change_version(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        new_version = self.new_version.currentText().strip()
        if not new_version or new_version == profile.version:
            return
        if QMessageBox.question(self, "Changer de version", "Un backup va être créé. Revenir vers une ancienne version peut corrompre le monde. Continuer ?") != QMessageBox.Yes:
            return
        create_backup(profile, "before-version-change")
        old_dir = profile.folder_path / "old_versions"
        old_dir.mkdir(exist_ok=True)
        if profile.jar_path.exists():
            shutil.copy2(profile.jar_path, old_dir / f"{profile.version}-{profile.jar_file}")
        try:
            VanillaDownloader().download_server(new_version, profile.jar_path)
        except Exception as exc:
            QMessageBox.critical(self, "Téléchargement impossible", str(exc))
            return
        profile.version = new_version
        self.store.update(profile)
        self.refresh_current_profile()

    def create_manual_backup(self) -> None:
        if not self.current_profile:
            return
        archive = create_backup(self.current_profile)
        self.refresh_backups()
        QMessageBox.information(self, "Backup créé", str(archive))

    def refresh_backups(self) -> None:
        self.backups_list.clear()
        if not self.current_profile:
            return
        for archive in backup_files(self.current_profile):
            self.backups_list.addItem(str(archive))

    def restore_selected_backup(self) -> None:
        profile = self.current_profile
        item = self.backups_list.currentItem()
        if not profile or not item:
            return
        if QMessageBox.question(self, "Restaurer", "Restaurer ce backup avec confirmation ?") == QMessageBox.Yes:
            restore_backup(profile, Path(item.text()))
            QMessageBox.information(self, "Backup restauré", "Restauration terminée.")

    def open_backups_folder(self) -> None:
        if self.current_profile:
            open_folder(backups_dir(self.current_profile))

    def _request_folder_size(self, profile: ServerProfile) -> None:
        """Kick off a background folder-size scan if none is running.

        Re-scanning every 10s is plenty for a size display and keeps
        os.walk off the UI thread entirely.
        """
        worker = self._folder_size_workers.get(profile.id)
        if worker and worker.isRunning():
            return
        last_started = self._folder_size_last_started.get(profile.id, 0.0)
        if time.monotonic() - last_started < 10.0:
            return
        self._folder_size_last_started[profile.id] = time.monotonic()
        worker = FolderSizeWorker(profile.id, profile.folder_path)
        worker.finished_size.connect(self._folder_size_ready)
        self._folder_size_workers[profile.id] = worker
        worker.start()

    def _folder_size_ready(self, profile_id: str, size_mb: float) -> None:
        self._folder_size_cache[profile_id] = size_mb
        if self.current_profile and self.current_profile.id == profile_id:
            self.folder_label.setText(f"Taille dossier: {size_mb:.1f} Mo")
            self.disk_chart.push(size_mb)

    def refresh_dashboard(self) -> None:
        profile = self.current_profile
        if not profile:
            return
        runner = self.runner(profile)
        folder_mb = self._folder_size_cache.get(profile.id, 0.0)
        snapshot = self.monitor.snapshot(runner.pid, profile.folder_path, folder_mb)
        self._request_folder_size(profile)
        self.status_label.setText(f"Statut: {'demarre' if runner.running else 'arrete'}")
        self._refresh_start_button()
        max_ram = max(profile.ram_max_gb * 1024, 1)
        self.ram_bar.setMaximum(max_ram)
        self.ram_bar.setValue(min(int(snapshot["ram_mb"]), max_ram))
        self.ram_bar.setFormat(f"{snapshot['ram_mb']:.0f} Mo / {profile.ram_max_gb} Go")
        self.ram_chart.push(snapshot["ram_mb"], max_ram)
        cpu_value = max(0.0, snapshot["cpu"])
        self.cpu_bar.setValue(max(0, min(int(snapshot["cpu"]), 100)))
        self.cpu_bar.setFormat(f"{cpu_value:.1f}%")
        self.cpu_chart.push(cpu_value, 100)
        connected = len([p for p in self.trackers.get(profile.id, PlayerTracker()).rows() if p.get("status") == "connecte"])
        self.players_bar.setMaximum(max(int(profile.properties.get("max-players", "20")), 1))
        self.players_bar.setValue(connected)
        self.players_bar.setFormat(f"{connected} connecté(s)")
        self.ram_alloc_label.setText(f"Allocation RAM: {profile.ram_min_gb} Go min / {profile.ram_max_gb} Go max")
        self.folder_label.setText(f"Taille dossier: {snapshot['folder_mb']:.1f} Mo")
        self.disk_label.setText(f"Disque libre: {snapshot['disk_free_gb']:.1f} Go")
        self.storage_label.setText(
            f"Dossier: {profile.folder_path}\n"
            f"server.jar: {profile.jar_path}\n"
            f"Processus surveillés: {int(snapshot['process_count'])}\n"
            f"Taille du dossier serveur: {snapshot['folder_mb']:.1f} Mo\n"
            f"Espace disque libre: {snapshot['disk_free_gb']:.1f} Go"
        )
        self._check_resource_alerts(profile, runner, snapshot, max_ram)

    def _check_resource_alerts(self, profile: ServerProfile, runner: ServerRunner, snapshot: Dict[str, float], max_ram: int) -> None:
        """Warn about resource issues that often cause crashes or lag.

        Each alert fires once per "episode": it is re-armed only once the
        metric goes back under a lower threshold, to avoid spamming a
        notification every 1.5s while the server stays under pressure.
        """
        if runner.running and snapshot["ram_mb"] >= max_ram * 0.9:
            if profile.id not in self._ram_warned:
                self._ram_warned.add(profile.id)
                self.notify(
                    profile.name,
                    f"RAM presque pleine: {snapshot['ram_mb']:.0f} Mo utilisés sur {profile.ram_max_gb} Go alloués. "
                    "Le serveur risque de devenir instable ou de crasher.",
                    QSystemTrayIcon.Warning,
                )
        elif snapshot["ram_mb"] < max_ram * 0.75:
            self._ram_warned.discard(profile.id)

        if snapshot["disk_free_gb"] < 1.0:
            if profile.id not in self._disk_warned:
                self._disk_warned.add(profile.id)
                self.notify(
                    profile.name,
                    f"Espace disque faible: {snapshot['disk_free_gb']:.1f} Go restants sur {machine_label()}. "
                    "Le serveur peut s’arrêter ou corrompre des fichiers s’il n’y a plus de place.",
                    QSystemTrayIcon.Warning,
                )
        elif snapshot["disk_free_gb"] > 2.0:
            self._disk_warned.discard(profile.id)
