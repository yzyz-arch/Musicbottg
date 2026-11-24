"""Perintah admin: auth, unauth, sudoers, stats."""
from __future__ import annotations

import time

import database as db
import strings as S
from pyrogram import Client, filters
from pyrogram.types import Message
from queue_manager import queue

from plugins.common import HTML, register_user
from utils import can_control, esc, is_sudo


def _target(message: Message) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].lstrip("-").isdigit():
        return int(parts[1])
    return None


@Client.on_message(filters.command(["auth", "allow"]))
async def auth_cmd(client: Client, message: Message) -> None:
    chat_id = message.chat.id
    if chat_id > 0:
        await message.reply_text("Pakai di grup ya.", parse_mode=HTML)
        return
    if not await can_control(client, chat_id, message.from_user.id):
        await message.reply_text(S.NO_PERM, parse_mode=HTML)
        return
    target = _target(message)
    if not target:
        await message.reply_text(
            "❌ Reply user atau tulis ID-nya. Contoh: <code>/auth 12345678</code>",
            parse_mode=HTML,
        )
        return
    await db.add_auth(chat_id, target, message.from_user.id)
    name = target
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        name = u.first_name or str(target)
    await message.reply_text(S.AUTH_OK.format(user=esc(str(name))), parse_mode=HTML)


@Client.on_message(filters.command(["unauth", "disallow"]))
async def unauth_cmd(client: Client, message: Message) -> None:
    chat_id = message.chat.id
    if chat_id > 0:
        await message.reply_text("Pakai di grup ya.", parse_mode=HTML)
        return
    if not await can_control(client, chat_id, message.from_user.id):
        await message.reply_text(S.NO_PERM, parse_mode=HTML)
        return
    target = _target(message)
    if not target:
        await message.reply_text("❌ Reply user atau tulis ID-nya.", parse_mode=HTML)
        return
    removed = await db.remove_auth(chat_id, target)
    if removed:
        await message.reply_text(S.UNAUTH_OK.format(user=target), parse_mode=HTML)
    else:
        await message.reply_text("ℹ️ User itu nggak ada di daftar auth.", parse_mode=HTML)


@Client.on_message(filters.command(["sudoers", "authlist"]))
async def sudoers_cmd(client: Client, message: Message) -> None:
    chat_id = message.chat.id
    users = await db.list_auth(chat_id if chat_id < 0 else 0)
    if not users:
        await message.reply_text(S.NO_AUTHED, parse_mode=HTML)
        return
    rows = "\n".join(f"• <code>{uid}</code>" for uid in users)
    await message.reply_text(S.AUTH_LIST.format(rows=rows), parse_mode=HTML)


@Client.on_message(filters.command(["stats"]))
async def stats_cmd(client: Client, message: Message) -> None:
    if not await is_sudo(message.from_user.id):
        await message.reply_text(S.OWNER_ONLY, parse_mode=HTML)
        return
    await register_user(message.from_user, message.chat.id)
    data = await db.stats()
    active = len([s for s in queue.all_states() if s.active])
    ping = 0.0
    try:
        start = time.monotonic()
        await client.get_me()
        ping = (time.monotonic() - start) * 1000
    except Exception:
        pass
    await message.reply_text(
        S.STATS.format(
            chats=data.get("chats", 0),
            users=data.get("users", 0),
            played=data.get("played", 0),
            downloads=data.get("downloads", 0),
            active=active,
            ping=f"{ping:.0f}",
        ),
        parse_mode=HTML,
    )
