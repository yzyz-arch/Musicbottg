"""Perintah dasar: /start, /help, /alive."""
from __future__ import annotations

import config
import strings as S
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from plugins.common import HTML, register_user


def _start_markup(bot_username: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                "➕ Tambah ke Grup",
                url=f"https://t.me/{bot_username}?startgroup=true&admin=invite_users+manage_video_chats",
            )
        ],
        [
            InlineKeyboardButton("📖 Perintah", callback_data="help_menu"),
            InlineKeyboardButton("🧪 Coba Sendiri", url=f"https://t.me/{bot_username}"),
        ],
    ]
    extra = []
    if config.SUPPORT_CHAT:
        extra.append(InlineKeyboardButton("💬 Support", url=config.SUPPORT_CHAT))
    if config.UPDATES_CHANNEL:
        extra.append(InlineKeyboardButton("📢 Channel", url=config.UPDATES_CHANNEL))
    if extra:
        rows.append(extra)
    return InlineKeyboardMarkup(rows)


def _text(body: str) -> str:
    if config.VOICE_CHAT:
        return body
    return S.FILE_MODE_NOTE + "\n\n" + body


@Client.on_message(filters.command(["start"]) & filters.private)
async def start_cmd(client: Client, message: Message) -> None:
    await register_user(message.from_user, message.chat.id)
    me = await client.get_me()
    await message.reply_text(
        _text(S.START),
        parse_mode=HTML,
        reply_markup=_start_markup(me.username or ""),
    )


@Client.on_message(filters.command(["start"]) & filters.group)
async def start_group(client: Client, message: Message) -> None:
    await register_user(message.from_user, message.chat.id, getattr(message.chat, "title", None))
    hint = (
        "Mulai voice chat lalu <code>/play judul lagu</code>."
        if config.VOICE_CHAT
        else "Langsung <code>/play judul lagu</code> — file dikirim ke chat ini."
    )
    await message.reply_text(f"🎧 Aku aktif di grup ini.\n{hint}", parse_mode=HTML)


@Client.on_message(filters.command(["help"]))
async def help_cmd(client: Client, message: Message) -> None:
    await message.reply_text(_text(S.HELP), parse_mode=HTML)


@Client.on_callback_query(filters.regex(r"^help_menu$"))
async def help_cb(client: Client, cb) -> None:
    await cb.message.edit_text(_text(S.HELP), parse_mode=HTML)
    await cb.answer()


@Client.on_message(filters.command(["alive", "ping"]))
async def ping_cmd(client: Client, message: Message) -> None:
    import time

    t0 = time.perf_counter()
    sent = await message.reply_text("🏓", parse_mode=HTML)
    ms = (time.perf_counter() - t0) * 1000
    try:
        await sent.edit_text(f"🏓 <b>Pong!</b> <code>{ms:.0f} ms</code>", parse_mode=HTML)
    except Exception:
        await sent.edit_text("🏓 Pong!")
