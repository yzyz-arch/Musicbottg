"""Lapisan database SQLite (async)."""
from __future__ import annotations

import time
from pathlib import Path

import aiosqlite
import config

_path: Path = config.DATA_DIR / "musicem.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id   INTEGER PRIMARY KEY,
    title     TEXT,
    added_at  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    user_id   INTEGER PRIMARY KEY,
    name      TEXT,
    username  TEXT,
    seen_at   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS auth (
    chat_id  INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    added_by INTEGER,
    added_at INTEGER NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);
CREATE TABLE IF NOT EXISTS settings (
    chat_id INTEGER NOT NULL,
    key     TEXT NOT NULL,
    value   TEXT,
    PRIMARY KEY (chat_id, key)
);
CREATE TABLE IF NOT EXISTS counters (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
"""


async def init() -> None:
    config.prepare_dirs()
    async with aiosqlite.connect(_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def _exec(sql: str, params: tuple = ()) -> None:
    async with aiosqlite.connect(_path) as db:
        await db.execute(sql, params)
        await db.commit()


async def _fetchone(sql: str, params: tuple = ()):
    async with aiosqlite.connect(_path) as db:
        async with db.execute(sql, params) as cur:
            return await cur.fetchone()


async def _fetchall(sql: str, params: tuple = ()) -> list[tuple]:
    async with aiosqlite.connect(_path) as db:
        async with db.execute(sql, params) as cur:
            return list(await cur.fetchall())


# ── chats & users ───────────────────────────────────────────────────────


async def add_chat(chat_id: int, title: str | None) -> None:
    await _exec(
        "INSERT INTO chats(chat_id, title, added_at) VALUES(?,?,?) "
        "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title",
        (chat_id, title, int(time.time())),
    )


async def add_user(user_id: int, name: str | None, username: str | None) -> None:
    await _exec(
        "INSERT INTO users(user_id, name, username, seen_at) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, "
        "username=excluded.username, seen_at=excluded.seen_at",
        (user_id, name, username, int(time.time())),
    )


async def bump(key: str, amount: int = 1) -> None:
    async with aiosqlite.connect(_path) as db:
        await db.execute(
            "INSERT INTO counters(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=value+excluded.value",
            (key, amount),
        )
        await db.commit()


async def counters() -> dict[str, int]:
    rows = await _fetchall("SELECT key, value FROM counters")
    return {row[0]: row[1] for row in rows}


async def stats() -> dict[str, int]:
    chats = await _fetchone("SELECT COUNT(*) FROM chats")
    users = await _fetchone("SELECT COUNT(*) FROM users")
    data = await counters()
    data["chats"] = chats[0] if chats else 0
    data["users"] = users[0] if users else 0
    return data


# ── auth ────────────────────────────────────────────────────────────────


async def add_auth(chat_id: int, user_id: int, added_by: int | None = None) -> None:
    await _exec(
        "INSERT OR IGNORE INTO auth(chat_id, user_id, added_by, added_at) VALUES(?,?,?,?)",
        (chat_id, user_id, added_by, int(time.time())),
    )


async def remove_auth(chat_id: int, user_id: int) -> int:
    _exec_sql = "DELETE FROM auth WHERE chat_id=? AND user_id=?"
    async with aiosqlite.connect(_path) as db:
        cur = await db.execute(_exec_sql, (chat_id, user_id))
        await db.commit()
        return cur.rowcount


async def is_auth(chat_id: int, user_id: int) -> bool:
    row = await _fetchone(
        "SELECT 1 FROM auth WHERE (chat_id=? OR chat_id=0) AND user_id=? LIMIT 1",
        (chat_id, user_id),
    )
    return row is not None


async def is_global_auth(user_id: int) -> bool:
    return await is_auth(0, user_id)


async def list_auth(chat_id: int) -> list[int]:
    rows = await _fetchall("SELECT user_id FROM auth WHERE chat_id=?", (chat_id,))
    return [r[0] for r in rows]


# ── settings per chat ───────────────────────────────────────────────────


async def set_setting(chat_id: int, key: str, value: str) -> None:
    await _exec(
        "INSERT INTO settings(chat_id, key, value) VALUES(?,?,?) "
        "ON CONFLICT(chat_id, key) DO UPDATE SET value=excluded.value",
        (chat_id, key, value),
    )


async def get_setting(chat_id: int, key: str, default: str | None = None) -> str | None:
    row = await _fetchone("SELECT value FROM settings WHERE chat_id=? AND key=?", (chat_id, key))
    return row[0] if row else default
