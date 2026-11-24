"""Entrypoint bot musik Telegram."""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

import config
import database as db
import runtime
import strings as S
from downloader import cleanup_cache
from player import Player
from plugins.common import HTML
from pyrogram import Client
from pyrogram.types import BotCommand
from queue_manager import queue

from utils import controls_markup, esc, human_time

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("pytgcalls").setLevel(logging.WARNING)
log = logging.getLogger("musicem")

COMMANDS = [
    BotCommand("play", "Putar musik di voice chat"),
    BotCommand("vplay", "Putar video di voice chat"),
    BotCommand("song", "Download MP3"),
    BotCommand("pause", "Pause lagu"),
    BotCommand("resume", "Lanjutkan lagu"),
    BotCommand("skip", "Lagu berikutnya"),
    BotCommand("seek", "Lompat ke detik tertentu"),
    BotCommand("end", "Stop & bersihkan antrean"),
    BotCommand("queue", "Lihat antrean"),
    BotCommand("current", "Lagu yang diputar"),
    BotCommand("loop", "Mode ulang"),
    BotCommand("volume", "Atur volume"),
    BotCommand("auth", "Izinkan user kontrol"),
    BotCommand("help", "Bantuan"),
]


async def on_player_event(chat_id: int, event: str, track, text: str = "") -> None:
    """Dipanggil player saat lagu ganti / antrean habis."""
    if event == "next" and track:
        state = await queue.get(chat_id)
        await runtime.bot.send_message(
            chat_id,
            S.PLAYING.format(
                title=esc(track.short),
                dur=human_time(track.duration),
                user=esc(track.requester_name or "Auto-play"),
            ),
            parse_mode=HTML,
            reply_markup=controls_markup(chat_id, False),
        )
        state.panel_chat = chat_id
    elif event == "empty":
        await runtime.bot.send_message(chat_id, S.LEFT_EMPTY, parse_mode=HTML)
    elif event == "error":
        await runtime.bot.send_message(
            chat_id, S.ERROR.format(err=esc(text[:200] or "unknown")), parse_mode=HTML
        )


async def housekeeping() -> None:
    while True:
        await asyncio.sleep(1800)
        try:
            runtime.searches.prune()
            removed = await asyncio.to_thread(cleanup_cache)
            if removed:
                log.info("cache: %s file lama dihapus", removed)
        except Exception as exc:
            log.warning("housekeeping error: %s", exc)


async def register_commands(client: Client) -> None:
    try:
        await client.set_bot_commands(COMMANDS)
    except Exception as exc:
        log.warning("gagal set command: %s", exc)


def fail_missing() -> None:
    missing = config.missing()
    print("=" * 60)
    print("  KONFIGURASI BELUM LENGKAP")
    print("=" * 60)
    for name in missing:
        print(f"  ✗ {name}")
    print("\nIsi di file .env (lihat .env.example).")
    if "SESSION_STRING" in missing:
        print("\nBuat session assistant dengan:\n  python session_gen.py")
    if "API_ID" in missing or "API_HASH" in missing:
        print("\nAmbil API_ID/API_HASH di https://my.telegram.org → API development tools")
    sys.exit(1)


async def main() -> None:
    config.prepare_dirs()
    await db.init()

    bot = Client(
        "musicem_bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        plugins=dict(root="plugins"),
        workers=32,
        parse_mode=None,
        sleep_threshold=30,
    )
    runtime.bot = bot

    assistant = None
    if config.VOICE_CHAT:
        assistant = Client(
            "musicem_assistant",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=config.SESSION_STRING,
            workers=16,
            parse_mode=None,
        )
        runtime.assistant = assistant
        runtime.player = Player(assistant)
        runtime.player.notifier = on_player_event

    log.info("menghubungkan bot…")
    await bot.start()
    me = await bot.get_me()
    log.info("bot online: @%s (%s)", me.username, me.first_name)

    if config.VOICE_CHAT:
        log.info("menghubungkan assistant…")
        await assistant.start()
        ame = await assistant.get_me()
        log.info("assistant online: %s (%s)", ame.first_name, ame.id)
        await runtime.player.start()
    else:
        log.info("MODE FILE aktif — /play & /vplay kirim file, tanpa voice chat")

    await register_commands(bot)

    asyncio.create_task(housekeeping())

    if config.LOG_CHANNEL:
        try:
            await bot.send_message(config.LOG_CHANNEL, f"✅ @{me.username} online.")
        except Exception:
            pass

    stop = asyncio.Event()

    def _stop(*_):
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    await stop.wait()
    log.info("mematikan bot…")
    if config.VOICE_CHAT and runtime.player:
        await runtime.player.stop()
    if assistant is not None:
        await assistant.stop()
    await bot.stop()


def choose_mode() -> str:
    if config.MODE in {"lite", "full"}:
        return config.MODE
    return "full" if not config.missing() else "lite"


if __name__ == "__main__":
    mode = choose_mode()
    if mode == "lite" and config.missing():
        log.warning(
            "kredensial belum lengkap (%s) — jalan di MODE LITE. "
            "Streaming voice chat butuh API_ID/API_HASH + SESSION_STRING.",
            ", ".join(config.missing()),
        )
    try:
        if mode == "lite":
            from lite import run as run_lite

            asyncio.run(run_lite())
        else:
            if config.missing():
                fail_missing()
            asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # tampilkan error awal dengan jelas
        log.error("startup gagal: %s", exc, exc_info=config.DEBUG)
        sys.exit(1)
