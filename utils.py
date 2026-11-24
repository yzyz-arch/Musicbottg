"""Helper umum: format, auth, UI, dan antrean download."""
from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from typing import Iterable

import config
import database as db
from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger("musicem")

PLATFORMS = (
    "youtube.com",
    "youtu.be",
    "music.youtube.com",
    "soundcloud.com",
    "spotify.com",
    "vimeo.com",
    "dailymotion.com",
)

# ── Format helpers ──────────────────────────────────────────────────────


def human_time(seconds: int | float | None) -> str:
    if not seconds or seconds < 0:
        return "LIVE"
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def human_bytes(num: int | float | None) -> str:
    if not num:
        return "0 B"
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def progress_bar(done: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "▱" * width
    filled = max(0, min(width, round(width * done / total)))
    return "▰" * filled + "▱" * (width - filled)


def shorten(text: str | None, limit: int = 48) -> str:
    text = (text or "Unknown").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def esc(text: str | None) -> str:
    return html.escape(text or "")


def is_url(text: str) -> bool:
    text = (text or "").strip()
    return bool(re.match(r"^https?://[^\s]+\.[a-z]{2,}", text, re.I))


def now() -> float:
    return time.time()


# ── Auth ────────────────────────────────────────────────────────────────


async def is_sudo(user_id: int) -> bool:
    return (
        user_id == config.OWNER_ID
        or user_id in config.SUDO_USERS
        or await db.is_global_auth(user_id)
    )


async def is_group_admin(client: Client, chat_id: int, user_id: int) -> bool:
    if chat_id > 0:
        return False
    try:
        member = await client.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    if member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
        return True
    return bool(getattr(member, "privileges", None)) and getattr(
        member.privileges, "can_manage_video_chats", False
    )


async def can_control(client: Client, chat_id: int, user_id: int) -> bool:
    if await is_sudo(user_id):
        return True
    if await is_group_admin(client, chat_id, user_id):
        return True
    return await db.is_chat_auth(chat_id, user_id)


# ── Chat / assistant helpers ────────────────────────────────────────────


async def ensure_assistant(client: Client, chat_id: int) -> None:
    """Pastikan akun assistant sudah jadi anggota chat."""
    if chat_id > 0:
        return
    try:
        await client.get_chat_member(chat_id, "me")
        return
    except UserNotParticipant:
        pass
    except Exception as exc:  # chat tidak dikenal / belum join
        log.debug("assistant lookup failed: %s", exc)

    invite = None
    try:
        invite = await client.export_chat_invite_link(chat_id)
    except Exception:
        invite = None
    if not invite:
        raise RuntimeError("Assistant belum di grup dan link invite tidak bisa dibuat.")
    await client.join_chat(invite)


async def is_admin(client: Client, chat_id: int) -> bool:
    try:
        me = await client.get_chat_member(chat_id, "me")
        return me.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except Exception:
        return False


async def chat_type_is_group(chat_id: int) -> bool:
    return chat_id < 0


# ── UI ──────────────────────────────────────────────────────────────────


def controls_markup(chat_id: int, paused: bool = False) -> InlineKeyboardMarkup:
    toggle = ("resume", "▶️ Resume") if paused else ("pause", "⏸ Pause")
    rows = [
        [
            InlineKeyboardButton("⏮", callback_data=f"ctl:prev:{chat_id}"),
            InlineKeyboardButton(toggle[1], callback_data=f"ctl:{toggle[0]}:{chat_id}"),
            InlineKeyboardButton("⏭", callback_data=f"ctl:skip:{chat_id}"),
            InlineKeyboardButton("⏹", callback_data=f"ctl:end:{chat_id}"),
        ],
        [
            InlineKeyboardButton("📋 Antrean", callback_data=f"ctl:queue:{chat_id}"),
            InlineKeyboardButton("🔁 Loop", callback_data=f"ctl:loop:{chat_id}"),
            InlineKeyboardButton("🔊", callback_data=f"ctl:volup:{chat_id}"),
            InlineKeyboardButton("🔉", callback_data=f"ctl:voldown:{chat_id}"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def queue_markup(chat_id: int, page: int, pages: int) -> InlineKeyboardMarkup:
    rows = []
    if pages > 1:
        rows.append(
            [
                InlineKeyboardButton("◀️", callback_data=f"q:{chat_id}:{page - 1}"),
                InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"),
                InlineKeyboardButton("▶️", callback_data=f"q:{chat_id}:{page + 1}"),
            ]
        )
    rows.append([InlineKeyboardButton("❌ Tutup", callback_data=f"ctl:close:{chat_id}")])
    return InlineKeyboardMarkup(rows)


def result_markup(token: str, results: Iterable[dict], is_video: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for idx, item in enumerate(results):
        label = f"{idx + 1}. {shorten(item['title'], 42)} • {human_time(item.get('duration'))}"
        action = "v" if is_video else "a"
        rows.append([InlineKeyboardButton(label, callback_data=f"pick:{token}:{idx}:{action}")])
    rows.append([InlineKeyboardButton("❌ Batal", callback_data=f"pick:{token}:x")])
    return InlineKeyboardMarkup(rows)


# ── Download semaphore (batasi proses yt-dlp paralel) ───────────────────

_download_sem = asyncio.Semaphore(3)


def download_slot() -> asyncio.Semaphore:
    return _download_sem
