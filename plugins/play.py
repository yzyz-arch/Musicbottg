"""Perintah pemutaran: /play, /vplay, /song."""
from __future__ import annotations

import logging

import config
import database as db
import runtime
import strings as S
from downloader import DownloadError, search, to_mp3
from pyrogram import Client, filters
from pyrogram.types import Message

from plugins.common import (
    HTML,
    download_track,
    enqueue_or_play,
    pick_token,
    register_user,
    user_tag,
)
from utils import esc, human_time, is_url, result_markup, shorten

log = logging.getLogger("musicem.play")


async def _resolve(message: Message, video: bool) -> None:
    try:
        query = message.text.split(None, 1)[1].strip()
    except IndexError:
        await message.reply_text(S.NO_QUERY, parse_mode=HTML)
        return
    if not query:
        await message.reply_text(S.NO_QUERY, parse_mode=HTML)
        return

    await register_user(message.from_user, message.chat.id, getattr(message.chat, "title", None))
    if message.chat.id > 0 and config.VOICE_CHAT:
        await message.reply_text(
            "⚠️ Streaming cuma jalan di <b>grup</b>. Tambahin aku ke grup dulu ya.",
            parse_mode=HTML,
        )
        return

    status = await message.reply_text(
        S.SEARCHING.format(q=esc(shorten(query, 60))), parse_mode=HTML
    )
    try:
        results = await search(query, 1 if is_url(query) else config.SEARCH_LIMIT)
    except DownloadError as exc:
        await status.edit_text(S.ERROR.format(err=esc(str(exc)[:250])), parse_mode=HTML)
        return

    if not results:
        await status.edit_text(
            S.NOT_FOUND.format(q=esc(shorten(query, 60))), parse_mode=HTML
        )
        return

    if len(results) == 1:
        track = results[0]
        track.requested_by = message.from_user.id if message.from_user else 0
        track.requester_name = message.from_user.first_name if message.from_user else ""
        await enqueue_or_play(status, track, video, message.from_user)
        return

    await status.edit_text(
        S.SEARCH_RESULTS.format(q=esc(shorten(query, 60))), parse_mode=HTML
    )
    token = pick_token()
    runtime.searches.put(token, results)
    try:
        await status.edit_reply_markup(
            reply_markup=result_markup(token, [
                {"title": r.title, "duration": r.duration} for r in results
            ], video)
        )
    except Exception as exc:
        log.debug("markup failed: %s", exc)


@Client.on_message(filters.command(["play", "p"]) & filters.group)
async def play_cmd(client: Client, message: Message) -> None:
    await _resolve(message, video=False)


@Client.on_message(filters.command(["vplay", "vp"]) & filters.group)
async def vplay_cmd(client: Client, message: Message) -> None:
    await _resolve(message, video=True)


@Client.on_message(filters.command(["play", "vplay"]) & filters.private)
async def play_private(client: Client, message: Message) -> None:
    if config.VOICE_CHAT:
        await message.reply_text(
            "⚠️ Aku cuma bisa streaming di <b>grup</b> dengan voice chat aktif.\n"
            "Tambahin aku ke grup, jadikan admin, lalu ulangi /play di sana.",
            parse_mode=HTML,
        )
        return
    command = message.text.split()[0][1:].split("@")[0].lower()
    await _resolve(message, video=command.startswith("v"))


@Client.on_message(filters.command(["song", "download", "dl"]))
async def song_cmd(client: Client, message: Message) -> None:
    try:
        query = message.text.split(None, 1)[1].strip()
    except IndexError:
        await message.reply_text(
            "❌ Contoh: <code>/song perfect ed sheeran</code>", parse_mode=HTML
        )
        return

    await register_user(message.from_user, message.chat.id)
    status = await message.reply_text(
        S.SEARCHING.format(q=esc(shorten(query, 50))), parse_mode=HTML
    )
    try:
        results = await search(query, 1)
    except DownloadError as exc:
        await status.edit_text(S.ERROR.format(err=esc(str(exc)[:250])), parse_mode=HTML)
        return
    if not results:
        await status.edit_text(S.NOT_FOUND.format(q=esc(shorten(query, 50))), parse_mode=HTML)
        return

    track = results[0]
    if track.duration and track.duration > config.MAX_DURATION:
        await status.edit_text(
            S.TOO_LONG.format(dur=human_time(track.duration), max=human_time(config.MAX_DURATION)),
            parse_mode=HTML,
        )
        return
    if not await download_track(status, track, video=False):
        return

    await status.edit_text(
        f"📤 Upload <b>{esc(shorten(track.title, 45))}</b>…", parse_mode=HTML
    )
    try:
        upload_path = await to_mp3(track.filepath)
        await message.reply_audio(
            upload_path,
            title=track.title,
            performer=track.uploader or "Unknown",
            duration=track.duration,
            caption=(
                f"🎵 <b>{esc(shorten(track.title, 60))}</b>\n"
                f"⏱ <code>{human_time(track.duration)}</code> • 👤 {user_tag(message.from_user)}"
            ),
            parse_mode=HTML,
        )
    except Exception as exc:
        await status.edit_text(
            S.ERROR.format(err=esc(f"upload gagal: {str(exc)[:200]}")), parse_mode=HTML
        )
        return
    await status.delete()
    await db.bump("downloads")
