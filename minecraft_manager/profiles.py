from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from .models import ServerProfile, app_data_dir


class ProfileStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or (app_data_dir() / "profiles.json")
        self.profiles: List[ServerProfile] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.profiles = []
            return
        with self.path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        self.profiles = [ServerProfile.from_dict(item) for item in raw]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump([p.to_dict() for p in self.profiles], fh, ensure_ascii=False, indent=2)

    def add(self, profile: ServerProfile) -> None:
        self.profiles.append(profile)
        self.save()

    def update(self, profile: ServerProfile) -> None:
        for index, current in enumerate(self.profiles):
            if current.id == profile.id:
                self.profiles[index] = profile
                self.save()
                return
        self.add(profile)

    def remove(self, profile_id: str) -> None:
        self.profiles = [p for p in self.profiles if p.id != profile_id]
        self.save()

    def get(self, profile_id: str) -> Optional[ServerProfile]:
        return next((p for p in self.profiles if p.id == profile_id), None)
