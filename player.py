"""Mesin playback: PyTgCalls + pengelolaan stream."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

import config
import ntgcalls
from downloader import Track
from pyrogram import Client
from pytgcalls import PyTgCalls, filters
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError
from pytgcalls.types import (
    AudioQuality,
    Direction,
    MediaStream,
    StreamEnded,
    Update,
    VideoQuality,
)
from queue_manager import ChatState, queue

log = logging.getLogger("musicem.player")


class PlayerError(RuntimeError):
    pass


class Player:
    def __init__(self, assistant: Client) -> None:
        self.assistant = assistant
        self.calls = PyTgCalls(assistant)
        self.notifier: Callable[[int, str, Track | None, str], Awaitable[None]] | None = None
        self._started = False
        self._guard: dict[int, float] = {}

    # ── lifecycle ───────────────────────────────────────────────────────
    async def start(self) -> None:
        await self.calls.start()
        self.calls.on_update(filters.stream_end)(self._on_stream_end)
        self._started = True
        log.info("py-tgcalls siap")

    async def stop(self) -> None:
        try:
            await self.calls.stop()
        except Exception:
            pass
        self._started = False

    def _guard_end(self, chat_id: int, seconds: float = 2.0) -> None:
        self._guard[chat_id] = time.monotonic() + seconds

    async def _notify(self, chat_id: int, event: str, track: Track | None, text: str = "") -> None:
        if self.notifier:
            try:
                await self.notifier(chat_id, event, track, text)
            except Exception as exc:
                log.warning("notifier error (%s): %s", event, exc)

    # ── stream params ───────────────────────────────────────────────────
    @staticmethod
    def _ffmpeg_params(state: ChatState, seek: float = 0) -> str:
        parts: list[str] = []
        if seek > 0:
            parts += ["-ss", str(int(seek))]
        if state.volume != 100:
            parts += ["--mid", "-af", f"volume={state.volume / 100:.2f}"]
        return " ".join(parts)

    async def _stream(self, state: ChatState, track: Track, seek: float = 0) -> MediaStream:
        if not track.filepath:
            raise PlayerError("File track tidak ada.")
        params = self._ffmpeg_params(state, seek)
        kwargs = dict(
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.HD_720p,
            ffmpeg_parameters=params or None,
        )
        if state.video:
            return MediaStream(track.filepath, **kwargs)
        return MediaStream(
            track.filepath,
            audio_flags=MediaStream.Flags.REQUIRED,
            video_flags=MediaStream.Flags.IGNORE,
            **kwargs,
        )

    # ── playback ────────────────────────────────────────────────────────
    async def play(self, chat_id: int, track: Track, video: bool = False, seek: float = 0) -> None:
        """Putar track sebagai lagu aktif (bukan antrean)."""
        state = await queue.get(chat_id)
        async with state.lock:
            track.is_video = video
            state.video = video
            state.generation += 1
            self._guard_end(chat_id)
            state.current = track
            state.active = True
            state.paused = False
            state.offset = seek
            state.playing_since = time.monotonic()
            stream = await self._stream(state, track, seek)
            try:
                # Telegram kadang balas 500 saat join; satu retry biasanya cukup
                for attempt in range(2):
                    try:
                        await self.calls.play(chat_id, stream)
                        break
                    except ntgcalls.TelegramServerError:
                        if attempt == 1:
                            raise
                        await asyncio.sleep(5)
            except NoActiveGroupCall as exc:
                state.current = None
                state.active = False
                raise PlayerError("no_group_call") from exc
            except Exception as exc:
                state.current = None
                state.active = False
                raise PlayerError(str(exc)) from exc
        if state.leave_task:
            state.leave_task.cancel()
            state.leave_task = None

    async def start_queue(self, chat_id: int, track: Track, video: bool = False) -> None:
        state = await queue.get(chat_id)
        state.history.append(track)
        await self.play(chat_id, track, video)

    async def pause(self, chat_id: int) -> bool:
        state = await queue.get(chat_id)
        if not state.active:
            return False
        await self.calls.pause(chat_id)
        state.paused = True
        state.offset += time.monotonic() - state.playing_since
        return True

    async def resume(self, chat_id: int) -> bool:
        state = await queue.get(chat_id)
        if not state.active or not state.paused:
            return False
        await self.calls.resume(chat_id)
        state.paused = False
        state.playing_since = time.monotonic()
        return True

    async def seek(self, chat_id: int, seconds: float) -> bool:
        state = await queue.get(chat_id)
        if not state.active or not state.current:
            return False
        seconds = max(0.0, seconds)
        if state.current.duration and seconds >= state.current.duration:
            return False
        paused = state.paused
        await self.play(chat_id, state.current, state.video, seek=seconds)
        if paused:
            await self.pause(chat_id)
        return True

    async def set_volume(self, chat_id: int, volume: int) -> int:
        state = await queue.get(chat_id)
        state.volume = max(1, min(200, volume))
        if state.active and state.current:
            pos = await self.elapsed(chat_id)
            was_paused = state.paused
            await self.play(chat_id, state.current, state.video, seek=pos)
            if was_paused:
                await self.pause(chat_id)
        return state.volume

    async def elapsed(self, chat_id: int) -> float:
        state = await queue.get(chat_id)
        if not state.active:
            return 0.0
        if state.paused:
            return state.offset
        return state.offset + max(0.0, time.monotonic() - state.playing_since)

    async def skip(self, chat_id: int) -> Track | None:
        state = await queue.get(chat_id)
        async with state.lock:
            state.generation += 1
            self._guard_end(chat_id)
            return await self._advance_locked(state, force=True)

    async def prev(self, chat_id: int) -> Track | None:
        state = await queue.get(chat_id)
        if not state.history:
            return None
        track = state.history.pop()
        current = state.current
        state.generation += 1
        await self.play(chat_id, track, track.is_video)
        if current:
            state.queue.appendleft(current)
        return track

    async def end(self, chat_id: int) -> None:
        state = await queue.get(chat_id)
        async with state.lock:
            state.generation += 1
            state.active = False
            state.paused = False
            state.current = None
            state.queue.clear()
            state.history.clear()
        try:
            await self.calls.leave_call(chat_id)
        except (NotInCallError, NoActiveGroupCall):
            pass
        except Exception as exc:
            log.debug("leave_call error: %s", exc)

    async def _advance_locked(self, state: ChatState, force: bool = False) -> Track | None:
        current = state.current
        if current:
            if state.loop != "one":
                state.history.append(current)
        nxt = await queue.next_track(state.chat_id, force=force)
        if not nxt:
            state.current = None
            state.active = False
            state.paused = False
            state.offset = 0
            await self._leave_later(state)
            await self._notify(state.chat_id, "empty", None)
            return None
        state.current = nxt
        self._guard_end(state.chat_id)
        state.video = nxt.is_video
        state.active = True
        state.paused = False
        state.offset = 0
        state.playing_since = time.monotonic()
        stream = await self._stream(state, nxt, 0)
        try:
            await self.calls.play(state.chat_id, stream)
        except Exception as exc:
            log.warning("play next failed: %s", exc)
            state.current = None
            state.active = False
            await self._notify(state.chat_id, "error", nxt, str(exc))
            return None
        await self._notify(state.chat_id, "next", nxt)
        return nxt

    async def _leave_later(self, state: ChatState) -> None:
        if config.LEAVE_TIMEOUT <= 0:
            await self._leave_now(state.chat_id)
            return

        async def waiter():
            await asyncio.sleep(config.LEAVE_TIMEOUT)
            st = await queue.get(state.chat_id)
            if not st.active and st.size == 0:
                await self._leave_now(state.chat_id)

        state.leave_task = asyncio.create_task(waiter())

    async def _leave_now(self, chat_id: int) -> None:
        try:
            await self.calls.leave_call(chat_id)
        except (NotInCallError, NoActiveGroupCall):
            pass
        except Exception as exc:
            log.debug("leave error: %s", exc)
        state = await queue.get(chat_id)
        state.active = False
        state.current = None

    # ── event dari ntgcalls ─────────────────────────────────────────────
    async def _on_stream_end(self, _client: PyTgCalls, update: Update) -> None:
        if not isinstance(update, StreamEnded):
            return
        if update.stream_type & StreamEnded.Type.VIDEO and not (
            update.stream_type & StreamEnded.Type.AUDIO
        ):
            return
        if time.monotonic() < self._guard.get(update.chat_id, 0):
            return
        state = await queue.get(update.chat_id)
        if not state.active:
            return
        async with state.lock:
            if not state.active:
                return
            await self._advance_locked(state)

    async def position(self, chat_id: int) -> float:
        """Posisi stream dari server (fallback ke timer lokal)."""
        try:
            ns = await self.calls.time(chat_id, Direction.OUTGOING)
            if ns:
                return ns / 1_000_000_000
        except Exception:
            pass
        return await self.elapsed(chat_id)
