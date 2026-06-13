from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .settings import SettingsStore
from .style import style_for_mode
from .ui import MainWindow

def _icon_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / "app_icon.png"


ICON_PATH = _icon_path()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Gestion Serveurs Minecraft")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setStyleSheet(style_for_mode(SettingsStore().get_str("theme_mode")))
    window = MainWindow()
    window.resize(1280, 780)
    window.show()
    sys.exit(app.exec())
