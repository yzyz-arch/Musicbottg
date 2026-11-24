"""Handler inline button (kontrol & pemilihan hasil pencarian)."""
from __future__ import annotations

import logging

import config
import runtime
import strings as S
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery
from queue_manager import queue

from plugins.common import HTML, enqueue_or_play, queue_view
from utils import can_control, controls_markup

log = logging.getLogger("musicem.callbacks")


async def _guard(cb: CallbackQuery, chat_id: int) -> bool:
    if not await can_control(runtime.bot, chat_id, cb.from_user.id):
        await cb.answer("Cuma admin grup / user ter-auth yang bisa kontrol.", show_alert=True)
        return False
    return True


@Client.on_callback_query(filters.regex(r"^noop$"))
async def noop(_client: Client, cb: CallbackQuery) -> None:
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^ctl:"))
async def control_cb(client: Client, cb: CallbackQuery) -> None:
    try:
        _, action, raw_chat = cb.data.split(":")
        chat_id = int(raw_chat)
    except ValueError:
        await cb.answer("Data tombol rusak.")
        return

    if not config.VOICE_CHAT:
        await cb.answer("Bot jalan tanpa voice chat — pakai /play ya.", show_alert=True)
        return
    if not await _guard(cb, chat_id):
        return
    state = await queue.get(chat_id)

    if action == "close":
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.answer()
        return

    if action == "pause":
        if not state.active:
            await cb.answer("Nggak ada yang diputar.", show_alert=True)
            return
        if state.paused:
            await runtime.player.resume(chat_id)
            label = "▶️ Lanjut"
        else:
            await runtime.player.pause(chat_id)
            label = "⏸ Pause"
        try:
            await cb.message.edit_reply_markup(controls_markup(chat_id, state.paused))
        except Exception:
            pass
        await cb.answer(label)

    elif action == "resume":
        if not state.active:
            await cb.answer("Nggak ada yang diputar.", show_alert=True)
            return
        await runtime.player.resume(chat_id)
        try:
            await cb.message.edit_reply_markup(controls_markup(chat_id, False))
        except Exception:
            pass
        await cb.answer("▶️ Lanjut")

    elif action == "skip":
        if not state.active:
            await cb.answer("Nggak ada yang diputar.", show_alert=True)
            return
        nxt = await runtime.player.skip(chat_id)
        await cb.answer(f"⏭ {nxt.short if nxt else 'Antrean habis'}")

    elif action == "prev":
        prev = await runtime.player.prev(chat_id)
        await cb.answer(f"⏮ {prev.short if prev else 'Tidak ada riwayat'}")

    elif action == "end":
        await runtime.player.end(chat_id)
        try:
            await cb.message.edit_text(S.ENDED, parse_mode=HTML)
        except Exception:
            pass
        await cb.answer("⏹ Stop")

    elif action == "queue":
        text, markup = await queue_view(chat_id, state, 0)
        try:
            await cb.message.reply_text(text, parse_mode=HTML, reply_markup=markup)
        except Exception as exc:
            log.debug("queue reply failed: %s", exc)
        await cb.answer("📋 Antrean dikirim")

    elif action == "loop":
        order = {"off": "one", "one": "all", "all": "off"}
        state.loop = order.get(state.loop, "off")
        await cb.answer(f"🔁 Loop {state.loop}")

    elif action in {"volup", "voldown"}:
        delta = 10 if action == "volup" else -10
        vol = max(1, min(200, state.volume + delta))
        if state.active:
            await runtime.player.set_volume(chat_id, vol)
        else:
            state.volume = vol
        await cb.answer(f"🔊 Volume {vol}%")


@Client.on_callback_query(filters.regex(r"^q:"))
async def queue_page_cb(client: Client, cb: CallbackQuery) -> None:
    try:
        _, raw_chat, raw_page = cb.data.split(":")
        chat_id, page = int(raw_chat), int(raw_page)
    except ValueError:
        await cb.answer("Data tombol rusak.")
        return
    if not config.VOICE_CHAT:
        await cb.answer("Bot jalan tanpa voice chat.", show_alert=True)
        return
    state = await queue.get(chat_id)
    text, markup = await queue_view(chat_id, state, page)
    try:
        await cb.message.edit_text(text, parse_mode=HTML, reply_markup=markup)
    except Exception:
        pass
    await cb.answer()


@Client.on_callback_query(filters.regex(r"^pick:"))
async def pick_cb(client: Client, cb: CallbackQuery) -> None:
    parts = cb.data.split(":")
    if len(parts) < 4:
        await cb.answer()
        return
    _, token, idx, action = parts[:4]
    if idx == "x":
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.answer("Dibatalkan")
        return

    results = runtime.searches.get(token)
    if not results:
        await cb.answer("Hasil kedaluwarsa, ulangi /play.", show_alert=True)
        return
    try:
        track = results[int(idx)]
    except (ValueError, IndexError):
        await cb.answer("Pilihan tidak valid.", show_alert=True)
        return

    await cb.answer("Diproses…")
    track.requested_by = cb.from_user.id
    track.requester_name = cb.from_user.first_name or ""
    await enqueue_or_play(cb.message, track, action == "v", cb.from_user)
