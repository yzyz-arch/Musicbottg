"""Fungsi bersama untuk plugin."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import config
import database as db
import runtime
import strings as S
from downloader import DownloadError, Track, download, to_mp3
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User
from queue_manager import ChatState, queue

from utils import (
    can_control,
    controls_markup,
    ensure_assistant,
    esc,
    human_bytes,
    human_time,
    progress_bar,
    shorten,
)

log = logging.getLogger("musicem.plugins")

HTML = ParseMode.HTML


def user_tag(user: User | None) -> str:
    if not user:
        return "Unknown"
    name = esc(user.first_name or "User")
    if user.username:
        return f'<a href="tg://user?id={user.id}">{name}</a>'
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def track_duration(track: Track) -> str:
    return human_time(track.duration) if track.duration else "LIVE"


async def register_user(user: User | None, chat_id: int, title: str | None = None) -> None:
    if user:
        await db.add_user(user.id, user.first_name, user.username)
    if chat_id < 0:
        await db.add_chat(chat_id, title)


async def require_control(cb_or_msg, chat_id: int, user_id: int) -> bool:
    ok = await can_control(runtime.bot, chat_id, user_id)
    if not ok:
        text = S.NO_PERM
        if isinstance(cb_or_msg, CallbackQuery):
            await cb_or_msg.answer("Cuma admin grup / user ter-auth.", show_alert=True)
        else:
            await cb_or_msg.reply_text(text, parse_mode=HTML)
    return ok


async def _progress_loop(msg: Message, track: Track, stats: dict) -> None:
    """Edit pesan tiap 4 detik selama proses download."""
    while stats.get("running"):
        await asyncio.sleep(4)
        if not stats.get("running"):
            break
        done, total = stats.get("done", 0), stats.get("total", 0)
        if total <= 0:
            continue
        pct = int(done * 100 / total)
        try:
            await msg.edit_text(
                S.DOWNLOADING.format(
                    title=esc(track.title), bar=progress_bar(done, total), pct=pct
                ),
                parse_mode=HTML,
            )
        except Exception:
            pass


async def download_track(msg: Message, track: Track, video: bool) -> bool:
    stats: dict = {"running": True, "done": 0, "total": 0}

    def hook(d: dict) -> None:
        if d.get("status") == "downloading":
            stats["done"] = d.get("downloaded_bytes") or 0
            stats["total"] = d.get("total_bytes") or d.get("total_bytes_estimate") or 0

    poll = asyncio.create_task(_progress_loop(msg, track, stats))
    try:
        await msg.edit_text(
            S.DOWNLOADING.format(title=esc(track.title), bar=progress_bar(0, 1), pct=0),
            parse_mode=HTML,
        )
        await download(track, is_video=video, progress=hook)
        await db.bump("downloads")
        return True
    except DownloadError as exc:
        await msg.edit_text(S.ERROR.format(err=esc(str(exc)[:300])), parse_mode=HTML)
        return False
    finally:
        stats["running"] = False
        poll.cancel()


async def send_track_file(
    msg: Message,
    track: Track,
    video: bool,
    user: User | None,
) -> None:
    """Mode tanpa voice chat: kirim hasil download sebagai file."""
    if not track.filepath:
        await msg.edit_text(S.ERROR.format(err="file tidak ada"), parse_mode=HTML)
        return
    size = Path(track.filepath).stat().st_size
    if size > config.MAX_UPLOAD:
        await msg.edit_text(
            S.FILE_TOO_BIG.format(
                size=human_bytes(size),
                limit=human_bytes(config.MAX_UPLOAD),
                url=esc(track.url),
            ),
            parse_mode=HTML,
        )
        return

    await msg.edit_text(S.UPLOADING.format(title=esc(track.short)), parse_mode=HTML)
    caption = (
        f"🎵 <b>{esc(shorten(track.title, 60))}</b>\n"
        f"⏱ <code>{track_duration(track)}</code> • 👤 {user_tag(user)}"
    )
    try:
        upload_path = track.filepath if video else await to_mp3(track.filepath)
        if video:
            await msg.reply_video(
                upload_path,
                duration=track.duration or None,
                caption=caption,
                parse_mode=HTML,
                width=1280,
                height=720,
                supports_streaming=True,
            )
        else:
            await msg.reply_audio(
                upload_path,
                title=track.title,
                performer=track.uploader or "Unknown",
                duration=track.duration or None,
                caption=caption,
                parse_mode=HTML,
            )
    except Exception as exc:
        log.warning("upload gagal: %s", exc)
        if size > 20 * 1024 * 1024:
            await msg.edit_text(
                S.FILE_TOO_BIG.format(
                    size=human_bytes(size),
                    limit="20 MB (upload bot)",
                    url=esc(track.url),
                ),
                parse_mode=HTML,
            )
        else:
            await msg.edit_text(
                S.ERROR.format(err=esc(f"{type(exc).__name__}: {str(exc)[:180]}")),
                parse_mode=HTML,
            )
        return
    await db.bump("downloads")
    try:
        await msg.edit_text(S.SENT.format(title=esc(track.short)), parse_mode=HTML)
    except Exception:
        pass


async def enqueue_or_play(
    msg: Message,
    track: Track,
    video: bool,
    user: User | None,
) -> None:
    chat_id = msg.chat.id
    track.is_video = video
    if track.duration and track.duration > config.MAX_DURATION:
        await msg.edit_text(
            S.TOO_LONG.format(
                dur=human_time(track.duration), max=human_time(config.MAX_DURATION)
            ),
            parse_mode=HTML,
        )
        return

    if not config.VOICE_CHAT:
        if not await download_track(msg, track, video):
            return
        await send_track_file(msg, track, video, user)
        return

    state = await queue.get(chat_id)
    try:
        await ensure_assistant(runtime.assistant, chat_id)
    except Exception as exc:
        log.warning("assistant join failed: %s", exc)
        await msg.edit_text(S.NEED_ASSISTANT, parse_mode=HTML)
        return

    if not await download_track(msg, track, video):
        return

    if state.active:
        try:
            pos = await queue.push(chat_id, track)
        except ValueError:
            await msg.edit_text(S.QUEUE_FULL.format(limit=config.QUEUE_LIMIT), parse_mode=HTML)
            return
        await msg.edit_text(
            S.ADDED_QUEUE.format(
                pos=pos,
                title=esc(track.short),
                dur=track_duration(track),
                user=user_tag(user),
            ),
            parse_mode=HTML,
        )
        return

    try:
        await runtime.player.start_queue(chat_id, track, video)
    except Exception as exc:
        log.warning("start_queue failed: %s", exc)
        name = type(exc).__name__
        low = str(exc).lower()
        if "group_call" in low or "noactive" in name.lower():
            text = S.NEED_VC
        elif "telegramserver" in name.lower() or "500" in str(exc):
            text = (
                "⚠️ Telegram lagi error saat join voice chat (500).\n"
                "Coba lagi 1–2 menit, atau stop lalu mulai ulang voice chat-nya."
            )
        else:
            text = S.ERROR.format(err=esc(f"{name}: {str(exc)[:200]}"))
        await msg.edit_text(text, parse_mode=HTML)
        # fallback: kalau VC gagal, kirim filenya biar tetap bisa didengar
        if track.filepath:
            try:
                up = await to_mp3(track.filepath)
                await msg.reply_audio(
                    up,
                    title=track.title,
                    performer=track.uploader or "Unknown",
                    duration=track.duration,
                    caption=f"🎵 <b>{esc(track.short)}</b> — file audio (VC gagal join)",
                    parse_mode=HTML,
                )
            except Exception:
                pass
        return

    await msg.edit_text(
        S.PLAYING.format(
            title=esc(track.short),
            dur=track_duration(track),
            user=user_tag(user),
        ),
        parse_mode=HTML,
        reply_markup=controls_markup(chat_id, False),
    )
    state.panel_chat = msg.chat.id
    state.panel_id = msg.id
    await db.bump("played")


def pick_token() -> str:
    import secrets

    return secrets.token_hex(4)


async def queue_view(chat_id: int, state: ChatState, page: int = 0) -> tuple[str, InlineKeyboardMarkup | None]:
    """Teks + markup antrean (10 lagu per halaman)."""
    from utils import queue_markup

    if not state.current and not state.queue:
        return S.QUEUE_EMPTY, None
    pos = await runtime.player.elapsed(chat_id) if state.active else 0
    body = S.NOW_HEADER.format(
        title=esc(shorten(state.current.title, 55)) if state.current else "-",
        pos=human_time(pos),
        dur=human_time(state.current.duration) if state.current else "-",
        vol=state.volume,
        loop=state.loop,
    )
    items = list(state.queue)
    per_page = 10
    pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = items[page * per_page : (page + 1) * per_page]
    if chunk:
        body += "\n" + S.QUEUE_HEADER.format(count=len(items))
        for idx, item in enumerate(chunk, start=page * per_page + 1):
            body += S.QUEUE_ROW.format(
                idx=idx, title=esc(shorten(item.title, 45)), dur=human_time(item.duration)
            )
    return body, queue_markup(chat_id, page, pages)
