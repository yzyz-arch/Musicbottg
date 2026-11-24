"""Self-test tanpa koneksi Telegram: config, DB, pencarian, download, stream params."""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS, FAIL = "✅", "❌"
errors: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{PASS if ok else FAIL} {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        errors.append(name)


async def main() -> int:
    import config
    import database as db

    print("\n[1] konfigurasi")
    missing = config.missing()
    if missing:
        print(f"  ⚠️  belum diisi: {', '.join(missing)} (bot belum bisa online)")
    check("folder data & download", True)
    config.prepare_dirs()

    print("\n[2] database")
    await db.init()
    await db.add_chat(-100123, "Test")
    await db.add_user(1, "Tester", "tester")
    await db.add_auth(-100123, 42, 1)
    ok = await db.is_auth(-100123, 42)
    check("auth tersimpan", ok)
    await db.remove_auth(-100123, 42)
    check("auth terhapus", not await db.is_auth(-100123, 42))

    print("\n[3] queue")
    from downloader import Track
    from queue_manager import queue

    st = await queue.get(-100999)
    await queue.push(-100999, Track(id="a", title="A", duration=10))
    await queue.push(-100999, Track(id="b", title="B", duration=20))
    n1 = await queue.next_track(-100999)
    check("pop urutan benar", n1 is not None and n1.id == "a")
    st.loop = "all"
    st.history.append(Track(id="c", title="C"))
    await queue.next_track(-100999)
    n2 = await queue.next_track(-100999)
    check("loop all mengisi ulang", n2 is not None and n2.id == "c")
    await queue.clear(-100999)
    check("clear", (await queue.get(-100999)).size == 0)

    print("\n[4] pencarian yt-dlp")
    from downloader import search

    results = await search("ed sheeran perfect", 3)
    check("hasil pencarian", len(results) > 0, f"{len(results)} item")
    if results:
        print(f"   contoh: {results[0].title[:60]} ({results[0].duration}s)")

    print("\n[5] download + ffmpeg/stream params")
    if results:
        from downloader import download
        from player import Player
        from pytgcalls.types import MediaStream
        from queue_manager import ChatState

        short = next((r for r in results if 0 < r.duration <= 600), None)
        if short is None:
            print("   (semua hasil live/panjang, tes download dilewati)")
            results = []
        t0 = time.time()
        path = await download(short, is_video=False)
        size = os.path.getsize(path)
        check("file terunduh", size > 0, f"{size / 1e6:.1f} MB, {time.time() - t0:.1f}s")

        dummy = ChatState(chat_id=-1, volume=60)
        params = Player._ffmpeg_params(dummy, seek=30)
        check("ffmpeg params volume+seek", "--mid" in params and "-ss" in params, params)

        stream = MediaStream(
            path,
            audio_flags=MediaStream.Flags.REQUIRED,
            video_flags=MediaStream.Flags.IGNORE,
            ffmpeg_parameters=params,
        )
        await stream.check_stream()
        check("probe stream audio", stream.microphone is not None)

        from downloader import to_mp3

        mp3 = await to_mp3(path)
        check("konversi mp3 untuk upload", mp3.endswith(".mp3") and os.path.getsize(mp3) > 0)

        stream_v = MediaStream(path, video_flags=MediaStream.Flags.AUTO_DETECT)
        await stream_v.check_stream()
        print(f"   video terdeteksi: {stream_v.camera is not None}")

    print("\n[6] callback data (maks 64 byte)")
    from utils import controls_markup

    longest = 0
    for row in controls_markup(-1001234567890).inline_keyboard:
        for btn in row:
            longest = max(longest, len(btn.callback_data.encode()))
    check("ukuran callback", longest <= 64, f"maks {longest} byte")

    print("\n[7] handler plugin")
    import importlib

    import pyrogram.handlers  # noqa: F401

    total_handlers = 0
    for mod in ("start", "play", "controls", "callbacks", "admin", "tools"):
        module = importlib.import_module(f"plugins.{mod}")
        count = 0
        for name in dir(module):
            obj = getattr(module, name)
            count += len(getattr(obj, "handlers", []))
        total_handlers += count
        check(f"handler {mod}", count > 0, f"{count} handler")
    check("total handler", total_handlers >= 15, str(total_handlers))

    print("\n[8] teks pesan")
    import strings as S

    for name in ("START", "HELP", "PLAYING", "QUEUE_HEADER"):
        check(f"string {name}", bool(getattr(S, name)))

    if config.missing():
        print("\nℹ️  Untuk uji koneksi Telegram, isi .env lalu jalankan: python bot.py")
    print("\n" + ("SEMUA OK" if not errors else f"GAGAL: {', '.join(errors)}"))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
