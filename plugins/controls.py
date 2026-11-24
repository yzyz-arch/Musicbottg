"""Kontrol playback: pause, resume, skip, end, seek, loop, volume, queue."""
from __future__ import annotations

import logging
import re

import config
import runtime
import strings as S
from pyrogram import Client, filters
from pyrogram.types import Message
from queue_manager import queue

from plugins.common import HTML, queue_view, require_control
from utils import controls_markup, esc, human_time

log = logging.getLogger("musicem.controls")


def parse_time(raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    parts = raw.split(":")
    if len(parts) <= 3 and all(p.isdigit() for p in parts):
        total = 0
        for part in parts:
            total = total * 60 + int(part)
        return total
    return None


async def _state(chat_id: int):
    return await queue.get(chat_id)


async def _no_vc(message: Message) -> bool:
    """True kalau bot jalan tanpa voice chat (perintah kontrol tidak berlaku)."""
    if config.VOICE_CHAT:
        return False
    await message.reply_text(S.NO_VC_MODE, parse_mode=HTML)
    return True


@Client.on_message(filters.command(["pause"]))
async def pause_cmd(client: Client, message: Message) -> None:
    if await _no_vc(message):
        return
    chat_id = message.chat.id
    if chat_id > 0:
        return
    if not await require_control(message, chat_id, message.from_user.id):
        return
    state = await _state(chat_id)
    if not state.active:
        await message.reply_text(S.NOT_PLAYING, parse_mode=HTML)
        return
    if state.paused:
        await message.reply_text(S.PAUSED.format(title=esc(state.current.short)), parse_mode=HTML)
        return
    try:
        await runtime.player.pause(chat_id)
    except Exception as exc:
        await message.reply_text(S.ERROR.format(err=esc(str(exc)[:200])), parse_mode=HTML)
        return
    await message.reply_text(
        S.PAUSED.format(title=esc(state.current.short)),
        parse_mode=HTML,
        reply_markup=controls_markup(chat_id, True),
    )


@Client.on_message(filters.command(["resume", "unpause"]))
async def resume_cmd(client: Client, message: Message) -> None:
    if await _no_vc(message):
        return
    chat_id = message.chat.id
    if chat_id > 0:
        return
    if not await require_control(message, chat_id, message.from_user.id):
        return
    state = await _state(chat_id)
    if not state.active or not state.current:
        await message.reply_text(S.NOT_PLAYING, parse_mode=HTML)
        return
    try:
        await runtime.player.resume(chat_id)
    except Exception as exc:
        await message.reply_text(S.ERROR.format(err=esc(str(exc)[:200])), parse_mode=HTML)
        return
    await message.reply_text(
        S.RESUMED.format(title=esc(state.current.short)),
        parse_mode=HTML,
        reply_markup=controls_markup(chat_id, False),
    )


@Client.on_message(filters.command(["skip", "next"]))
async def skip_cmd(client: Client, message: Message) -> None:
    if await _no_vc(message):
        return
    chat_id = message.chat.id
    if chat_id > 0:
        return
    if not await require_control(message, chat_id, message.from_user.id):
        return
    state = await _state(chat_id)
    if not state.active:
        await message.reply_text(S.NOT_PLAYING, parse_mode=HTML)
        return
    old = state.current.short if state.current else "-"
    try:
        nxt = await runtime.player.skip(chat_id)
    except Exception as exc:
        await message.reply_text(S.ERROR.format(err=esc(str(exc)[:200])), parse_mode=HTML)
        return
    if nxt is None:
        await message.reply_text(S.ENDED, parse_mode=HTML)
        return
    await message.reply_text(
        f"{S.SKIPPED.format(title=esc(old))}\n▶️ <b>{esc(nxt.short)}</b>",
        parse_mode=HTML,
    )


@Client.on_message(filters.command(["end", "stop"]))
async def end_cmd(client: Client, message: Message) -> None:
    if await _no_vc(message):
        return
    chat_id = message.chat.id
    if chat_id > 0:
        return
    if not await require_control(message, chat_id, message.from_user.id):
        return
    try:
        await runtime.player.end(chat_id)
    except Exception as exc:
        await message.reply_text(S.ERROR.format(err=esc(str(exc)[:200])), parse_mode=HTML)
        return
    await message.reply_text(S.ENDED, parse_mode=HTML)


@Client.on_message(filters.command(["seek"]))
async def seek_cmd(client: Client, message: Message) -> None:
    if await _no_vc(message):
        return
    chat_id = message.chat.id
    if chat_id > 0:
        return
    if not await require_control(message, chat_id, message.from_user.id):
        return
    try:
        raw = message.text.split(None, 1)[1]
    except IndexError:
        await message.reply_text(
            "❌ Contoh: <code>/seek 1:30</code> atau <code>/seek 90</code>", parse_mode=HTML
        )
        return
    seconds = parse_time(raw)
    if seconds is None:
        await message.reply_text("❌ Format waktu nggak valid.", parse_mode=HTML)
        return
    state = await _state(chat_id)
    if not state.active:
        await message.reply_text(S.NOT_PLAYING, parse_mode=HTML)
        return
    try:
        ok = await runtime.player.seek(chat_id, seconds)
    except Exception as exc:
        await message.reply_text(S.ERROR.format(err=esc(str(exc)[:200])), parse_mode=HTML)
        return
    if not ok:
        await message.reply_text("❌ Posisi di luar durasi lagu.", parse_mode=HTML)
        return
    await message.reply_text(S.SEEKED.format(pos=human_time(seconds)), parse_mode=HTML)


@Client.on_message(filters.command(["loop"]))
async def loop_cmd(client: Client, message: Message) -> None:
    if await _no_vc(message):
        return
    chat_id = message.chat.id
    if chat_id > 0:
        return
    if not await require_control(message, chat_id, message.from_user.id):
        return
    state = await _state(chat_id)
    try:
        arg = message.text.split(None, 1)[1].strip().lower()
    except IndexError:
        arg = "off"
    mapping = {"off": "off", "0": "off", "one": "one", "1": "one", "all": "all", "2": "all"}
    if arg not in mapping:
        arg = {"off": "one", "one": "all", "all": "off"}[state.loop]
    state.loop = mapping[arg]
    await message.reply_text(S.LOOP_SET.format(mode=state.loop), parse_mode=HTML)


@Client.on_message(filters.command(["volume", "vol"]))
async def volume_cmd(client: Client, message: Message) -> None:
    if await _no_vc(message):
        return
    chat_id = message.chat.id
    if chat_id > 0:
        return
    if not await require_control(message, chat_id, message.from_user.id):
        return
    try:
        raw = message.text.split(None, 1)[1].strip().rstrip("%")
        vol = int(raw)
    except (IndexError, ValueError):
        await message.reply_text(
            "❌ Contoh: <code>/volume 120</code> (1-200)", parse_mode=HTML
        )
        return
    if not 1 <= vol <= 200:
        await message.reply_text("❌ Volume 1-200.", parse_mode=HTML)
        return
    try:
        await runtime.player.set_volume(chat_id, vol)
    except Exception as exc:
        await message.reply_text(S.ERROR.format(err=esc(str(exc)[:200])), parse_mode=HTML)
        return
    await message.reply_text(S.VOLUME_SET.format(vol=vol), parse_mode=HTML)


@Client.on_message(filters.command(["queue", "q"]))
async def queue_cmd(client: Client, message: Message) -> None:
    if await _no_vc(message):
        return
    chat_id = message.chat.id
    state = await _state(chat_id)
    text, markup = await queue_view(chat_id, state, 0)
    await message.reply_text(text, parse_mode=HTML, reply_markup=markup)


@Client.on_message(filters.command(["current", "now", "np"]))
async def current_cmd(client: Client, message: Message) -> None:
    if await _no_vc(message):
        return
    chat_id = message.chat.id
    state = await _state(chat_id)
    if not state.active or not state.current:
        await message.reply_text(S.NOT_PLAYING, parse_mode=HTML)
        return
    text, markup = await queue_view(chat_id, state, 0)
    await message.reply_text(text, parse_mode=HTML, reply_markup=markup)
