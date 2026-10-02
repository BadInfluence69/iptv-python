"""Favorites and recent channels, kept in data_cache/user_data.json.

Stored on the server rather than in the browser so the list follows you between
browsers and survives a cleared cache.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from . import config


class UserData:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.favorites: list[str] = []
        self.recent: list[dict[str, Any]] = []
        self.settings: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        path = config.USER_DATA_FILE
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        self.favorites = list(payload.get("favorites", []))
        self.recent = list(payload.get("recent", []))
        self.settings = dict(payload.get("settings", {}))

    def _save(self) -> None:
        path = config.USER_DATA_FILE
        temp = path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                {
                    "favorites": self.favorites,
                    "recent": self.recent[:60],
                    "settings": self.settings,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        temp.replace(path)

    @property
    def favorite_set(self) -> set[str]:
        return set(self.favorites)

    def toggle_favorite(self, key: str) -> bool:
        with self._lock:
            if key in self.favorites:
                self.favorites.remove(key)
                state = False
            else:
                self.favorites.insert(0, key)
                state = True
            self._save()
        return state

    def remember(self, key: str, name: str) -> None:
        with self._lock:
            self.recent = [r for r in self.recent if r.get("key") != key]
            self.recent.insert(0, {"key": key, "name": name})
            self.recent = self.recent[:60]
            self._save()

    def set_setting(self, name: str, value: Any) -> None:
        with self._lock:
            self.settings[name] = value
            self._save()
