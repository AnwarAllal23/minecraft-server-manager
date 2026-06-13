from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .models import app_data_dir


DEFAULT_SETTINGS: Dict[str, Any] = {
    "download_player_heads": True,
    "theme_mode": "auto",
    "notifications_enabled": True,
}


class SettingsStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or (app_data_dir() / "settings.json")
        self.values = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            self.values.update(raw)
        except (OSError, json.JSONDecodeError):
            self.values = dict(DEFAULT_SETTINGS)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(self.values, fh, ensure_ascii=False, indent=2)

    def get_bool(self, key: str) -> bool:
        return bool(self.values.get(key, DEFAULT_SETTINGS.get(key, False)))

    def set_bool(self, key: str, value: bool) -> None:
        self.values[key] = bool(value)
        self.save()

    def get_str(self, key: str) -> str:
        return str(self.values.get(key, DEFAULT_SETTINGS.get(key, "")))

    def set_str(self, key: str, value: str) -> None:
        self.values[key] = str(value)
        self.save()
