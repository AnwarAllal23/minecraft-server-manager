from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

JOIN_RE = re.compile(r"(?P<name>[A-Za-z0-9_]{2,16})\[/((?P<ip>[^:/]+):(?P<port>\d+))\] logged in")
LEFT_RE = re.compile(r"(?P<name>[A-Za-z0-9_]{2,16}) left the game")


class PlayerTracker:
    def __init__(self, rows: List[Dict[str, str]] | None = None) -> None:
        self.sessions: Dict[str, Dict[str, str]] = {}
        self.load(rows or [])

    def load(self, rows: List[Dict[str, str]]) -> None:
        for row in rows:
            pseudo = row.get("pseudo", "")
            if pseudo:
                self.sessions[pseudo] = dict(row)

    def ingest(self, line: str) -> Optional[Tuple[str, str]]:
        """Parse a console line and update the player sessions.

        Returns ``("join", pseudo)`` or ``("leave", pseudo)`` when the line
        matches a connection/disconnection log, so callers can show a
        notification, or ``None`` otherwise.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        joined = JOIN_RE.search(line)
        if joined:
            name = joined.group("name")
            self.sessions[name] = {
                "pseudo": name,
                "ip": joined.group("ip"),
                "remote_port": joined.group("port"),
                "connected_at": now,
                "disconnected_at": "",
                "status": "connecte",
            }
            return ("join", name)
        left = LEFT_RE.search(line)
        if left:
            name = left.group("name")
            session = self.sessions.setdefault(
                name,
                {"pseudo": name, "ip": "", "remote_port": "", "connected_at": "", "status": "deconnecte"},
            )
            session["disconnected_at"] = now
            session["status"] = "deconnecte"
            return ("leave", name)
        return None

    def rows(self) -> List[Dict[str, str]]:
        return list(self.sessions.values())
