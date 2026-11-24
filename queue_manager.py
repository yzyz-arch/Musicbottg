"""State antrean per chat."""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field

import config
from downloader import Track


@dataclass
class ChatState:
    chat_id: int
    queue: deque[Track] = field(default_factory=deque)
    history: deque[Track] = field(default_factory=lambda: deque(maxlen=20))
    current: Track | None = None
    loop: str = "off"          # off | one | all
    paused: bool = False
    volume: int = config.DEFAULT_VOLUME
    playing_since: float = 0.0  # monotonic saat stream mulai
    offset: float = 0.0         # detik yang sudah dilewati (seek/pause)
    video: bool = False
    active: bool = False
    generation: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    leave_task: asyncio.Task | None = None
    panel_chat: int | None = None
    panel_id: int | None = None

    @property
    def size(self) -> int:
        return len(self.queue)


class QueueManager:
    def __init__(self) -> None:
        self._states: dict[int, ChatState] = {}
        self._lock = asyncio.Lock()

    async def get(self, chat_id: int) -> ChatState:
        async with self._lock:
            state = self._states.get(chat_id)
            if state is None:
                state = ChatState(chat_id=chat_id)
                self._states[chat_id] = state
            return state

    async def drop(self, chat_id: int) -> None:
        async with self._lock:
            self._states.pop(chat_id, None)

    def all_states(self) -> list[ChatState]:
        return list(self._states.values())

    async def push(self, chat_id: int, track: Track) -> int:
        state = await self.get(chat_id)
        if len(state.queue) >= config.QUEUE_LIMIT:
            raise ValueError("queue_full")
        state.queue.append(track)
        return len(state.queue)

    async def next_track(self, chat_id: int, force: bool = False) -> Track | None:
        state = await self.get(chat_id)
        if not force and state.loop == "one" and state.current:
            return state.current
        if state.queue:
            nxt = state.queue.popleft()
            return nxt
        if state.loop == "all" and state.history:
            state.queue.extend(state.history)
            state.history.clear()
            if state.queue:
                return state.queue.popleft()
        return None

    async def clear(self, chat_id: int) -> None:
        state = await self.get(chat_id)
        state.queue.clear()
        state.history.clear()
        state.current = None
        state.paused = False
        state.active = False
        state.generation += 1


queue = QueueManager()
