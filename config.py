"""Konfigurasi bot — semua nilai dibaca dari environment / .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int = 0) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _ids(name: str, default: str = "") -> list[int]:
    raw = os.environ.get(name) or default
    out: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


# ── Telegram credentials ────────────────────────────────────────────────
API_ID = _int("API_ID")
API_HASH = (os.environ.get("API_HASH") or "").strip()
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or "").strip()
SESSION_STRING = (os.environ.get("SESSION_STRING") or "").strip()

OWNER_ID = _int("OWNER_ID")
SUDO_USERS = _ids("SUDO_USERS")
LOG_CHANNEL = _int("LOG_CHANNEL")

# ── Branding ────────────────────────────────────────────────────────────
BOT_NAME = os.environ.get("BOT_NAME", "Musicem")
SUPPORT_CHAT = os.environ.get("SUPPORT_CHAT", "")
UPDATES_CHANNEL = os.environ.get("UPDATES_CHANNEL", "")

# ── Media / storage ─────────────────────────────────────────────────────
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", BASE_DIR / "downloads")).expanduser()
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data")).expanduser()
COOKIES_FILE = Path(os.environ.get("COOKIES_FILE", BASE_DIR / "cookies.txt")).expanduser()

MAX_DURATION = _int("MAX_DURATION", 3 * 60 * 60)      # detik per track
MAX_FILESIZE = _int("MAX_FILESIZE", 200 * 1024 * 1024)
QUEUE_LIMIT = _int("QUEUE_LIMIT", 50)
CACHE_TTL = _int("CACHE_TTL", 6 * 60 * 60)            # file download dihapus setelah ini
SEARCH_LIMIT = _int("SEARCH_LIMIT", 5)
LEAVE_TIMEOUT = _int("LEAVE_TIMEOUT", 180)            # auto-leave VC saat idle

# ── Mode pengiriman ────────────────────────────────────────────────────
# false = mode file: /play & /vplay kirim file ke chat (tanpa voice chat)
VOICE_CHAT = os.environ.get("VOICE_CHAT", "false").strip().lower() in {"1", "true", "yes"}
MAX_UPLOAD = _int("MAX_UPLOAD", 50 * 1024 * 1024)

# ── Playback defaults ───────────────────────────────────────────────────
VIDEO_HEIGHT = _int("VIDEO_HEIGHT", 720)
AUDIO_QUALITY = os.environ.get("AUDIO_QUALITY", "high").strip().lower()
DEFAULT_VOLUME = _int("DEFAULT_VOLUME", 100)

# ── Misc ────────────────────────────────────────────────────────────────
DEBUG = os.environ.get("DEBUG", "false").strip().lower() in {"1", "true", "yes"}

# auto = mode penuh kalau kredensial lengkap, kalau tidak mode lite
MODE = os.environ.get("MODE", "auto").strip().lower()


def missing() -> list[str]:
    """Nama env yang wajib tapi belum diisi."""
    need = []
    if not API_ID:
        need.append("API_ID")
    if not API_HASH:
        need.append("API_HASH")
    if not BOT_TOKEN:
        need.append("BOT_TOKEN")
    if not SESSION_STRING:
        need.append("SESSION_STRING")
    return need


def prepare_dirs() -> None:
    for path in (DOWNLOAD_DIR, DATA_DIR):
        path.mkdir(parents=True, exist_ok=True)
