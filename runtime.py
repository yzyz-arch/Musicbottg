"""Objek runtime yang dipakai bareng oleh semua plugin."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from downloader import Track
from player import Player
from pyrogram import Client


@dataclass
class SearchCache:
    items: dict[str, tuple[float, list[Track]]] = field(default_factory=dict)
    ttl: int = 600

    def put(self, token: str, tracks: list[Track]) -> None:
        self.items[token] = (time.time(), tracks)

    def get(self, token: str) -> list[Track] | None:
        row = self.items.get(token)
        if not row:
            return None
        created, tracks = row
        if time.time() - created > self.ttl:
            self.items.pop(token, None)
            return None
        return tracks

    def prune(self) -> None:
        now = time.time()
        for key, (created, _) in list(self.items.items()):
            if now - created > self.ttl:
                self.items.pop(key, None)


bot: Client
assistant: Client
player: Player
searches = SearchCache()
