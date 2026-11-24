"""Utilitas: /id, info chat, dan pembersih cache."""
from __future__ import annotations

import logging

import config
from downloader import cleanup_cache
from pyrogram import Client, filters
from pyrogram.types import Message

from plugins.common import HTML
from utils import esc, human_bytes

log = logging.getLogger("musicem.tools")


@Client.on_message(filters.command(["id", "chatid", "userid"]))
async def id_cmd(client: Client, message: Message) -> None:
    lines = [f"💬 <b>Chat</b>: <code>{message.chat.id}</code>"]
    if message.chat.title:
        lines.append(f"📛 <b>Nama</b>: {esc(message.chat.title)}")
    if message.from_user:
        lines.append(f"👤 <b>User</b>: <code>{message.from_user.id}</code>")
        lines.append(f"🏷 <b>Nama</b>: {esc(message.from_user.first_name or '-')}")
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        lines.append(f"↩️ <b>Target</b>: <code>{u.id}</code> — {esc(u.first_name or '-')}")
    await message.reply_text("\n".join(lines), parse_mode=HTML)


@Client.on_message(filters.command(["cache"]) & filters.user(config.OWNER_ID or 0))
async def cache_cmd(client: Client, message: Message) -> None:
    removed = cleanup_cache()
    total = sum(p.stat().st_size for p in config.DOWNLOAD_DIR.glob("*") if p.is_file())
    await message.reply_text(
        f"🧹 Hapus <code>{removed}</code> file lama.\n"
        f"💾 Sisa cache: <code>{human_bytes(total)}</code>",
        parse_mode=HTML,
    )
