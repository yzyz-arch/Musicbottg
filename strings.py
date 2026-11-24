"""Semua teks yang dikirim bot ke user (HTML parse mode)."""
from __future__ import annotations

from config import BOT_NAME

START = (
    f"🎧 <b>{BOT_NAME}</b>\n\n"
    "Bot musik Telegram dengan streaming voice chat realtime.\n"
    "Tambahin aku ke grup, jadikan <b>admin</b>, terus mainkan lagu apa aja.\n\n"
    "<b>Perintah utama</b>\n"
    "• /play <code>judul / link</code> — putar musik di voice chat\n"
    "• /vplay <code>judul / link</code> — putar video\n"
    "• /song <code>judul</code> — kirim file MP3\n"
    "• /queue — lihat antrean\n"
    "• /help — semua perintah\n\n"
    "Jalan 24/7. Selamat mendengarkan 🎶"
)

HELP = (
    "📖 <b>Menu Perintah</b>\n\n"
    "<b>▶️ Pemutaran</b>\n"
    "<code>/play &lt;judul|link&gt;</code> — musik\n"
    "<code>/vplay &lt;judul|link&gt;</code> — video\n"
    "<code>/song &lt;judul|link&gt;</code> — download MP3\n"
    "<code>/pause</code> — pause\n"
    "<code>/resume</code> — lanjut\n"
    "<code>/skip</code> — lagu berikutnya\n"
    "<code>/seek &lt;detik|mm:ss&gt;</code> — lompat ke posisi\n"
    "<code>/end</code> — stop &amp; bersihkan antrean\n"
    "<code>/loop off|one|all</code> — mode ulang\n"
    "<code>/volume &lt;1-200&gt;</code> — atur volume\n\n"
    "<b>📋 Info</b>\n"
    "<code>/queue</code> — antrean lagu\n"
    "<code>/current</code> — lagu yang diputar\n"
    "<code>/ping</code> — latensi bot\n"
    "<code>/id</code> — info chat/user\n\n"
    "<b>🛠 Admin</b>\n"
    "<code>/auth</code> <code>/unauth</code> — izinkan user lain kontrol\n"
    "<code>/sudoers</code> — daftar user diizinkan\n"
    "<code>/stats</code> — statistik bot\n\n"
    "Kontrol musik cuma bisa dipakai admin grup atau user yang di-<i>auth</i>."
)

NO_QUERY = "❌ Kasih judul atau link ya. Contoh: <code>/play lofi hip hop</code>"
SEARCHING = "🔎 Nyari <b>{q}</b>…"
NOT_FOUND = "❌ Hasil nggak ketemu buat <b>{q}</b>."
SEARCH_RESULTS = "🎵 <b>Hasil pencarian</b> — <i>{q}</i>\nPilih salah satu:"
DOWNLOADING = "⬇️ Download <b>{title}</b>\n<code>{bar}</code> {pct}%"
PLAYING = "▶️ <b>{title}</b>\n⏱ <code>{dur}</code> • 👤 {user}"
ADDED_QUEUE = "➕ Masuk antrean <b>#{pos}</b>\n<b>{title}</b>\n⏱ <code>{dur}</code> • 👤 {user}"
QUEUE_EMPTY = "📭 Antrean kosong."
PAUSED = "⏸ Pause <b>{title}</b>"
RESUMED = "▶️ Lanjut <b>{title}</b>"
SKIPPED = "⏭ Skip <b>{title}</b>"
ENDED = "⏹ Stop. Antrean dibersihkan."
LOOP_SET = "🔁 Mode ulang: <b>{mode}</b>"
VOLUME_SET = "🔊 Volume: <b>{vol}%</b>"
NOT_PLAYING = "❌ Nggak ada yang diputar sekarang."
NOT_IN_VC = "❌ Aku nggak ada di voice chat."
NO_PERM = "🚫 Cuma admin grup / user ter-<i>auth</i> yang bisa kontrol."
NEED_VC = (
    "🎙 <b>Voice chat belum aktif.</b>\n"
    "Mulai voice chat dulu di grup ini, lalu ulangi perintahnya."
)
NEED_ASSISTANT = (
    "⚠️ <b>Assistant belum bisa join.</b>\n"
    "Jadikan bot admin dengan izin <i>invite users</i>, lalu ulangi."
)
TOO_LONG = "❌ Durasi <code>{dur}</code> terlalu panjang (maks <code>{max}</code>)."
QUEUE_FULL = "❌ Antrean penuh (maks {limit} lagu)."
QUEUE_HEADER = "📋 <b>Antrean</b> — {count} lagu\n\n"
QUEUE_ROW = "{idx}. <b>{title}</b> — <code>{dur}</code>\n"
NOW_HEADER = "▶️ <b>Sedang diputar</b>\n<b>{title}</b>\n⏱ <code>{pos} / {dur}</code> • 🔊 {vol}% • 🔁 {loop}\n"
ERROR = "💥 Error: <code>{err}</code>"
ALREADY_PLAYING = "▶️ Sudah diputar: <b>{title}</b>"
LEFT_EMPTY = "👋 Antrean habis, aku keluar dari voice chat."
SEEKED = "⏩ Lompat ke <code>{pos}</code>"
UPLOADING = "📤 Upload <b>{title}</b>…"
SENT = "✅ Terkirim: <b>{title}</b>"
FILE_TOO_BIG = (
    "⚠️ File <code>{size}</code> melebihi limit upload bot (<code>{limit}</code>).\n"
    "Link: {url}"
)
NO_VC_MODE = (
    "ℹ️ Bot jalan <b>tanpa voice chat</b> — lagu dikirim sebagai file.\n"
    "Pakai <code>/play judul</code> lalu pilih hasilnya."
)
FILE_MODE_NOTE = "📁 Mode file: lagu dikirim langsung ke chat (tanpa voice chat)."
AUTH_OK = "✅ <b>{user}</b> sekarang bisa kontrol musik di chat ini."
UNAUTH_OK = "✅ Akses <b>{user}</b> dicabut."
AUTH_LIST = "🛡 <b>User ter-auth</b>\n\n{rows}"
NO_AUTHED = "🛡 Belum ada user ter-auth di chat ini."
OWNER_ONLY = "🚫 Cuma owner bot yang bisa pakai ini."
STATS = (
    "📊 <b>Statistik</b>\n\n"
    "💬 Chat: <code>{chats}</code>\n"
    "👥 User: <code>{users}</code>\n"
    "🎵 Lagu diputar: <code>{played}</code>\n"
    "⬇️ Download: <code>{downloads}</code>\n"
    "📡 Aktif VC: <code>{active}</code>\n"
    "🏓 Ping: <code>{ping} ms</code>"
)
