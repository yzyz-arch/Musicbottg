"""Cari & download media pakai yt-dlp (jalan di thread pool)."""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import config
import yt_dlp

from utils import is_url

log = logging.getLogger("musicem.downloader")

_NAME_SANITIZE = re.compile(r"[^\w\s.-]")


@dataclass(slots=True)
class Track:
    id: str
    title: str
    duration: int = 0
    url: str = ""
    thumbnail: str | None = None
    uploader: str | None = None
    requested_by: int = 0
    requester_name: str = ""
    is_video: bool = False
    is_live: bool = False
    filepath: str | None = None
    extra: dict = field(default_factory=dict)

    @property
    def short(self) -> str:
        return self.title if len(self.title) <= 55 else self.title[:54] + "…"


class DownloadError(RuntimeError):
    pass


AUDIO_READY = {".mp3", ".m4a", ".aac", ".ogg", ".flac", ".wav"}


def _to_mp3_sync(path: str) -> str:
    """Telegram sendAudio hanya menerima mp3/m4a — konversi kalau perlu."""
    src = Path(path)
    if src.suffix.lower() in AUDIO_READY:
        return str(src)
    out = src.with_suffix(".mp3")
    if out.exists() and out.stat().st_size > 0:
        return str(out)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-vn", "-ar", "44100", "-b:a", "192k", str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise DownloadError(f"gagal konversi ke mp3: {exc}") from exc
    if not out.exists():
        raise DownloadError("konversi mp3 gagal (file kosong)")
    return str(out)


async def to_mp3(path: str) -> str:
    return await asyncio.to_thread(_to_mp3_sync, path)


def _cookie_opts() -> dict:
    if config.COOKIES_FILE.is_file():
        return {"cookiefile": str(config.COOKIES_FILE)}
    return {}


def _base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "source_address": "0.0.0.0",
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 20,
        "nocheckcertificate": True,
    }
    opts.update(_cookie_opts())
    return opts


SEARCH_OPTS = {
    **_base_opts(),
    "extract_flat": "in_playlist",
    "skip_download": True,
}


def _search_sync(query: str, limit: int) -> list[Track]:
    opts = dict(SEARCH_OPTS)
    target = query if is_url(query) else f"ytsearch{limit}:{query}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target, download=False)

    entries = info.get("entries") if "entries" in info else [info]
    out: list[Track] = []
    for item in entries or []:
        if not item:
            continue
        video_id = item.get("id") or ""
        if not video_id:
            continue
        if item.get("_type") == "url" and "youtube.com" in (item.get("url") or ""):
            video_id = item.get("url", "").split("v=")[-1]
        out.append(
            Track(
                id=video_id,
                title=item.get("title") or video_id,
                duration=int(item.get("duration") or 0),
                url=item.get("webpage_url") or f"https://youtu.be/{video_id}",
                thumbnail=item.get("thumbnail"),
                uploader=item.get("uploader") or item.get("channel"),
                is_live=bool(item.get("is_live")),
            )
        )
        if len(out) >= limit:
            break
    return out


async def search(query: str, limit: int | None = None) -> list[Track]:
    limit = limit or config.SEARCH_LIMIT
    try:
        return await asyncio.to_thread(_search_sync, query.strip(), limit)
    except Exception as exc:  # yt-dlp melempar banyak tipe error
        log.warning("search failed for %r: %s", query, exc)
        raise DownloadError(str(exc)) from exc


def _find_cached(video_id: str, is_video: bool = False) -> Path | None:
    prefixes = [f"{video_id}.v." if is_video else f"{video_id}.a."]
    if not is_video:
        # audio boleh pakai file video (audio-nya tetap bisa diputar)
        prefixes += [f"{video_id}.v.", f"{video_id}."]
    for prefix in prefixes:
        for path in config.DOWNLOAD_DIR.glob(prefix + "*"):
            if path.suffix in {".part", ".ytdl"}:
                continue
            if path.stat().st_size > 0:
                return path
    return None


def cleanup_cache() -> int:
    """Hapus file download yang lebih tua dari CACHE_TTL."""
    if config.CACHE_TTL <= 0:
        return 0
    cutoff = time.time() - config.CACHE_TTL
    removed = 0
    for path in config.DOWNLOAD_DIR.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue
    return removed


def _download_sync(
    track: Track,
    is_video: bool,
    progress=None,
    max_filesize: int | None = None,
) -> str:
    config.prepare_dirs()
    cached = _find_cached(track.id, is_video)
    if cached:
        track.filepath = str(cached)
        return str(cached)

    if is_video:
        fmt = (
            f"bv*[height<={config.VIDEO_HEIGHT}][ext=mp4]+ba[ext=m4a]/"
            f"b[height<={config.VIDEO_HEIGHT}][ext=mp4]/"
            f"bv*[height<={config.VIDEO_HEIGHT}]+ba/b"
        )
        merge = "mp4"
    else:
        fmt = "bestaudio[acodec=opus]/bestaudio[ext=m4a]/bestaudio/best"
        merge = None

    kind = "v" if is_video else "a"
    outtmpl = str(config.DOWNLOAD_DIR / f"{track.id}.{kind}.%(ext)s")
    opts = {
        **_base_opts(),
        "format": fmt,
        "outtmpl": outtmpl,
        "restrictfilenames": True,
        "overwrites": False,
        "max_filesize": max_filesize or config.MAX_FILESIZE,
        "progress_hooks": [progress] if progress else [],
    }
    if merge:
        opts["merge_output_format"] = merge
    if re.match(r"^https?://", track.url or "", re.I):
        target = track.url
    else:
        target = track.id

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target, download=True)

    # yt-dlp bisa mengembalikan playlist; ambil file pertama yang cocok
    candidate = None
    if info:
        if info.get("requested_downloads"):
            candidate = info["requested_downloads"][0].get("filepath")
        candidate = candidate or info.get("filepath")
    if not candidate or not Path(candidate).exists():
        cached = _find_cached(track.id, is_video)
        candidate = str(cached) if cached else None
    if not candidate:
        raise DownloadError("File hasil download tidak ditemukan.")

    track.filepath = candidate
    track.duration = int(info.get("duration") or track.duration or 0)
    track.title = info.get("title") or track.title
    track.thumbnail = info.get("thumbnail") or track.thumbnail
    return candidate


async def download(
    track: Track,
    is_video: bool = False,
    progress=None,
    max_filesize: int | None = None,
) -> str:
    async with _slot():
        try:
            path = await asyncio.to_thread(
                _download_sync, track, is_video, progress, max_filesize
            )
            track.filepath = path
            return path
        except Exception as exc:
            log.warning("download failed for %s: %s", track.id, exc)
            raise DownloadError(str(exc)) from exc


class _slot:
    """Batasi jumlah download paralel (default 3)."""

    _sem: asyncio.Semaphore | None = None

    async def __aenter__(self):
        if _slot._sem is None:
            _slot._sem = asyncio.Semaphore(3)
        await _slot._sem.acquire()
        return self

    async def __aexit__(self, *exc):
        _slot._sem.release()  # type: ignore[union-attr]
        return False
