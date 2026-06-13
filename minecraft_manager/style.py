from __future__ import annotations

import subprocess


def macos_system_theme() -> str:
    try:
        output = subprocess.check_output(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "light"
    return "dark" if output.lower() == "dark" else "light"


def resolve_theme(mode: str) -> str:
    if mode == "dark":
        return "dark"
    if mode == "light":
        return "light"
    return macos_system_theme()


def style_for_mode(mode: str) -> str:
    return _style(resolve_theme(mode))


def _style(theme: str) -> str:
    dark = theme == "dark"
    colors = {
        "bg": "#1f1f24" if dark else "#f3f4f7",
        "panel": "#2a2a31" if dark else "#ffffff",
        "sidebar": "#24242b" if dark else "#eceff4",
        "border": "#3a3a44" if dark else "#dde1e8",
        "text": "#f5f5f7" if dark else "#1f2328",
        "muted": "#a1a1aa" if dark else "#667085",
        "field": "#303038" if dark else "#ffffff",
        "field_border": "#484852" if dark else "#cfd6df",
        "hover": "#34343d" if dark else "#f8fafc",
        "pressed": "#3c3c46" if dark else "#e7edf5",
        "selected": "#0a3a66" if dark else "#dcecff",
        "selected_text": "#e8f3ff" if dark else "#0b3a75",
        "table_header": "#303038" if dark else "#f8fafc",
        "grid": "#3a3a44" if dark else "#edf0f5",
        "console_bg": "#0e1118" if dark else "#111827",
        "console_text": "#f3f4f6" if dark else "#e5e7eb",
        "progress": "#34343d" if dark else "#e8ecf2",
        "danger": "#ff453a" if dark else "#b42318",
        "danger_border": "#74302c" if dark else "#f0b8b2",
        "accent": "#0a84ff",
        "scrollbar": "#45454f" if dark else "#c7ccd6",
        "scrollbar_hover": "#55555f" if dark else "#aab1bf",
        "tooltip_bg": "#3a3a44" if dark else "#1f2328",
        "tooltip_text": "#f5f5f7" if dark else "#ffffff",
    }
    return f"""
* {{
    font-family: "SF Pro Text", "Helvetica Neue", Arial;
    font-size: 13px;
}}
QMainWindow, QWidget {{
    background: {colors["bg"]};
    color: {colors["text"]};
}}
QWidget#Sidebar {{
    background: {colors["sidebar"]};
    border-right: 1px solid {colors["border"]};
}}
QLabel#SidebarTitle {{
    font-size: 20px;
    font-weight: 700;
    padding: 10px 6px 8px 6px;
}}
QLabel#PageTitle {{
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 0;
}}
QLabel#PanelTitle {{
    font-size: 15px;
    font-weight: 700;
}}
QLabel#SubtleLabel {{
    color: {colors["muted"]};
}}
QLabel#WarningLabel {{
    color: {colors["danger"]};
    font-weight: 600;
}}
QFrame#Surface {{
    background: {colors["panel"]};
    border: 1px solid {colors["border"]};
    border-radius: 8px;
}}
QListWidget {{
    background: transparent;
    border: 0;
    padding: 4px;
}}
QListWidget::item {{
    padding: 10px 9px;
    border-radius: 7px;
}}
QListWidget::item:hover {{
    background: {colors["panel"]};
}}
QListWidget::item:selected {{
    background: {colors["selected"]};
    color: {colors["selected_text"]};
}}
QLineEdit, QComboBox, QSpinBox {{
    background: {colors["field"]};
    color: {colors["text"]};
    border: 1px solid {colors["field_border"]};
    border-radius: 7px;
    padding: 7px 9px;
    min-height: 22px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {colors["accent"]};
}}
QPushButton {{
    background: {colors["panel"]};
    color: {colors["text"]};
    border: 1px solid {colors["field_border"]};
    border-radius: 7px;
    padding: 8px 12px;
    min-height: 22px;
}}
QPushButton:hover {{
    background: {colors["hover"]};
}}
QPushButton:pressed {{
    background: {colors["pressed"]};
}}
QPushButton#PrimaryButton {{
    background: #0a84ff;
    color: #ffffff;
    border: 1px solid #0878e7;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{
    background: #0077ed;
}}
QPushButton#StopButton {{
    background: #ff453a;
    color: #ffffff;
    border: 1px solid #d8342b;
    font-weight: 600;
}}
QPushButton#StopButton:hover {{
    background: #e63b32;
}}
QPushButton#DangerButton {{
    color: {colors["danger"]};
    border: 1px solid {colors["danger_border"]};
}}
QPushButton#SidebarButton {{
    background: transparent;
    border: 1px solid transparent;
    text-align: left;
    padding: 8px 10px;
    color: {colors["muted"]};
}}
QPushButton#SidebarButton:hover {{
    background: {colors["panel"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
}}
QTabWidget::pane {{
    border: 0;
    background: {colors["bg"]};
}}
QTabBar::tab {{
    background: transparent;
    color: {colors["muted"]};
    padding: 10px 12px;
    margin: 3px 1px;
    border-radius: 7px;
}}
QTabBar::tab:selected {{
    background: {colors["panel"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
}}
QTextEdit {{
    background: {colors["console_bg"]};
    color: {colors["console_text"]};
    border: 1px solid #1f2937;
    border-radius: 7px;
    padding: 9px;
    selection-background-color: #2563eb;
}}
QTableWidget {{
    background: {colors["panel"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 8px;
    gridline-color: {colors["grid"]};
    selection-background-color: {colors["selected"]};
    selection-color: {colors["selected_text"]};
}}
QHeaderView::section {{
    background: {colors["table_header"]};
    color: {colors["muted"]};
    border: 0;
    border-bottom: 1px solid {colors["border"]};
    padding: 8px;
    font-weight: 600;
}}
QProgressBar {{
    background: {colors["progress"]};
    border: 1px solid {colors["field_border"]};
    border-radius: 7px;
    text-align: center;
    min-height: 18px;
}}
QProgressBar::chunk {{
    background: #30d158;
    border-radius: 6px;
}}
QMenu {{
    background: {colors["panel"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 22px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background: {colors["selected"]};
}}
QCompleter QAbstractItemView {{
    background: {colors["panel"]};
    color: {colors["text"]};
    border: 1px solid {colors["border"]};
    selection-background-color: {colors["selected"]};
    selection-color: {colors["selected_text"]};
}}
QSplitter::handle {{
    background: transparent;
    width: 6px;
}}
QSplitter::handle:hover {{
    background: {colors["accent"]};
}}
QToolTip {{
    background: {colors["tooltip_bg"]};
    color: {colors["tooltip_text"]};
    border: 1px solid {colors["border"]};
    border-radius: 6px;
    padding: 6px 8px;
}}
QMenuBar {{
    background: {colors["bg"]};
    color: {colors["text"]};
    border-bottom: 1px solid {colors["border"]};
}}
QMenuBar::item {{
    padding: 6px 10px;
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background: {colors["hover"]};
}}
QStatusBar {{
    background: {colors["bg"]};
    color: {colors["muted"]};
    border-top: 1px solid {colors["border"]};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {colors["scrollbar"]};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {colors["scrollbar_hover"]};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {colors["scrollbar"]};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {colors["scrollbar_hover"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
    border: none;
    background: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {colors["field_border"]};
    background: {colors["field"]};
}}
QCheckBox::indicator:checked {{
    background: {colors["accent"]};
    border: 1px solid {colors["accent"]};
}}
"""


APP_STYLE = style_for_mode("auto")
