"""Mode lite: jalan hanya dengan BOT_TOKEN (Bot API HTTP, tanpa API_ID/session).

Dipakai kalau kredensial MTProto (API_ID/API_HASH/SESSION_STRING) belum ada.
Streaming voice chat tetap butuh mode penuh; di sini bot bisa:
/start, /help, /song, /play (kirim audio ke chat), /search, /ping, /id.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import config
import database as db
import strings as S
from downloader import DownloadError, Track, download, search, to_mp3

from utils import esc, human_time, is_url, progress_bar, shorten

log = logging.getLogger("musicem.lite")

API_BASE = "https://api.telegram.org/bot{token}/{method}"
HTML = "HTML"
MAX_CAPTION = 1000


class ApiError(RuntimeError):
    def __init__(self, method: str, payload: dict) -> None:
        self.method = method
        super().__init__(f"{method}: {payload.get('description')} ({payload.get('error_code')})")


@dataclass
class User:
    id: int
    first_name: str = "User"
    username: str | None = None


@dataclass
class Chat:
    id: int
    type: str = "private"
    title: str | None = None


def _user(raw: dict | None) -> User | None:
    if not raw:
        return None
    return User(
        id=raw.get("id", 0),
        first_name=raw.get("first_name") or raw.get("title") or "User",
        username=raw.get("username"),
    )


def _chat(raw: dict | None) -> Chat:
    raw = raw or {}
    return Chat(id=raw.get("id", 0), type=raw.get("type", "private"), title=raw.get("title"))


class LiteBot:
    def __init__(self, token: str) -> None:
        self.token = token
        self.session: aiohttp.ClientSession | None = None
        self.me: User | None = None
        self.username = ""
        self._offset = 0
        self._tasks: set[asyncio.Task] = set()
        self._running = False
        self._message_handlers: list[tuple[tuple[str, ...], object]] = []
        self._callback_handlers: list[tuple[str, object]] = []
        self._search_cache: dict[str, tuple[float, list[Track]]] = {}

    # ── HTTP ────────────────────────────────────────────────────────────
    async def call(self, method: str, **params):
        assert self.session is not None
        url = API_BASE.format(token=self.token, method=method)
        for attempt in range(3):
            try:
                async with self.session.post(url, json=params, timeout=70) as resp:
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == 2:
                    raise ApiError(method, {"description": str(exc)}) from exc
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if data.get("ok"):
                return data.get("result")
            code = data.get("error_code", 0)
            if code == 429:
                retry = data.get("parameters", {}).get("retry_after", 3)
                await asyncio.sleep(min(retry, 20))
                continue
            raise ApiError(method, data)
        raise ApiError(method, {"description": "retry habis"})

    async def call_multipart(self, method: str, form: aiohttp.FormData):
        assert self.session is not None
        url = API_BASE.format(token=self.token, method=method)
        async with self.session.post(url, data=form, timeout=300) as resp:
            data = await resp.json(content_type=None)
        if not data.get("ok"):
            raise ApiError(method, data)
        return data.get("result")

    # ── lifecycle ───────────────────────────────────────────────────────
    async def start(self) -> None:
        self.session = aiohttp.ClientSession()
        me = await self.call("getMe")
        self.me = _user(me)
        self.username = me.get("username", "")
        try:
            await self.call("deleteWebhook", drop_pending_updates=False)
        except ApiError:
            pass
        self._running = True
        self._tasks.add(asyncio.create_task(self._poll()))
        log.info("mode lite aktif sebagai @%s", self.username)

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self.session:
            await self.session.close()

    async def _poll(self) -> None:
        while self._running:
            try:
                updates = await self.call(
                    "getUpdates",
                    offset=self._offset,
                    timeout=30,
                    allowed_updates=["message", "callback_query"],
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("polling error: %s", exc)
                await asyncio.sleep(3)
                continue
            for upd in updates or []:
                self._offset = max(self._offset, upd.get("update_id", 0) + 1)
                task = asyncio.create_task(self._dispatch(upd))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    async def _dispatch(self, update: dict) -> None:
        try:
            if "message" in update:
                msg = Message(self, update["message"])
                text = msg.text or ""
                cmd = None
                if text.startswith("/"):
                    cmd = text.split()[0][1:].split("@")[0].lower()
                for commands, handler in self._message_handlers:
                    if cmd and cmd in commands:
                        await handler(msg)
                        return
            elif "callback_query" in update:
                cq = CallbackQuery(self, update["callback_query"])
                for prefix, handler in self._callback_handlers:
                    if (cq.data or "").startswith(prefix):
                        await handler(cq)
                        return
                await cq.answer()
        except Exception as exc:
            log.error("handler error: %s", exc, exc_info=config.DEBUG)

    # ── registrasi handler ──────────────────────────────────────────────
    def on_message(self, commands: list[str]):
        def decorator(func):
            self._message_handlers.append((tuple(commands), func))
            return func

        return decorator

    def on_callback(self, prefix: str):
        def decorator(func):
            self._callback_handlers.append((prefix, func))
            return func

        return decorator


class Message:
    def __init__(self, bot: LiteBot, raw: dict) -> None:
        self.bot = bot
        self.raw = raw
        self.message_id: int = raw.get("message_id", 0)
        self.chat = _chat(raw.get("chat"))
        self.from_user = _user(raw.get("from"))
        self.text: str = raw.get("text") or raw.get("caption") or ""
        self.reply_to_message = (
            Message(bot, raw["reply_to_message"]) if raw.get("reply_to_message") else None
        )

    async def reply_text(self, text: str, **kwargs) -> "Message":
        result = await self.bot.call(
            "sendMessage",
            chat_id=self.chat.id,
            text=text,
            **_clean(kwargs),
        )
        return Message(self.bot, result)

    async def edit_text(self, text: str, **kwargs) -> "Message":
        try:
            result = await self.bot.call(
                "editMessageText",
                chat_id=self.chat.id,
                message_id=self.message_id,
                text=text,
                **_clean(kwargs),
            )
            return Message(self.bot, result)
        except ApiError as exc:
            if "not modified" in str(exc):
                return self
            raise

    async def edit_reply_markup(self, reply_markup=None) -> None:
        await self.bot.call(
            "editMessageReplyMarkup",
            chat_id=self.chat.id,
            message_id=self.message_id,
            reply_markup=_markup(reply_markup),
        )

    async def delete(self) -> None:
        await self.bot.call("deleteMessage", chat_id=self.chat.id, message_id=self.message_id)

    async def reply_audio(self, path: str, **kwargs) -> "Message":
        form = aiohttp.FormData()
        form.add_field("chat_id", str(self.chat.id))
        for key in ("title", "performer", "caption"):
            if kwargs.get(key):
                form.add_field(key, str(kwargs[key])[:MAX_CAPTION])
        if kwargs.get("duration"):
            form.add_field("duration", str(int(kwargs["duration"])))
        if kwargs.get("parse_mode"):
            form.add_field("parse_mode", str(kwargs["parse_mode"]))
        p = Path(path)
        form.add_field(
            "audio",
            p.read_bytes(),
            filename=p.name,
            content_type="audio/mpeg",
        )
        result = await self.bot.call_multipart("sendAudio", form)
        return Message(self.bot, result)


class CallbackQuery:
    def __init__(self, bot: LiteBot, raw: dict) -> None:
        self.bot = bot
        self.raw = raw
        self.id: str = raw.get("id", "")
        self.data: str = raw.get("data") or ""
        self.from_user = _user(raw.get("from"))
        self.message = Message(bot, raw["message"]) if raw.get("message") else None

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        try:
            await self.bot.call(
                "answerCallbackQuery",
                callback_query_id=self.id,
                text=text[:200],
                show_alert=show_alert,
            )
        except ApiError as exc:
            log.debug("answer cb: %s", exc)


def _clean(kwargs: dict) -> dict:
    kwargs.pop("disable_web_page_preview", None)
    if "reply_markup" in kwargs:
        kwargs["reply_markup"] = _markup(kwargs["reply_markup"])
    return {k: v for k, v in kwargs.items() if v is not None}


def _markup(markup) -> dict | None:
    return markup if isinstance(markup, dict) else None


def kb(rows: list[list[tuple[str, str]]]) -> dict:
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": data} for text, data in row] for row in rows
        ]
    }


# ── UI helper ───────────────────────────────────────────────────────────


def start_text() -> str:
    return (
        S.START
        + "\n\n⚠️ <b>Mode lite</b>: streaming voice chat belum aktif.\n"
        "Isi <code>API_ID</code>, <code>API_HASH</code>, dan <code>SESSION_STRING</code> "
        "di <code>.env</code> lalu restart untuk mode penuh."
    )


def register(bot: LiteBot) -> None:
    """Daftarkan seluruh handler mode lite ke bot."""
    def user_tag(user: User | None) -> str:
        if not user:
            return "Unknown"
        return f'<a href="tg://user?id={user.id}">{esc(user.first_name)}</a>'

    def progress_loop(msg: Message, track: Track, stats: dict) -> asyncio.Task:
        async def worker():
            while stats.get("running"):
                await asyncio.sleep(4)
                if not stats.get("running"):
                    break
                done, total = stats.get("done", 0), stats.get("total", 0)
                if total <= 0:
                    continue
                try:
                    await msg.edit_text(
                        S.DOWNLOADING.format(
                            title=esc(track.title), bar=progress_bar(done, total),
                            pct=int(done * 100 / total),
                        ),
                        parse_mode=HTML,
                    )
                except Exception:
                    pass

        return asyncio.create_task(worker())

    async def send_track(msg: Message, track: Track, video: bool = False) -> None:
        stats = {"running": True, "done": 0, "total": 0}

        def hook(d: dict) -> None:
            if d.get("status") == "downloading":
                stats["done"] = d.get("downloaded_bytes") or 0
                stats["total"] = d.get("total_bytes") or d.get("total_bytes_estimate") or 0

        poll = progress_loop(msg, track, stats)
        try:
            await msg.edit_text(
                S.DOWNLOADING.format(title=esc(track.title), bar=progress_bar(0, 1), pct=0),
                parse_mode=HTML,
            )
            await download(track, is_video=video, progress=hook)
        except DownloadError as exc:
            await msg.edit_text(S.ERROR.format(err=esc(str(exc)[:250])), parse_mode=HTML)
            stats["running"] = False
            poll.cancel()
            return
        stats["running"] = False
        poll.cancel()

        size = Path(track.filepath).stat().st_size if track.filepath else 0
        if size > 49 * 1024 * 1024:
            await msg.edit_text(
                f"⚠️ File <code>{size / 1e6:.1f} MB</code> melebihi limit upload bot (50 MB).\n"
                f"Link: {esc(track.url)}",
                parse_mode=HTML,
            )
            return

        await msg.edit_text(
            f"📤 Upload <b>{esc(track.short)}</b>…", parse_mode=HTML
        )
        try:
            upload_path = await to_mp3(track.filepath)
            await msg.reply_audio(
                upload_path,
                title=track.title,
                performer=track.uploader or "Unknown",
                duration=track.duration,
                caption=(
                    f"🎵 <b>{esc(track.short)}</b>\n⏱ <code>{human_time(track.duration)}</code>"
                ),
                parse_mode=HTML,
            )
        except ApiError as exc:
            await msg.edit_text(S.ERROR.format(err=esc(str(exc)[:250])), parse_mode=HTML)
            return
        except Exception as exc:
            await msg.edit_text(
                S.ERROR.format(err=esc(f"upload gagal: {str(exc)[:200]}")), parse_mode=HTML
            )
            return
        await db.bump("downloads")
        try:
            await msg.delete()
        except Exception:
            pass

    # ── handlers ────────────────────────────────────────────────────────
    @bot.on_message(["start", "help"])
    async def cmd_start(msg: Message) -> None:
        if msg.from_user:
            await db.add_user(msg.from_user.id, msg.from_user.first_name, msg.from_user.username)
        command = msg.text.split()[0][1:].split("@")[0].lower()
        text = S.HELP if command == "help" else start_text()
        await msg.reply_text(
            text,
            parse_mode=HTML,
            reply_markup=kb(
                [
                    [("➕ Tambah ke Grup", f"https://t.me/{bot.username}?startgroup=true")],
                    [("📖 Perintah", "help"), ("🎵 Cari Lagu", "help")],
                ]
            ),
        )

    @bot.on_message(["ping", "alive"])
    async def cmd_ping(msg: Message) -> None:
        t0 = time.perf_counter()
        sent = await msg.reply_text("🏓", parse_mode=HTML)
        ms = (time.perf_counter() - t0) * 1000
        await sent.edit_text(f"🏓 <b>Pong!</b> <code>{ms:.0f} ms</code>", parse_mode=HTML)

    @bot.on_message(["id"])
    async def cmd_id(msg: Message) -> None:
        lines = [f"💬 <b>Chat</b>: <code>{msg.chat.id}</code>"]
        if msg.from_user:
            lines.append(f"👤 <b>User</b>: <code>{msg.from_user.id}</code>")
        await msg.reply_text("\n".join(lines), parse_mode=HTML)

    @bot.on_message(["song", "play", "vplay", "download", "dl"])
    async def cmd_song(msg: Message) -> None:
        parts = msg.text.split(None, 1)
        if len(parts) < 2 or not parts[1].strip():
            await msg.reply_text(S.NO_QUERY, parse_mode=HTML)
            return
        query = parts[1].strip()
        status = await msg.reply_text(
            S.SEARCHING.format(q=esc(shorten(query, 50))), parse_mode=HTML
        )
        try:
            results = await search(query, 1 if is_url(query) else 5)
        except DownloadError as exc:
            await status.edit_text(S.ERROR.format(err=esc(str(exc)[:250])), parse_mode=HTML)
            return
        if not results:
            await status.edit_text(S.NOT_FOUND.format(q=esc(shorten(query, 50))), parse_mode=HTML)
            return
        if len(results) == 1:
            await send_track(status, results[0])
            return
        token = f"{msg.message_id:x}"
        bot._search_cache[token] = (time.time(), results)
        rows = [
            [(f"{i + 1}. {shorten(r.title, 40)} • {human_time(r.duration)}", f"pick:{token}:{i}")]
            for i, r in enumerate(results)
        ]
        rows.append([("❌ Batal", f"pick:{token}:x")])
        await status.edit_text(
            S.SEARCH_RESULTS.format(q=esc(shorten(query, 50))),
            parse_mode=HTML,
            reply_markup=kb(rows),
        )

    @bot.on_callback("pick:")
    async def on_pick(cq: CallbackQuery) -> None:
        try:
            _, token, raw_idx = cq.data.split(":")
        except ValueError:
            await cq.answer()
            return
        if raw_idx == "x":
            try:
                await cq.message.delete()
            except Exception:
                pass
            await cq.answer("Dibatalkan")
            return
        row = bot._search_cache.get(token)
        if not row or time.time() - row[0] > 600:
            await cq.answer("Hasil kedaluwarsa, ulangi /song.", show_alert=True)
            return
        try:
            track = row[1][int(raw_idx)]
        except (ValueError, IndexError):
            await cq.answer("Pilihan tidak valid.", show_alert=True)
            return
        await cq.answer("Diproses…")
        await send_track(cq.message, track)

    @bot.on_callback("help")
    async def on_help(cq: CallbackQuery) -> None:
        try:
            await cq.message.edit_text(S.HELP, parse_mode=HTML)
        except Exception:
            pass
        await cq.answer()


async def run() -> None:
    """Jalankan bot mode lite sampai dihentikan."""
    bot = LiteBot(config.BOT_TOKEN)
    register(bot)
    await db.init()
    await bot.start()
    stop = asyncio.Event()
    import signal

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    try:
        await stop.wait()
    finally:
        log.info("mematikan mode lite…")
        await bot.stop()
